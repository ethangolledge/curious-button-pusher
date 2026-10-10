"""Auditions: the same passage in every candidate voice, and the theme's music prompt in
every variation, so a person can pick one of each and lock it in the theme."""

import time
from pathlib import Path

from content.production.media import MediaProvider
from content.state import CallRecord, call_record
from content.theme import Theme


def audition(
    theme: Theme, media: MediaProvider, output_directory: Path
) -> tuple[list[str], list[CallRecord]]:
    """Render the theme's audition passage with each candidate voice, with and without
    spoken direction when the voice takes it. A candidate that fails is reported, not fatal.

    Lock the chosen one by setting `voice.model`, `voice.voice`, and
    `voice.direction_style` in the theme. Returns the clips and the calls paid for."""
    voice = theme.spec.voice
    text = theme.spoken_text(voice.audition_text)
    output_directory.mkdir(parents=True, exist_ok=True)
    results: list[str] = []
    calls: list[CallRecord] = []
    master = theme.reference_audio
    for candidate in voice.candidates:
        if candidate.clone and master is None:
            results.append(f"{candidate.model}: skipped (lock a master voice first)")
            continue
        directions = (
            [None] if candidate.direction_style == "none" else [None, voice.audition_direction]
        )
        for direction in directions:
            base = "master" if candidate.clone else candidate.voice or "default"
            name = f"{candidate.model.replace('/', '_')}__{base}"
            clip = output_directory / f"{name}{'__directed' if direction else ''}"
            started = time.perf_counter()
            try:
                audio, usage = media.speech(
                    model=candidate.model,
                    text=text,
                    voice=candidate.voice,
                    reference_audio=master if candidate.clone else None,
                    reference_transcript=voice.reference_transcript if candidate.clone else None,
                    direction=direction,
                    direction_style=candidate.direction_style,
                )
            except Exception as error:  # one failed candidate must not stop the rest
                results.append(f"{name}: failed ({error})")
                continue
            calls.append(call_record("voice_audition", usage, time.perf_counter() - started))
            clip = clip.with_name(clip.name + _suffix(audio))
            clip.write_bytes(audio)
            results.append(str(clip))
    return results, calls


def design_voices(
    theme: Theme, media: MediaProvider, output_directory: Path
) -> tuple[list[str], list[CallRecord]]:
    """Render the audition passage once per voice design. Each clip reads the audition
    passage, so it can become the master recording with that passage as its transcript.
    Returns the clips and the calls paid for."""
    voice = theme.spec.voice
    text = theme.spoken_text(voice.audition_text)
    output_directory.mkdir(parents=True, exist_ok=True)
    results: list[str] = []
    calls: list[CallRecord] = []
    for index, design in enumerate(voice.designs, start=1):
        clip = output_directory / f"design-{index}"
        started = time.perf_counter()
        try:
            audio, usage = media.speech(
                model=design.model,
                text=text,
                voice=design.voice,
                reference_audio=None,
                reference_transcript=None,
                direction=design.description,
                direction_style=design.direction_style,
            )
        except Exception as error:  # one failed design must not stop the rest
            results.append(f"design-{index} ({design.model}): failed ({error})")
            continue
        calls.append(call_record("voice_design", usage, time.perf_counter() - started))
        clip = clip.with_name(clip.name + _suffix(audio))
        clip.write_bytes(audio)
        clip.with_suffix(".json").write_text(design.model_dump_json(indent=2), encoding="utf-8")
        results.append(f"{clip}  ({design.model}, {design.voice or 'default'})")
    return results, calls


def music_audition(
    theme: Theme, media: MediaProvider, model: str, output_directory: Path, *, seconds: float = 60
) -> tuple[list[Path], list[CallRecord]]:
    """Render one candidate bed per variation of the theme's music prompt; returns the beds
    and the calls paid for.

    Lock the chosen one by copying it into the theme and setting `music.track`."""
    music = theme.spec.music
    output_directory.mkdir(parents=True, exist_ok=True)
    tracks: list[Path] = []
    calls: list[CallRecord] = []
    for index, variation in enumerate(music.variations or [""], start=1):
        started = time.perf_counter()
        audio, usage = media.music(
            model=model, prompt=f"{music.prompt} {variation}".strip(), seconds=seconds
        )
        calls.append(call_record("music_audition", usage, time.perf_counter() - started))
        track = output_directory / f"music-{index}.mp3"
        track.write_bytes(audio)
        tracks.append(track)
    return tracks, calls


def _suffix(audio: bytes) -> str:
    return ".wav" if audio[:4] == b"RIFF" else ".mp3"
