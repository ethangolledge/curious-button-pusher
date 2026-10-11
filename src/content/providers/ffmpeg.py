"""Thin wrappers around the local ffmpeg and ffprobe binaries."""

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class FfmpegError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MediaInfo:
    duration: float
    width: int | None
    height: int | None
    fps: float | None


def available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def run(*args: str | Path) -> str:
    """Run ffmpeg quietly; return its stderr, where filters report their measurements."""
    command = ["ffmpeg", "-hide_banner", "-nostdin", "-y", *(str(arg) for arg in args)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        # A failed render leaves a broken file at its output path; renders are cached by
        # path, so it would be taken as finished next time.
        output = args[-1] if args else None
        if isinstance(output, Path) and output.is_file():
            output.unlink()
        tail = "\n".join(result.stderr.strip().splitlines()[-8:])
        raise FfmpegError(f"ffmpeg failed ({result.returncode}):\n{tail}")
    return result.stderr


def decode(path: Path, *, sample_rate: int) -> bytes:
    """The audio as raw mono 32-bit float samples, for analysis."""
    command = [
        "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(path),
        "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "-",
    ]  # fmt: skip
    result = subprocess.run(command, capture_output=True, check=False)
    if result.returncode != 0:
        raise FfmpegError(f"ffmpeg could not decode {path}")
    return result.stdout


def probe(path: Path) -> MediaInfo:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height,avg_frame_rate",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise FfmpegError(f"ffprobe could not read {path}: {result.stderr.strip()}")
    data = json.loads(result.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    fps = None
    if video and video.get("avg_frame_rate", "0/0") != "0/0":
        numerator, denominator = video["avg_frame_rate"].split("/")
        fps = int(numerator) / int(denominator)
    return MediaInfo(
        # A still picture has no duration.
        duration=float(data["format"].get("duration", 0.0)),
        width=video.get("width") if video else None,
        height=video.get("height") if video else None,
        fps=fps,
    )
