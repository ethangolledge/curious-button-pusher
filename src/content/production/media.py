"""Media generation: images, video, speech, transcription, music, and perception.

One protocol, two implementations: OpenRouter for real runs (the same key as every
text model and Jev), and an ffmpeg-backed fake that produces real, small files so the
whole pipeline runs offline and deterministically in tests.
"""

import base64
import hashlib
import io
import json
import math
import mimetypes
import os
import tempfile
import time
import wave
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from content.errors import ConfigurationError
from content.providers import ffmpeg
from content.providers.base import Usage
from content.providers.http import RETRY_WAITS, retry_after
from content.schemas.media import Word
from content.schemas.perception import Observation, Perception
from content.story.pace import syllables
from content.theme import DirectionStyle

API_ROOT = "https://openrouter.ai/api/v1"
VIDEO_POLL_SECONDS = 10.0
VIDEO_TIMEOUT_SECONDS = 20 * 60


class MediaProvider(Protocol):
    def image(
        self,
        *,
        model: str,
        prompt: str,
        references: Sequence[Path],
        aspect_ratio: str,
        resolution: str,
        seed: int,
    ) -> tuple[bytes, Usage]: ...

    def video(
        self,
        *,
        model: str,
        prompt: str,
        first_frame: Path,
        last_frame: Path | None,
        duration: int,
        resolution: str,
        aspect_ratio: str,
        seed: int,
    ) -> tuple[bytes, Usage]: ...

    def speech(
        self,
        *,
        model: str,
        text: str,
        voice: str | None,
        reference_audio: Path | None,
        reference_transcript: str | None,
        direction: str | None = None,
        direction_style: DirectionStyle = "none",
    ) -> tuple[bytes, Usage]: ...

    def transcribe(self, *, model: str, audio: Path) -> tuple[list[Word], Usage]: ...

    def music(self, *, model: str, prompt: str, seconds: float) -> tuple[bytes, Usage]: ...

    def perceive(
        self,
        *,
        model: str,
        instructions: str,
        images: Sequence[Path],
    ) -> tuple[list[Observation], Usage]: ...


def data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


class OpenRouterMediaProvider:
    """Every generator through OpenRouter. Media endpoints are newer than chat; the request
    shapes follow OpenRouter's documentation and are confirmed by the first paid pilot."""

    def __init__(self, http: Any | None = None, chat: Any | None = None) -> None:
        if http is not None and chat is not None:
            self._http, self._chat = http, chat
            return
        key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not key:
            raise ConfigurationError("Set OPENROUTER_API_KEY in .env to generate media")
        try:
            import httpx
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Media generation requires: pip install -e '.[live]'") from exc
        self._http = httpx.Client(
            base_url=API_ROOT,
            headers={"Authorization": f"Bearer {key}"},
            timeout=300.0,
            transport=httpx.HTTPTransport(retries=2),
        )
        self._chat = OpenAI(base_url=API_ROOT, api_key=key)

    def image(
        self,
        *,
        model: str,
        prompt: str,
        references: Sequence[Path],
        aspect_ratio: str,
        resolution: str,
        seed: int,
    ) -> tuple[bytes, Usage]:
        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "seed": seed,
            "n": 1,
        }
        if references:
            body["input_references"] = [_image_part(path) for path in references]
        data = self._post_refusable("/images", body)
        return as_png(base64.b64decode(data["data"][0]["b64_json"])), _usage(model, data)

    def video(
        self,
        *,
        model: str,
        prompt: str,
        first_frame: Path,
        last_frame: Path | None,
        duration: int,
        resolution: str,
        aspect_ratio: str,
        seed: int,
    ) -> tuple[bytes, Usage]:
        frames = [{**_image_part(first_frame), "frame_type": "first_frame"}]
        if last_frame is not None:
            frames.append({**_image_part(last_frame), "frame_type": "last_frame"})
        job = self._post_refusable(
            "/videos",
            {
                "model": model,
                "prompt": prompt,
                "frame_images": frames,
                "duration": duration,
                "resolution": resolution,
                "aspect_ratio": aspect_ratio,
                "seed": seed,
                "generate_audio": False,
            },
        )
        deadline = time.monotonic() + VIDEO_TIMEOUT_SECONDS
        while job.get("status") not in {"completed", "failed"}:
            if time.monotonic() > deadline:
                raise RuntimeError(f"Video job {job.get('id')} did not finish in time")
            time.sleep(VIDEO_POLL_SECONDS)
            response = self._http.get(job["polling_url"])
            response.raise_for_status()
            job = response.json()
        if job["status"] == "failed":
            raise GenerationRefused(f"Video job {job.get('id')} failed: {job.get('error')}")
        content = self._http.get(f"/videos/{job['id']}/content", params={"index": 0})
        content.raise_for_status()
        return content.content, _usage(model, job)

    def speech(
        self,
        *,
        model: str,
        text: str,
        voice: str | None,
        reference_audio: Path | None,
        reference_transcript: str | None,
        direction: str | None = None,
        direction_style: DirectionStyle = "none",
    ) -> tuple[bytes, Usage]:
        body: dict[str, Any] = {"model": model, "input": text, "response_format": "mp3"}
        if voice is not None:
            body["voice"] = voice
        if direction is not None:
            body.update(_directed(body["input"], direction, direction_style))
        if reference_audio is not None:
            body["input_references"] = [
                {"type": "input_audio", "input_audio": {"data": data_url(reference_audio)}},
                *([{"type": "text", "text": reference_transcript}] if reference_transcript else []),
            ]
        response = self._post("/audio/speech", body)
        if response.status_code == 400 and "pcm" in response.text:
            # Some voices (Gemini) only return raw PCM; ask for that and wrap it as WAV.
            response = self._post("/audio/speech", {**body, "response_format": "pcm"})
        if response.status_code >= 400:
            raise RuntimeError(f"{model} speech failed ({response.status_code}): {response.text}")
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("audio/pcm"):
            return _wav_from_pcm(response.content, content_type), Usage(model=model)
        return response.content, Usage(model=model)

    def transcribe(self, *, model: str, audio: Path) -> tuple[list[Word], Usage]:
        data = self._post_json(
            "/audio/transcriptions",
            {
                "model": model,
                "input_audio": {
                    "data": base64.b64encode(audio.read_bytes()).decode("ascii"),
                    "format": audio.suffix.lstrip("."),
                },
                "language": "en",
                "response_format": "verbose_json",
                "timestamp_granularities": ["word"],
            },
        )
        words = [
            Word(text=item["word"], start=float(item["start"]), end=float(item["end"]))
            for item in data.get("words", [])
        ]
        return words, _usage(model, data)

    def music(self, *, model: str, prompt: str, seconds: float) -> tuple[bytes, Usage]:
        audio: list[str] = []
        usage: dict[str, Any] = {}
        with self._http.stream(
            "POST",
            "/chat/completions",
            json={
                "model": model,
                "messages": [
                    {"role": "user", "content": f"{prompt} Length: about {round(seconds)} seconds."}
                ],
                "modalities": ["text", "audio"],
                "audio": {"format": "mp3"},
                "stream": True,
            },
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                chunk = json.loads(line[len("data: ") :])
                usage = chunk.get("usage") or usage
                for choice in chunk.get("choices", []):
                    if part := (choice.get("delta", {}).get("audio") or {}).get("data"):
                        audio.append(part)
        if not audio:
            raise RuntimeError(f"{model} returned no audio")
        return base64.b64decode("".join(audio)), _usage(model, {"usage": usage})

    def perceive(
        self,
        *,
        model: str,
        instructions: str,
        images: Sequence[Path],
    ) -> tuple[list[Observation], Usage]:
        completion = self._chat.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": instructions},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Describe these {len(images)} images, in order."},
                        *(
                            {"type": "image_url", "image_url": {"url": data_url(path)}}
                            for path in images
                        ),
                    ],
                },
            ],
            response_format=Perception,
            extra_body={"provider": {"require_parameters": True}},
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError(f"{model} returned no perception")
        usage = completion.usage
        return Perception.model_validate(parsed).observations, Usage(
            model=completion.model or model,
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
            cost_usd=getattr(usage, "cost", None),
        )

    def _post(self, path: str, body: dict[str, Any]) -> Any:
        """POST, waiting and retrying while the provider is busy (429) or failing (5xx).
        Scenes are rendered in parallel, so a burst of requests can hit a rate limit."""
        for wait in RETRY_WAITS:
            response = self._http.post(path, json=body)
            if response.status_code != 429 and response.status_code < 500:
                return response
            time.sleep(retry_after(response) or wait)
        return self._http.post(path, json=body)

    def _post_refusable(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """A generation request whose rejection is reported as a refusal, so the producer
        can try a safer depiction instead of stopping the run."""
        response = self._post(path, body)
        if response.status_code in REFUSAL_STATUSES:
            raise GenerationRefused(f"{path} refused ({response.status_code}): {response.text}")
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data

    def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        response = self._post(path, body)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data


# Bad-request and forbidden answers to a generation are usually content-policy refusals.
REFUSAL_STATUSES = frozenset({400, 403, 422})


class GenerationRefused(RuntimeError):
    """The model declined or failed to render this request (often a content policy)."""


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def as_png(content: bytes) -> bytes:
    """Image models may answer in JPEG or WebP; keyframes are stored as real PNGs."""
    if content.startswith(PNG_SIGNATURE):
        return content
    with tempfile.TemporaryDirectory() as directory:
        source, target = Path(directory) / "image", Path(directory) / "image.png"
        source.write_bytes(content)
        ffmpeg.run("-i", source, "-frames:v", "1", target)
        return target.read_bytes()


def _wav_from_pcm(pcm: bytes, content_type: str) -> bytes:
    """Wrap raw 16-bit PCM in a WAV header, using the rate and channels the provider
    states in its content type (for example `audio/pcm;rate=24000;channels=1`)."""
    fields = dict(part.strip().split("=", 1) for part in content_type.split(";")[1:] if "=" in part)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(int(fields.get("channels", 1)))
        wav.setsampwidth(2)
        wav.setframerate(int(fields.get("rate", 24000)))
        wav.writeframes(pcm)
    return buffer.getvalue()


def _directed(text: str, direction: str, style: DirectionStyle) -> dict[str, Any]:
    """Request fields that give a voice model its spoken direction, in the form its
    provider documents (OpenRouter's text-to-speech guide, 27 Sep 2026)."""
    if style == "openai":
        return {"provider": {"options": {"openai": {"instructions": direction}}}}
    if style == "google":
        return {
            "provider": {"options": {"google-ai-studio": {"speech_metadata": {"style": direction}}}}
        }
    if style == "inline":
        return {"input": f"[{direction}] {text}"}
    return {}


def _image_part(path: Path) -> dict[str, Any]:
    return {"type": "image_url", "image_url": {"url": data_url(path)}}


def _usage(model: str, data: dict[str, Any]) -> Usage:
    usage = data.get("usage") or {}
    return Usage(
        model=data.get("model", model),
        input_tokens=usage.get("input_tokens", usage.get("prompt_tokens")),
        output_tokens=usage.get("output_tokens", usage.get("completion_tokens")),
        cost_usd=usage.get("cost"),
    )


class FakeMediaProvider:
    """Deterministic offline media made with ffmpeg: colour stills, crossfades, tones."""

    # Speaks at a fixed syllable pace (Lewis's fitted one), so offline timing is exact
    # and matches the reference narrator the tests use.
    SECONDS_PER_UTTERANCE = 0.757
    SECONDS_PER_SYLLABLE = 0.3007

    def __init__(self, *, brightness: float = 128.0, saturation: float = 0.0) -> None:
        """Stills are drawn at this mean brightness (luma) and saturation: give it the
        theme's neutral tone, and offline runs never redraw for colour."""
        self.calls: list[str] = []
        self.brightness = brightness
        self.saturation = saturation
        # textstat loads its pronouncing dictionary on first use; passages are narrated in
        # parallel, and threads racing that first load crash it.
        syllables("warm")

    def image(
        self,
        *,
        model: str,
        prompt: str,
        references: Sequence[Path],
        aspect_ratio: str,
        resolution: str,
        seed: int,
    ) -> tuple[bytes, Usage]:
        self.calls.append("image")
        # One flat colour per prompt, its brightness varied slightly; its tint sits on the
        # line where blue and red pull equally, so it is neither warm nor cool.
        digest = hashlib.sha256(f"{prompt}{seed}".encode()).digest()
        luma = round(self.brightness) + digest[0] % 3
        tint = round(128 - self.saturation / math.sqrt(2))
        return self._render(
            ".png",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={_size(aspect_ratio, small=True)},format=yuv444p,"
            f"lutyuv=y={luma}:u={tint}:v={tint}",
            "-frames:v",
            "1",
        ), Usage(model=model)

    def video(
        self,
        *,
        model: str,
        prompt: str,
        first_frame: Path,
        last_frame: Path | None,
        duration: int,
        resolution: str,
        aspect_ratio: str,
        seed: int,
    ) -> tuple[bytes, Usage]:
        self.calls.append("video")
        size = _size(aspect_ratio, small=True)
        # Moving grain stands in for the constant motion of a real morph.
        scale = (
            f"scale={size.replace('x', ':')},setsar=1,fps=24,format=yuv420p,noise=alls=10:allf=t+u"
        )
        if last_frame is None:
            graph = f"[0]{scale},format=yuv420p"
            inputs: list[str | Path] = ["-loop", "1", "-t", str(duration), "-i", first_frame]
        else:
            morph = duration * 0.4
            graph = (
                f"[0]{scale}[a];[1]{scale}[b];"
                f"[a][b]xfade=transition=fade:duration={morph}:offset={duration - morph},"
                "format=yuv420p"
            )
            inputs = [
                "-loop",
                "1",
                "-t",
                str(duration),
                "-i",
                first_frame,
                "-loop",
                "1",
                "-t",
                str(duration),
                "-i",
                last_frame,
            ]
        return self._render(
            ".mp4",
            *inputs,
            "-filter_complex",
            graph,
            "-t",
            str(duration),
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
        ), Usage(model=model)

    def speech(
        self,
        *,
        model: str,
        text: str,
        voice: str | None,
        reference_audio: Path | None,
        reference_transcript: str | None,
        direction: str | None = None,
        direction_style: DirectionStyle = "none",
    ) -> tuple[bytes, Usage]:
        self.calls.append("speech")
        seconds = self.SECONDS_PER_UTTERANCE + self.SECONDS_PER_SYLLABLE * syllables(text)
        return self._render(
            ".wav",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=220:duration={seconds:.3f}",
            "-ar",
            "48000",
        ), Usage(model=model)

    def transcribe(self, *, model: str, audio: Path) -> tuple[list[Word], Usage]:
        # No words: the aligner then spreads the known script evenly over the clip.
        self.calls.append("transcribe")
        return [], Usage(model=model)

    def music(self, *, model: str, prompt: str, seconds: float) -> tuple[bytes, Usage]:
        self.calls.append("music")
        return self._render(
            ".wav",
            "-f",
            "lavfi",
            "-i",
            f"anoisesrc=color=pink:amplitude=0.1:duration={seconds:.3f}",
            "-ar",
            "48000",
        ), Usage(model=model)

    def perceive(
        self,
        *,
        model: str,
        instructions: str,
        images: Sequence[Path],
    ) -> tuple[list[Observation], Usage]:
        self.calls.append("perceive")
        observation = Observation(
            subject="the anchor subject",
            setting="the anchor setting",
            composition="centred vertical frame",
            rendering_style="flat illustration with a paper grain",
            dominant_colours=["void black", "teal"],
            lighting="low-key",
            visible_text=[],
            artefacts=[],
        )
        return [observation for _ in images], Usage(model=model)

    @staticmethod
    def _render(suffix: str, *args: str | Path) -> bytes:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / f"out{suffix}"
            ffmpeg.run(*args, output)
            return output.read_bytes()


def _size(aspect_ratio: str, *, small: bool = False) -> str:
    width, height = (int(part) for part in aspect_ratio.split(":"))
    long_side = 640 if small else 1920
    if height >= width:
        return f"{round(long_side * width / height / 2) * 2}x{long_side}"
    return f"{long_side}x{round(long_side * height / width / 2) * 2}"
