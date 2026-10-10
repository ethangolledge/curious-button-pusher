from pathlib import Path

import pytest

from content.production.narration_analysis import analyse
from content.schemas.media import Word
from content.schemas.script import ScriptUnit
from content.schemas.story import NarrativeFunction, Transition
from content.story.pace import estimate, length_issues, passages, word_budget
from content.theme import load_theme, measure_voice

# Pinned, so the theme's chosen rate can change without changing what these check.
VOICE = load_theme(Path(__file__).parents[1] / "themes/starter").spec.voice.model_copy(
    update={"words_per_minute": 150, "hook_pace": 0.9, "length_tolerance": 0.15}
)


def test_consecutive_units_of_a_phase_are_one_passage() -> None:
    script = [
        _unit(1, "P1", "build", "A hook."),
        _unit(2, "P1", "build", "Who it is."),
        _unit(3, "P2", "turn", "The turn."),
        _unit(4, "P1", "release", "Back again."),
    ]

    spoken = passages(script)

    assert [(p.passage_id, p.unit_ids) for p in spoken] == [
        ("P1", ["U1", "U2"]),
        ("P2", ["U3"]),
        ("P1.2", ["U4"]),
    ]
    assert spoken[0].text == "A hook. Who it is."
    assert spoken[1].transition == "turn"


def test_narration_length_is_predicted_a_passage_at_a_time() -> None:
    script = [
        _unit(1, "P1", "build", "The river stank badly."),
        _unit(2, "P1", "build", "For six weeks, Parliament sat behind soaked curtains."),
        _unit(3, "P2", "turn", "Nobody noticed."),
    ]
    spoken = passages(script)

    prediction = estimate(spoken, VOICE)

    # Words at the target rate; the hook's passage a little slower.
    first = 60 * 12 / (150 * 0.9)
    second = 60 * 2 / 150
    assert prediction.passage_seconds == pytest.approx({"P1": first, "P2": second})
    assert prediction.total_seconds == pytest.approx(
        first + second + VOICE.pauses["turn"] + VOICE.tail_seconds
    )
    # A passage's time is shared among its units by words.
    assert prediction.unit_seconds["U1"] + prediction.unit_seconds["U2"] == pytest.approx(first)
    assert prediction.unit_seconds["U1"] < prediction.unit_seconds["U2"]


def test_only_a_gross_miss_of_the_planned_length_goes_back() -> None:
    line = "The city poured its waste into the river. "
    near = estimate(passages([_unit(1, "P1", "build", line * 5)]), VOICE)

    roomy = near.total_seconds * 2
    assert length_issues(near, near.total_seconds * 1.1, roomy, VOICE) == []
    (long,) = length_issues(near, near.total_seconds / 1.3, roomy, VOICE)
    assert "cut roughly" in long and "Longest passages: P1" in long
    (short,) = length_issues(near, near.total_seconds * 1.3, roomy, VOICE)
    assert "add roughly" in short


def test_narration_past_the_longest_video_is_reported_even_near_its_target() -> None:
    # A real run: 171 s was within 15% of the planned 152 s, but past the 167 s the
    # longest allowed video holds, so the writer was never told.
    line = "The city poured its waste into the river. "
    near = estimate(passages([_unit(1, "P1", "build", line * 5)]), VOICE)
    longest = near.total_seconds - 3

    (issue,) = length_issues(near, near.total_seconds * 0.95, longest, VOICE)

    assert f"past the {longest:.0f} s the longest video allows" in issue
    assert "cut at least 8 words" in issue


def test_word_budget_fills_the_planned_length() -> None:
    breaths = 4 * sum(VOICE.pauses.values()) / len(VOICE.pauses)
    assert word_budget(75, VOICE) == int((75 - VOICE.tail_seconds - breaths) * 150 / 60)


def test_a_reference_narration_is_reduced_to_rhythm_guidance() -> None:
    words = []
    clock = 0.0
    for sentence in ["The river carried the sewage past the Parliament.", "Who would act?"] * 6:
        for word in sentence.split():
            words.append(Word(text=word, start=clock, end=clock + 0.3))
            clock += 0.35
        clock += 0.5

    profile = analyse(words)

    assert profile.words == 66
    assert 130 <= profile.words_per_minute <= 145
    assert profile.sentence_words_mean == 5.5
    assert profile.sentence_words_spread == 2.5
    assert profile.short_share == 0.5
    assert profile.question_share == 0.5
    assert profile.pause_median == pytest.approx(0.55, abs=0.01)


def _unit(index: int, phase: str, transition: Transition, text: str) -> ScriptUnit:
    function: NarrativeFunction = "hook" if index == 1 else "context"
    return ScriptUnit(
        unit_id=f"U{index}",
        order=index,
        narrative_function=function,
        arc_phase_id=phase,
        transition_intent=transition,
        text=text,
        claim_ids=["C1"],
    )


def test_a_script_is_sized_at_the_pace_the_voice_delivers() -> None:
    voice = VOICE.model_copy(update={"tempo_range": (0.9, 1.2), "retakes": 2})
    assert measure_voice(voice, [100.0] * 7) is None  # too few takes to trust

    # Takes at 100 wpm reach only 120 within the 1.2 stretch; fast ones reach the target.
    natural = [100.0] * 5 + [140.0] * 4 + [80.0]
    measured = measure_voice(voice, natural)
    assert measured is not None
    assert measured.delivered == 120.0
    # 80 wpm reaches 96, short of 120 by more than the 15% tolerance: one take in ten.
    assert measured.short == 0.1
    sized = voice.model_copy(update={"measured": measured})

    assert sized.rate == 120.0
    assert sized.expected_takes == pytest.approx(1 + 0.1 + 0.01)
    assert word_budget(60, sized) < word_budget(60, voice)
    assert voice.expected_takes == 3  # unmeasured: every allowed take
