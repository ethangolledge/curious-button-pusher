"""The locked music bed, mapped once: where every beat and every bar starts, and the
track's phrases.

Beats and bar starts (downbeats) come from Beat This! (CPJKU, ISMIR 2024), a transformer
trained on thousands of annotated songs; it runs on a CPU in seconds. Phrases are groups of
whole bars, named by how loud they are. The map is saved as readable JSON beside the track
and can be corrected by hand; nothing is regenerated.
"""

import re
import statistics
from pathlib import Path

from content.production import ffmpeg
from content.schemas.base import ImmutableModel
from content.schemas.media import SectionLabel

# Bars per phrase: four bars of the model's pulse, the length music is usually built in.
PHRASE_BARS = 4
SAMPLE_RATE = 22050
SHORT_TERM = re.compile(r"lavfi\.r128\.S=(-?[\d.]+)")


class MusicSection(ImmutableModel):
    """One phrase of whole bars; `end_bar` is exclusive (indices into `downbeats`)."""

    label: SectionLabel
    start_bar: int
    end_bar: int
    # Loudness relative to the rest of the track: 0 the quietest phrase, 1 the loudest.
    energy: float


class MusicMap(ImmutableModel):
    beats: list[float]
    downbeats: list[float]
    duration: float
    sections: list[MusicSection]

    @property
    def beat_seconds(self) -> float:
        return statistics.median(b - a for a, b in zip(self.beats, self.beats[1:], strict=False))

    def bar_time(self, bar: int) -> float:
        """When bar `bar` starts; the bar after the last starts where the track ends."""
        return self.downbeats[bar] if bar < len(self.downbeats) else self.duration


def analyse_track(track: Path) -> MusicMap:
    """Requires the `music` extra (Beat This! on PyTorch). Used only when locking a track."""
    try:
        import numpy as np
        from beat_this.inference import Audio2Beats
    except ImportError as exc:
        raise RuntimeError("Mapping a track requires: pip install -e '.[music]'") from exc
    samples = np.frombuffer(ffmpeg.decode(track, sample_rate=SAMPLE_RATE), np.float32).copy()
    beats, downbeats = Audio2Beats(checkpoint_path="final0", device="cpu", dbn=False)(
        samples, SAMPLE_RATE
    )
    duration = ffmpeg.probe(track).duration
    bars = [round(float(time), 3) for time in downbeats]
    return MusicMap(
        beats=[round(float(time), 3) for time in beats],
        downbeats=bars,
        duration=round(duration, 3),
        sections=_phrases(bars, _loudness(track), duration),
    )


def save_map(music: MusicMap, path: Path) -> None:
    path.write_text(music.model_dump_json(indent=2) + "\n", encoding="utf-8")


def load_map(path: Path) -> MusicMap:
    return MusicMap.model_validate_json(path.read_text(encoding="utf-8"))


def map_for(track: Path | None) -> MusicMap | None:
    """A locked bed's map, saved beside it; None when there is no bed or it is unmapped."""
    if track is None or not track.with_suffix(".map.json").is_file():
        return None
    return load_map(track.with_suffix(".map.json"))


def _loudness(track: Path) -> list[float]:
    """Loudness every 100 ms (EBU R128 short-term)."""
    report = ffmpeg.run(
        "-i", track, "-af", "ebur128=metadata=1,ametadata=print:key=lavfi.r128.S",
        "-f", "null", "-",
    )  # fmt: skip
    return [float(value) for value in SHORT_TERM.findall(report)]


def _phrases(bars: list[float], loudness: list[float], duration: float) -> list[MusicSection]:
    """Whole phrases from the first bar, named by position and loudness: the first is the
    intro, the loudest the peak, those before it build, those after it the outro."""
    edges = [*bars, duration]
    starts = list(range(0, len(bars), PHRASE_BARS))
    levels = []
    for start in starts:
        begin, end = edges[start], edges[min(start + PHRASE_BARS, len(bars))]
        window = loudness[int(begin * 10) : int(end * 10)] or [-70.0]
        levels.append(statistics.fmean(window))
    low, high = min(levels), max(levels)
    peak = levels.index(high)
    sections = []
    for index, start in enumerate(starts):
        label: SectionLabel = (
            "intro"
            if index == 0
            else "peak"
            if index == peak
            else "build"
            if index < peak
            else "outro"
        )
        sections.append(
            MusicSection(
                label=label,
                start_bar=start,
                end_bar=min(start + PHRASE_BARS, len(bars)),
                energy=round((levels[index] - low) / (high - low), 3) if high > low else 1.0,
            )
        )
    return sections
