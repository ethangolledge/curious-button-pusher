"""Exact media checks that need no model: code measures, Jev judges only what needs taste."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from content.providers import ffmpeg
from content.schemas.media import Word

SCENE_SCORE = re.compile(r"lavfi\.scd\.score:\s*([\d.]+),\s*lavfi\.scd\.time:\s*([\d.]+)")
FREEZE_START = re.compile(r"freeze_start:\s*([\d.]+)")
BLACK_START = re.compile(r"black_start:\s*([\d.]+)")
LOUDNESS = re.compile(r"I:\s*(-?[\d.]+) LUFS")
LOUDNESS_RANGE = re.compile(r"LRA:\s*([\d.]+) LU")
SIGNAL = re.compile(r"lavfi\.signalstats\.(YAVG|SATAVG|SATHIGH|UAVG|VAVG)=([\d.]+)")
# Warmth (red chroma minus blue chroma) past which a frame reads as warm or cool; dark,
# near-neutral frames sit between and suit either. For scale: a flat ochre measures +51,
# a slate -24, a charcoal -3.
WARMTH_MARGIN = 4.0


@dataclass(frozen=True, slots=True)
class Signal:
    """An image's light and colour, measured once on a small copy (8-bit values)."""

    # Mean luma, 0-255.
    brightness: float
    # Mean saturation, and that of the most saturated tenth, 0-181.
    saturation: float
    highlight_saturation: float
    # Red chroma minus blue chroma: positive is warm, negative is cool.
    warmth: float


def measure(image: Path) -> Signal:
    report = ffmpeg.run(
        "-i", image, "-vf", "scale=270:-2,signalstats,metadata=print", "-f", "null", "-"
    )
    values = {name: float(value) for name, value in SIGNAL.findall(report)}
    return Signal(
        brightness=values["YAVG"],
        saturation=values["SATAVG"],
        highlight_saturation=values["SATHIGH"],
        warmth=values["VAVG"] - values["UAVG"],
    )


def hard_cuts(video: Path, threshold: float) -> list[float]:
    """Times where consecutive frames change abruptly. A morph should never jump."""
    report = ffmpeg.run("-i", video, "-vf", f"scdet=threshold={threshold}", "-f", "null", "-")
    return [float(time) for _, time in SCENE_SCORE.findall(report)]


def frozen_or_black(video: Path) -> list[str]:
    report = ffmpeg.run(
        "-i",
        video,
        "-vf",
        "freezedetect=n=0.001:d=1.5,blackdetect=d=0.5:pix_th=0.05",
        "-f",
        "null",
        "-",
    )
    problems = [f"frozen from {float(t):.1f} s" for t in FREEZE_START.findall(report)]
    problems += [f"black from {float(t):.1f} s" for t in BLACK_START.findall(report)]
    return problems


def segment_issues(video: Path, *, hard_cut_threshold: float) -> list[str]:
    issues = [f"hard cut at {time:.1f} s" for time in hard_cuts(video, hard_cut_threshold)]
    return issues + frozen_or_black(video)


def tone_issues(
    signal: Signal, *, max_mean_brightness: float, max_highlight_saturation: float
) -> list[str]:
    """Too bright or too saturated for the theme, whatever the scene."""
    issues = []
    if signal.brightness > max_mean_brightness:
        issues.append(f"too bright (mean {signal.brightness:.0f}, limit {max_mean_brightness:.0f})")
    if signal.highlight_saturation > max_highlight_saturation:
        issues.append(
            f"colour too saturated (highlights {signal.highlight_saturation:.0f}, "
            f"limit {max_highlight_saturation:.0f})"
        )
    return issues


def temperature_issues(signal: Signal, expected: str | None) -> list[str]:
    """A keyframe whose colour temperature works against its scene's field."""
    if expected == "warm" and signal.warmth < -WARMTH_MARGIN:
        return [f"colour too cool for the scene (warmth {signal.warmth:.0f})"]
    if expected == "cool" and signal.warmth > WARMTH_MARGIN:
        return [f"colour too warm for the scene (warmth {signal.warmth:.0f})"]
    return []


def colour_issues(
    signal: Signal,
    *,
    target_brightness: float,
    target_saturation: float,
    brightness_tolerance: float,
    saturation_tolerance: float,
) -> list[str]:
    """A keyframe whose light or colour misses its scene's target by more than the
    tolerance: the field asked for one feeling and the image carries another."""
    issues = []
    brightness_miss = signal.brightness - target_brightness
    if abs(brightness_miss) > brightness_tolerance:
        issues.append(
            f"too {'bright' if brightness_miss > 0 else 'dark'} for the scene "
            f"(mean {signal.brightness:.0f}, target {target_brightness:.0f})"
        )
    saturation_miss = signal.saturation - target_saturation
    if abs(saturation_miss) > saturation_tolerance:
        issues.append(
            f"colour too {'saturated' if saturation_miss > 0 else 'muted'} for the scene "
            f"(mean {signal.saturation:.0f}, target {target_saturation:.0f})"
        )
    return issues


def integrated_loudness(audio: Path) -> float:
    report = ffmpeg.run("-i", audio, "-af", "ebur128", "-f", "null", "-")
    values = LOUDNESS.findall(report)
    if not values:
        raise ffmpeg.FfmpegError(f"No loudness measurement for {audio}")
    return float(values[-1])


def loudness_range(audio: Path) -> float:
    """How much the level swings (EBU R128 LRA): a bed that stays under a voice barely moves."""
    values = LOUDNESS_RANGE.findall(ffmpeg.run("-i", audio, "-af", "ebur128", "-f", "null", "-"))
    if not values:
        raise ffmpeg.FfmpegError(f"No loudness range measured for {audio}")
    return float(values[-1])


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Share of script words the narration got wrong (substituted, dropped, or added)."""
    expected = _words(reference)
    heard = _words(hypothesis)
    previous = list(range(len(heard) + 1))
    for index, word in enumerate(expected, start=1):
        current = [index]
        for position, candidate in enumerate(heard, start=1):
            current.append(
                min(
                    previous[position] + 1,
                    current[position - 1] + 1,
                    previous[position - 1] + (word != candidate),
                )
            )
        previous = current
    return previous[-1] / max(len(expected), 1)


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


# A pause at least this long where the script has no punctuation sounds like a stumble.
MAX_UNMARKED_PAUSE = 0.45
# A pause at least this long after a transcribed full stop: the voice really ended there.
FRAGMENT_PAUSE = 0.3
SENTENCE_OR_CLAUSE_END = (".", "?", "!", ",", ":", ";", "—")


def listen_issues(passage_id: str, script_text: str, heard: Sequence[Word]) -> list[str]:
    """What a listener would notice in one spoken take, read from its transcript: a
    sentence the voice ended where the script did not (a fragment read as a statement,
    "The minister's brother." then a pause), and a long pause where the script has no mark."""
    written = script_text.split()
    spoken = _joined(heard)
    matcher = SequenceMatcher(
        a=[_normal(word) for word in written],
        b=[_normal(word.text) for word in spoken],
        autojunk=False,
    )
    issues = []
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            index, position = block.a + offset, block.b + offset
            if index >= len(written) - 1 or position >= len(spoken) - 1:
                continue
            mark = written[index].rstrip("'\"’”)")
            said = spoken[position]
            context = " ".join(written[max(index - 3, 0) : index + 1])
            pause = spoken[position + 1].start - said.end
            # The transcriber's full stop alone is a guess; a stop the voice also paused on
            # is a sentence the listener heard end; most bare full stops were false alarms.
            if (
                said.text.strip().endswith((".", "?", "!"))
                and pause >= FRAGMENT_PAUSE
                and not mark.endswith((".", "?", "!", ":", ";"))
            ):
                issues.append(
                    f'{passage_id}: the voice stopped after "{context}" ({pause:.2f} s), where '
                    "the script runs on; the line probably reads as a fragment."
                )
            if pause >= MAX_UNMARKED_PAUSE and not mark.endswith(SENTENCE_OR_CLAUSE_END):
                issues.append(
                    f'{passage_id}: a {pause:.2f} s pause after "{context}", where the script '
                    "has no break."
                )
    return issues


def _joined(heard: Sequence[Word]) -> list[Word]:
    """Transcribers split hyphenated words ("son", "-in", "-law."); join them back."""
    joined: list[Word] = []
    for word in heard:
        if joined and word.text.strip().startswith("-"):
            last = joined[-1]
            joined[-1] = last.model_copy(
                update={"text": last.text.strip() + word.text.strip(), "end": word.end}
            )
        else:
            joined.append(word)
    return joined


def _normal(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", word.lower())
