"""Keep a whole run under its cost cap (`production.max_usd`).

Measured on real runs (docs/visuals.md): AI video on every scene cost $6.40 on its own;
keyframes cost about $0.045 each; the text stages $1.5–2.5. So every scene is a still, and AI video
is spent only on the morph from each still into the next. Each scene therefore costs a
keyframe and a morph, and what is left of the budget after the writing sets how many
scenes the story can have. The narration never changes to fit: scenes just hold longer.

The cost so far comes from the run's own call log. A call the provider did not price is
counted at the average for that kind of call across past runs.
"""

import json
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from content.schemas.media import Budget, SceneTiming, TransitionTiming
from content.state import CallRecord

# Keyframes drawn per scene, on average, counting redraws for tone, colour, and anchor
# (14 calls for 10 scenes, measured).
KEYFRAME_DRAWS_PER_SCENE = 1.5
# Takes per morph, on average, counting retries.
TRANSITION_TAKES = 1.3
# Perception and judging of each keyframe and morph.
MARGIN_PER_PICTURE = 0.01
# Research, plan, script, fact check and storyboard together, measured on real runs:
# what a run spends before any narration, picture or video is paid for.
WRITING_USD = (1.5, 2.5)
# One narration take, measured from the key's balance: the provider does not price it.
NARRATION_TAKE_USD = 0.09
# The storyboard, its revisions and critique, still to come when the allowance is set
# (about $0.2-0.35, measured).
STORYBOARD_USD = 0.3


@dataclass(frozen=True, slots=True)
class Pricing:
    cap: float
    image_usd: float
    video_usd_per_second: float
    # How long each generated morph runs.
    morph_seconds: float

    @property
    def keyframe(self) -> float:
        return KEYFRAME_DRAWS_PER_SCENE * self.image_usd + MARGIN_PER_PICTURE

    @property
    def morph(self) -> float:
        return (
            self.morph_seconds * self.video_usd_per_second * TRANSITION_TAKES + MARGIN_PER_PICTURE
        )


def past_averages(run_logs: Iterable[Path]) -> dict[str, float]:
    """The average priced cost of each kind of call across past runs."""
    costs: dict[str, list[float]] = {}
    for path in run_logs:
        for call in json.loads(path.read_text(encoding="utf-8")).get("calls", []):
            if call.get("cost_usd") is not None:
                costs.setdefault(call["operation"], []).append(float(call["cost_usd"]))
    return {operation: statistics.fmean(values) for operation, values in costs.items()}


def spent(calls: Sequence[CallRecord], averages: dict[str, float]) -> float:
    return sum(
        call["cost_usd"] if call["cost_usd"] is not None else averages.get(call["operation"], 0.0)
        for call in calls
    )


def scene_allowance(already_spent: float, pricing: Pricing) -> int:
    """How many scenes the rest of the budget pays for: a keyframe each, and a morph
    between each pair (one fewer morph than scenes)."""
    left = pricing.cap - already_spent - STORYBOARD_USD
    per_scene = pricing.keyframe + pricing.morph
    return max(int((left + pricing.morph) // per_scene), 0)


def project(scenes: int, already_spent: float, pricing: Pricing) -> Budget:
    """The whole run's projected cost once the narration is timed."""
    morphs = max(scenes - 1, 0)
    return Budget(
        cap=pricing.cap,
        spent=round(already_spent, 2),
        keyframes=round(scenes * pricing.keyframe, 2),
        morphs=morphs,
        transitions=round(morphs * pricing.morph, 2),
    )


def morph_timings(scenes: Sequence[SceneTiming], seconds: float) -> list[TransitionTiming]:
    """A morph across every join between scenes. It takes up to half a morph from each
    side, but never more than a third of a scene, so every keyframe is still seen held;
    a shorter morph is the generated one played faster."""
    lengths = [scene.end - scene.start for scene in scenes]
    transitions = []
    for index, (before, after) in enumerate(zip(scenes, scenes[1:], strict=False)):
        taken = min(seconds / 2, lengths[index] / 3)
        given = min(seconds / 2, lengths[index + 1] / 3)
        transitions.append(
            TransitionTiming(
                from_scene_id=before.scene_id,
                to_scene_id=after.scene_id,
                start=round(after.start - taken, 3),
                seconds=round(taken + given, 3),
            )
        )
    return transitions


# Before a run: what a video of a given length and scene count costs

# The story the writing costs were measured on: about this many seconds of narration.
MEASURED_STORY_SECONDS = 165
# Seconds of narration per beat (a passage, one take): four to seven beats in a short.
PASSAGE_SECONDS = 35
# How long each picture holds, for the scene counts offered: a picture every 5 seconds
# (busy) to every 30 (a long-form talking stretch).
HOLD_OPTIONS = (5, 8, 12, 20, 30)
# The hold recommended by default: about one picture per beat in a short, longer holds
# where a long narration would otherwise need hundreds of pictures.
SHORT_HOLD, LONG_HOLD = 12, 20
SHORT_MAX_SECONDS = 180


@dataclass(frozen=True, slots=True)
class VideoEstimate:
    seconds: int
    scenes: int
    writing: tuple[float, float]
    narration: float
    pictures: float
    morphs: float

    @property
    def hold_seconds(self) -> float:
        return self.seconds / self.scenes

    @property
    def total(self) -> tuple[float, float]:
        rest = self.narration + self.pictures + self.morphs
        return self.writing[0] + rest, self.writing[1] + rest


def writing_usd(seconds: float) -> tuple[float, float]:
    """Research to storyboard. Measured on short stories; a longer one is scaled by its
    length (an estimate: long form is not yet measured)."""
    scale = max(seconds / MEASURED_STORY_SECONDS, 1.0)
    return WRITING_USD[0] * scale, WRITING_USD[1] * scale


def estimate_video(
    seconds: int, scenes: int, pricing: Pricing, *, expected_takes: float
) -> VideoEstimate:
    passages = max(4, round(seconds / PASSAGE_SECONDS))
    return VideoEstimate(
        seconds=seconds,
        scenes=scenes,
        writing=writing_usd(seconds),
        narration=passages * expected_takes * NARRATION_TAKE_USD,
        pictures=scenes * pricing.keyframe,
        morphs=max(scenes - 1, 0) * pricing.morph,
    )


def scene_options(seconds: int) -> list[int]:
    """Scene counts worth offering for a narration this long, most first."""
    return sorted({max(2, round(seconds / hold)) for hold in HOLD_OPTIONS}, reverse=True)


def recommended_scenes(seconds: int) -> int:
    hold = SHORT_HOLD if seconds <= SHORT_MAX_SECONDS else LONG_HOLD
    return max(2, round(seconds / hold))
