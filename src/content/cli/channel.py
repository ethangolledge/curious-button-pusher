"""Making a channel: `new-channel`, and the tools that design and lock its narrator and music."""

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from content.cli.spend import record_spend
from content.cli.storage import keep_theme
from content.config import (
    load_config,
    write_channel_config,
)
from content.errors import ConfigurationError
from content.production import ffmpeg
from content.production.assemble import mix_audio
from content.production.audition import audition, design_voices, music_audition
from content.production.checks import loudness_range
from content.production.music_map import analyse_track, save_map
from content.production.narration_analysis import analyse, apply_to_theme
from content.production.score import arrangements, choose, render
from content.production.voice_lock import lock_voice
from content.spend import now
from content.theme import ThemeError, new_theme
from content.workflow.providers import (
    build_media_provider,
)


def _audition(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="content voice-audition",
        description="Render one passage in every candidate voice listed in the theme.",
    )
    parser.add_argument("--config", type=Path, help="Runtime configuration JSON")
    parser.add_argument("--output", type=Path, help="Directory for the audition clips")
    args = parser.parse_args(arguments)
    try:
        config = load_config(args.config)
        media = build_media_provider(config)
    except ConfigurationError as exc:
        parser.error(str(exc))
    if media is None:
        parser.error("Voice audition needs a configuration with a production section")
    output = args.output or config.application.output_directory / "_theme" / "voice-audition"
    clips, calls = audition(config.theme, media, output)
    for clip in clips:
        print(f"Voice: {clip}")
    record_spend(config, calls, source="voice-audition", session=now(), stage="tools")
    print("Set voice.model, voice.voice and voice.direction_style in the theme to lock it.")
    return 0


def _voice_design(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="content voice-design",
        description="Render the theme's narrator descriptions as candidate voices.",
    )
    parser.add_argument("--config", type=Path, help="Runtime configuration JSON")
    parser.add_argument("--output", type=Path, help="Directory for the designed voices")
    args = parser.parse_args(arguments)
    try:
        config = load_config(args.config)
        media = build_media_provider(config)
    except ConfigurationError as exc:
        parser.error(str(exc))
    if media is None:
        parser.error("Voice design needs a configuration with a production section")
    output = args.output or config.application.output_directory / "_theme" / "voice-design"
    results, calls = design_voices(config.theme, media, output)
    for result in results:
        print(f"Design: {result}")
    record_spend(config, calls, source="voice-design", session=now(), stage="tools")
    print("Lock your favourite with: python -m content voice-lock <clip> --model <cloning model>")
    return 0


def _voice_lock(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="content voice-lock",
        description="Make a recording the channel's master voice, cloned for every narration.",
    )
    parser.add_argument(
        "clip", type=Path, help="The master recording (a designed voice or a person)"
    )
    parser.add_argument("--model", required=True, help="Cloning model that will speak the voice")
    parser.add_argument("--voice", help="Base voice ID, when the cloning model needs one")
    parser.add_argument(
        "--direction-style",
        choices=["none", "openai", "google", "inline"],
        default="none",
        help="How the cloning model takes spoken direction",
    )
    parser.add_argument(
        "--transcript", help="What the clip says (default: the theme's audition passage)"
    )
    parser.add_argument("--config", type=Path, help="Runtime configuration JSON")
    args = parser.parse_args(arguments)
    try:
        config = load_config(args.config)
    except ConfigurationError as exc:
        parser.error(str(exc))
    theme = config.theme
    master = lock_voice(
        theme,
        args.clip,
        transcript=args.transcript or theme.spoken_text(theme.spec.voice.audition_text),
        model=args.model,
        voice=args.voice,
        direction_style=args.direction_style,
    )
    print(
        f"Locked {master}. Every narration take is brought to "
        f"{theme.spec.voice.words_per_minute:.0f} words per minute."
    )
    keep_theme(config)
    return 0


def _music_audition(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="content music-audition",
        description="Render one music bed per variation of the theme's music prompt.",
    )
    parser.add_argument("--config", type=Path, help="Runtime configuration JSON")
    parser.add_argument("--output", type=Path, help="Directory for the candidate beds")
    parser.add_argument("--seconds", type=float, default=60, help="Length of each candidate")
    args = parser.parse_args(arguments)
    try:
        config = load_config(args.config)
        media = build_media_provider(config)
    except ConfigurationError as exc:
        parser.error(str(exc))
    if media is None or config.production is None or config.production.music_model is None:
        parser.error("Music audition needs a production section with a music_model")
    output = args.output or config.theme.root / "music" / "candidates"
    model = config.production.music_model
    tracks, calls = music_audition(config.theme, media, model, output, seconds=args.seconds)
    record_spend(config, calls, source="music-audition", session=now(), stage="tools")
    for track in tracks:
        swing = loudness_range(track)
        note = "steady" if swing <= 6 else "swells; may pull attention" if swing <= 10 else "busy"
        print(f"Music: {track}  (loudness range {swing:.1f} LU: {note})")
    print("Copy your choice into the theme's music folder and set music.track to lock it.")
    return 0


def _analyse_narration(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="content analyse-narration",
        description="Measure a reference narration's pace, pauses, and rhythm.",
    )
    parser.add_argument("audio", type=Path, help="Audio or video file of the narration")
    parser.add_argument("--config", type=Path, help="Runtime configuration JSON")
    parser.add_argument(
        "--apply", action="store_true", help="Write the measured targets into the theme"
    )
    args = parser.parse_args(arguments)
    try:
        config = load_config(args.config)
        media = build_media_provider(config)
    except ConfigurationError as exc:
        parser.error(str(exc))
    if media is None or config.production is None:
        parser.error("Analysing narration needs a configuration with a production section")
    with tempfile.TemporaryDirectory() as directory:
        audio = Path(directory) / "narration.mp3"
        ffmpeg.run("-i", args.audio, "-vn", "-ac", "1", "-ar", "16000", audio)
        words, _ = media.transcribe(model=config.production.transcription_model, audio=audio)
    profile = analyse(words)
    print(f"Length: {profile.seconds:.0f} s, {profile.words} words")
    print(f"Speaking rate: {profile.words_per_minute:.0f} words per minute")
    print(f"Rate variation across 10 s windows: ±{profile.rate_spread:.0f} words per minute")
    print(
        f"Pauses: {profile.pauses_per_minute:.0f} per minute, median "
        f"{profile.pause_median:.2f} s, longest tenth {profile.pause_p90:.2f} s+"
    )
    print(
        f"Sentences: {profile.sentence_words_mean:.1f} words on average, "
        f"spread ±{profile.sentence_words_spread:.1f}; {profile.short_share:.0%} very short, "
        f"{profile.long_share:.0%} long, {profile.question_share:.0%} questions"
    )
    if args.apply:
        apply_to_theme(config.theme, profile, source=f"Measured on {args.audio.name}")
        print("Saved the rhythm guidance to the theme (numbers only, never the words).")
    return 0


def _music_lock(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="content music-lock",
        description="Make a track the channel's music: map its beats and phrases, and preview "
        "it under the locked voice.",
    )
    parser.add_argument("track", type=Path, help="The chosen music file")
    parser.add_argument("--config", type=Path, help="Runtime configuration JSON")
    args = parser.parse_args(arguments)
    try:
        config = load_config(args.config)
    except ConfigurationError as exc:
        parser.error(str(exc))
    theme = config.theme
    locked = Path("music") / f"bed{args.track.suffix}"
    (theme.root / locked).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.track, theme.root / locked)
    path = theme.root / "theme.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["music"]["track"] = str(locked)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    track = theme.root / locked
    music = analyse_track(track)
    save_map(music, track.with_suffix(".map.json"))
    print(f"Locked {locked}: {60 / music.beat_seconds:.1f} BPM, {len(music.downbeats)} bars")
    for arrangement in arrangements(music, theme.spec.format.max_seconds):
        print(f"  arrangement {arrangement.seconds:6.1f} s, peak at {arrangement.peak_at:.1f} s")
    if theme.reference_audio is not None:
        preview = config.application.output_directory / "_theme" / "music-lock"
        preview.mkdir(parents=True, exist_ok=True)
        arranged = render(
            track,
            music,
            choose(music, 60, theme.spec.music.outro_seconds, theme.spec.format.max_seconds),
            preview / "music.wav",
        )
        mix_audio(theme.reference_audio, arranged, theme.spec.music, preview / "preview.m4a")
        print(f"Preview (the locked voice over it): {preview / 'preview.m4a'}")
    keep_theme(config)
    return 0


def _music_map(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="content music-map",
        description="Map the locked music bed's beat grid and sections, for scoring stories.",
    )
    parser.add_argument("--config", type=Path, help="Runtime configuration JSON")
    args = parser.parse_args(arguments)
    try:
        config = load_config(args.config)
    except ConfigurationError as exc:
        parser.error(str(exc))
    track = config.theme.music_track
    if track is None:
        parser.error("Lock a music bed first (music.track in the theme)")
    music = analyse_track(track)
    save_map(music, track.with_suffix(".map.json"))
    print(f"{60 / music.beat_seconds:.1f} BPM, {len(music.downbeats)} bars")
    for section in music.sections:
        start, end = music.bar_time(section.start_bar), music.bar_time(section.end_bar)
        bars = f"bars {section.start_bar}–{section.end_bar}"
        print(f"  {section.label:6} {bars:12} {start:5.1f}–{end:.1f} s")
    print("Arrangements a story can use:")
    for arrangement in arrangements(music, config.theme.spec.format.max_seconds):
        print(f"  {arrangement.seconds:6.1f} s, peak at {arrangement.peak_at:.1f} s")
    print(f"Saved {track.with_suffix('.map.json')}; correct it by hand if a phrase is off.")
    keep_theme(config)
    return 0


def _new_channel(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="content new-channel",
        description="Start a channel from the starter kit: its theme and its own configuration, "
        "in themes/<name>/, private to you (gitignored).",
    )
    parser.add_argument("name", help="Folder name for the channel, e.g. my-channel")
    kept_in = parser.add_mutually_exclusive_group()
    kept_in.add_argument(
        "--folder",
        help="A folder to keep the channel and its videos in, e.g. archive (docs/storage.md)",
    )
    kept_in.add_argument(
        "--bucket", help="A Google Cloud Storage bucket to keep them in (docs/google-cloud.md)"
    )
    args = parser.parse_args(arguments)
    themes = Path("themes")
    try:
        target = new_theme(themes / "starter", themes / args.name)
    except ThemeError as exc:
        parser.error(str(exc))
    config = write_channel_config(
        Path("config/config.example.json"), target, bucket=args.bucket, folder=args.folder
    )
    print(f"Created {target}, with its configuration {config}.")
    print(f"Next: follow {target / 'README.md'}, and pass --config {config} to every command.")
    return 0


COMMANDS = {
    "new-channel": _new_channel,
    "voice-audition": _audition,
    "voice-design": _voice_design,
    "voice-lock": _voice_lock,
    "music-audition": _music_audition,
    "music-lock": _music_lock,
    "music-map": _music_map,
    "analyse-narration": _analyse_narration,
}
