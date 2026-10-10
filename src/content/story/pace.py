"""Narration timing, known before any audio exists.

Every spoken passage is brought towards the voice's target rate (see `VoiceSpec`), no
further than its stretch limit allows. A narration is sized at `VoiceSpec.rate`: the pace
this voice actually delivers, measured from its recorded takes (the target until enough are
measured); the hook runs a little slower. The voice model's own speed varies widely from
take to take (measurements: docs/narration.md).
"""

import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import NamedTuple

import textstat

from content.schemas.script import ScriptUnit
from content.schemas.story import Transition
from content.theme import VoiceSpec


def syllables(text: str) -> int:
    return int(textstat.syllable_count(text))


def spoken_seconds(words: int, voice: VoiceSpec, *, hook: bool = False) -> float:
    """How long `words` take at the voice's rate (the hook's, for the first passage)."""
    return 60 * words / (voice.rate * (voice.hook_pace if hook else 1.0))


class Passage(NamedTuple):
    """Consecutive units of one arc phase, spoken in one take so the voice carries its
    own phrasing from sentence to sentence."""

    passage_id: str
    # (unit ID, the unit's text as the voice will say it), in order.
    units: tuple[tuple[str, str], ...]
    # How the passage enters from the one before; sets the breath before it.
    transition: Transition

    @property
    def text(self) -> str:
        return " ".join(text for _, text in self.units)

    @property
    def unit_ids(self) -> list[str]:
        return [unit_id for unit_id, _ in self.units]


def passages(
    units: Sequence[ScriptUnit], spoken: Callable[[str], str] = lambda text: text
) -> list[Passage]:
    """Group consecutive units that share an arc phase. A phase that recurs later gets a
    numbered passage ID (P2, then P2.2)."""
    groups: list[list[ScriptUnit]] = []
    for unit in units:
        if groups and groups[-1][0].arc_phase_id == unit.arc_phase_id:
            groups[-1].append(unit)
        else:
            groups.append([unit])
    seen: dict[str, int] = {}
    result = []
    for group in groups:
        phase = group[0].arc_phase_id
        seen[phase] = seen.get(phase, 0) + 1
        result.append(
            Passage(
                passage_id=phase if seen[phase] == 1 else f"{phase}.{seen[phase]}",
                units=tuple((unit.unit_id, spoken(unit.text)) for unit in group),
                transition=group[0].transition_intent,
            )
        )
    return result


@dataclass(frozen=True, slots=True)
class NarrationEstimate:
    total_seconds: float
    passage_seconds: dict[str, float]
    # Each passage's time shared among its units by words.
    unit_seconds: dict[str, float]


def gaps(transitions: Sequence[Transition], voice: VoiceSpec) -> list[float]:
    """The breath between consecutive passages, from how each one enters."""
    return [voice.pauses[transition] for transition in transitions[1:]]


def estimate(spoken: Sequence[Passage], voice: VoiceSpec) -> NarrationEstimate:
    """The whole narration: each passage at the target rate, with a breath between
    passages and the closing tail."""
    per_passage = {
        passage.passage_id: spoken_seconds(len(passage.text.split()), voice, hook=index == 0)
        for index, passage in enumerate(spoken)
    }
    per_unit = {}
    for passage in spoken:
        counts = [len(text.split()) for _, text in passage.units]
        for (unit_id, _), count in zip(passage.units, counts, strict=True):
            per_unit[unit_id] = per_passage[passage.passage_id] * count / max(sum(counts), 1)
    between = gaps([passage.transition for passage in spoken], voice)
    return NarrationEstimate(
        total_seconds=sum(per_passage.values()) + sum(between) + voice.tail_seconds,
        passage_seconds=per_passage,
        unit_seconds=per_unit,
    )


def length_issues(
    prediction: NarrationEstimate, target: float, longest: float, voice: VoiceSpec
) -> list[str]:
    """Narration past the longest the video allows, or a gross miss of the planned length;
    inside the tolerance, the music is fitted to whatever the narrator actually takes."""
    total = prediction.total_seconds
    biggest = sorted(prediction.passage_seconds.items(), key=lambda item: -item[1])[:2]
    where = (
        "ideally a beat that serves the story least, not the connecting words that make it "
        "flow. Longest passages: "
        + ", ".join(f"{passage_id} {seconds:.0f} s" for passage_id, seconds in biggest)
        + "."
    )
    if total > longest:
        cut = max(round((total - longest) * voice.rate / 60), 1)
        return [
            f"The narration is predicted to run {total:.0f} s, past the {longest:.0f} s the "
            f"longest video allows: cut at least {cut} words, {where}"
        ]
    low, high = target * (1 - voice.length_tolerance), target * (1 + voice.length_tolerance)
    if low <= total <= high:
        return []
    change_words = max(round(abs(total - target) * voice.rate / 60), 1)
    if total > high:
        return [
            f"The narration is predicted to run {total:.0f} s against a planned {target:.0f} s: "
            f"cut roughly {change_words} words, {where}"
        ]
    return [
        f"The narration is predicted to run {total:.0f} s against a planned {target:.0f} s: "
        f"add roughly {change_words} words of context or consequence the evidence supports."
    ]


def planned_seconds(beat_words: Sequence[int], voice: VoiceSpec) -> list[float]:
    """Each beat's spoken seconds from its planned words, as one passage at the target
    rate; the breaths and the tail come on top."""
    return [spoken_seconds(words, voice, hook=index == 0) for index, words in enumerate(beat_words)]


def story_seconds(beat_seconds: Sequence[float], voice: VoiceSpec) -> float:
    """The whole narration: beats, a typical breath between them, and the tail."""
    typical_pause = statistics.fmean(voice.pauses.values())
    return sum(beat_seconds) + typical_pause * max(len(beat_seconds) - 1, 0) + voice.tail_seconds


def words_per_second(voice: VoiceSpec) -> float:
    return voice.rate / 60


def word_budget(target_seconds: float, voice: VoiceSpec, *, passage_count: int = 5) -> int:
    """Roughly how many words fill the planned length, for the writer."""
    typical_pause = statistics.fmean(voice.pauses.values())
    speaking = target_seconds - voice.tail_seconds - typical_pause * (passage_count - 1)
    return max(int(speaking * words_per_second(voice)), 0)
