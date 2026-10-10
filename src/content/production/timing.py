"""The narration is the clock: spoken passages set unit windows, and unit windows set
scene windows. A scene may run as long as its narration needs."""

from collections.abc import Sequence

from content.production.subtitles import align
from content.schemas.media import NarrationClip, SceneTiming, Word
from content.schemas.visuals import Scene


def passage_starts(
    clips: Sequence[NarrationClip], gaps: Sequence[float], lead: float
) -> list[float]:
    """Where each passage starts on the final timeline: after the lead-in, each passage
    follows the last with its breath."""
    starts = []
    cursor = lead
    for clip, gap in zip(clips, [*gaps, 0.0], strict=True):
        starts.append(cursor)
        cursor += clip.duration + gap
    return starts


def lay_out(
    clips: Sequence[NarrationClip], starts: Sequence[float], texts: dict[str, str]
) -> tuple[dict[str, tuple[float, float]], list[Word]]:
    """Every script word timed on the final timeline from the words the voice actually
    spoke, and each unit's window: from its first word to its last (a passage's first
    unit from the passage start, its last to the passage end)."""
    windows: dict[str, tuple[float, float]] = {}
    timed: list[Word] = []
    for clip, start in zip(clips, starts, strict=True):
        words = align(
            " ".join(texts[unit_id] for unit_id in clip.unit_ids),
            clip.heard,
            start,
            start + clip.duration,
        )
        cursor = 0
        for index, unit_id in enumerate(clip.unit_ids):
            count = len(texts[unit_id].split())
            mine = words[cursor : cursor + count]
            cursor += count
            begin = start if index == 0 else mine[0].start
            end = start + clip.duration if index == len(clip.unit_ids) - 1 else mine[-1].end
            windows[unit_id] = (round(begin, 3), round(end, 3))
        timed += words
    return windows, timed


def scene_timings(
    scenes: Sequence[Scene], windows: dict[str, tuple[float, float]], total_seconds: float
) -> list[SceneTiming]:
    """Each scene runs from its first unit's speech to the next scene's; the first starts
    at zero and the last runs to the end."""
    starts = [0.0, *(windows[scene.script_unit_ids[0]][0] for scene in scenes[1:])]
    ends = [*starts[1:], total_seconds]
    return [
        SceneTiming(scene_id=scene.scene_id, start=round(start, 3), end=round(end, 3))
        for scene, start, end in zip(scenes, starts, ends, strict=True)
    ]
