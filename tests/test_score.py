import importlib.util
from pathlib import Path

import numpy as np
import pytest

from content.config import ContentConfig
from content.production.music_map import MusicMap, MusicSection, analyse_track
from content.production.score import (
    arranged_beats,
    arrangements,
    choose,
    fit,
    land,
    on_beat,
    render,
    turn_unit,
)
from content.providers import ffmpeg
from content.review.render import render_plan
from content.schemas.plan import EditorialBrief
from content.schemas.script import ScriptUnit
from content.schemas.story import NarrativeFunction, Transition
from content.workflow.demo import _brief_response
from content.workflow.gates import size_story

pytestmark = pytest.mark.skipif(not ffmpeg.available(), reason="ffmpeg is required")

# 120 BPM: beats every half second, two-second bars from half a second in.
MAP = MusicMap(
    beats=[0.5 + 0.5 * index for index in range(163)],
    downbeats=[0.5 + 2.0 * index for index in range(40)],
    duration=82.0,
    sections=[
        MusicSection(label="intro", start_bar=0, end_bar=8, energy=0.2),
        MusicSection(label="build", start_bar=8, end_bar=16, energy=0.5),
        MusicSection(label="peak", start_bar=16, end_bar=24, energy=1.0),
        MusicSection(label="outro", start_bar=24, end_bar=40, energy=0.4),
    ],
)
# The longest video a theme allows, in seconds.
LONGEST = 180.0


@pytest.mark.skipif(importlib.util.find_spec("beat_this") is None, reason="needs the music extra")
def test_the_map_finds_the_pulse(tmp_path: Path) -> None:
    track = tmp_path / "pulse.wav"
    ffmpeg.run(
        "-f", "lavfi", "-i",
        "aevalsrc='0.8*sin(2*PI*80*t)*exp(-25*mod(t,0.5))"
        "+0.4*sin(2*PI*60*t)*exp(-12*mod(t,2))+0.05*sin(2*PI*220*t)':d=40",
        track,
    )  # fmt: skip

    music = analyse_track(track)

    assert 60 / music.beat_seconds == pytest.approx(120, abs=2) or 60 / music.beat_seconds == (
        pytest.approx(60, abs=1)
    )
    assert len(music.downbeats) >= 8
    assert all(section.end_bar - section.start_bar <= 4 for section in music.sections)


def test_arrangements_only_drop_or_repeat_whole_phrases_and_keep_the_ending() -> None:
    options = {round(a.seconds, 1): a for a in arrangements(MAP, LONGEST)}

    as_written = options[82.0]
    assert as_written.phrases == [0, 1, 2, 3]
    assert as_written.peak_at == pytest.approx(0.5 + 16 * 2.0)
    shorter = options[round(82.0 - 16.0, 1)]
    assert shorter.phrases == [0, 2, 3]
    assert all(a.phrases[0] == 0 and a.phrases[-1] == 3 for a in options.values())
    assert max(options) > 82.0


def test_a_requested_length_picks_the_arrangement_that_holds_it() -> None:
    assert choose(MAP, 60, (1.0, 6.0), 180).seconds == pytest.approx(66.0)
    assert choose(MAP, 80, (1.0, 6.0), 180).seconds == pytest.approx(82.0)


def test_an_arrangement_renders_exactly_without_clicks(tmp_path: Path) -> None:
    track, output = tmp_path / "bed.wav", tmp_path / "arranged.wav"
    ffmpeg.run(
        "-f", "lavfi", "-i", "aevalsrc='0.3*sin(2*PI*110*t)*(1+0.5*sin(2*PI*0.5*t))':d=82",
        track,
    )  # fmt: skip
    longer = max(arrangements(MAP, LONGEST), key=lambda a: a.seconds)

    render(track, MAP, longer, output)

    assert ffmpeg.probe(output).duration == pytest.approx(longer.seconds, abs=0.03)
    samples = np.frombuffer(ffmpeg.decode(output, sample_rate=48000), np.float32)
    assert np.abs(np.diff(samples)).max() < 0.05


def test_lines_start_on_the_music_s_beats() -> None:
    beats = [0.25 + 0.5 * index for index in range(40)]
    gaps = on_beat([2.2, 3.1, 1.7], [0.1, 0.55], beats)

    starts = [2.2 + gaps[0], 2.2 + gaps[0] + 3.1 + gaps[1]]
    assert all(min(abs(start - beat) for beat in beats) < 1e-6 for start in starts)
    assert all(gap >= 0.05 for gap in gaps)


def test_beats_move_with_the_phrases_they_belong_to() -> None:
    shorter = min(arrangements(MAP, LONGEST), key=lambda a: a.seconds)

    beats = arranged_beats(MAP, shorter)

    assert shorter.peak_at in beats
    assert all(later > earlier for earlier, later in zip(beats, beats[1:], strict=False))


def test_the_turn_passage_lands_on_the_peak_only_when_close() -> None:
    durations, gaps = [3.0, 4.0, 5.0], [0.2, 0.2]

    landed = land(2, durations, gaps, target=8.0)
    far = land(2, durations, gaps, target=12.0)

    assert sum(durations[:2]) + sum(landed) == pytest.approx(8.0)
    assert far == gaps


def test_the_story_turns_on_the_first_reveal_else_the_first_turn() -> None:
    story = [_unit(1, "hook", "build"), _unit(2, "orient", "turn"), _unit(3, "reveal", "build")]

    assert turn_unit(story) == "U3"
    assert turn_unit(story[:2]) == "U2"


def test_the_shortest_edit_that_holds_the_spoken_narration_is_used() -> None:
    lengths = sorted(a.seconds for a in arrangements(MAP, LONGEST))

    holding, just_over = (
        fit(MAP, lengths[1] - 5, (1.0, 6.0), 180),
        fit(MAP, lengths[1] - 0.5, (1.0, 6.0), 180),
    )
    assert holding is not None and holding.seconds == lengths[1]
    assert just_over is not None and just_over.seconds == lengths[2]
    assert fit(MAP, lengths[-1], (1.0, 6.0), 180) is None


def test_no_edit_runs_past_the_platforms_limit() -> None:
    limit = sorted(a.seconds for a in arrangements(MAP, LONGEST))[-2]

    assert max(a.seconds for a in arrangements(MAP, limit)) == limit
    assert choose(MAP, 1000, (1.0, 6.0), limit).seconds == limit
    assert fit(MAP, limit, (1.0, 6.0), limit) is None


def _unit(index: int, function: NarrativeFunction, transition: Transition) -> ScriptUnit:
    return ScriptUnit(
        unit_id=f"U{index}",
        order=index,
        narrative_function=function,
        arc_phase_id="P1",
        transition_intent=transition,
        text="Words.",
        claim_ids=[],
    )


def test_a_plan_is_sized_from_its_beats_and_snapped_to_the_music(
    app_config: ContentConfig,
) -> None:
    theme = app_config.theme
    brief = EditorialBrief.model_validate(_brief_response("The Great Stink"))

    size, arrangement = size_story(brief, theme, MAP)
    unscored, _ = size_story(brief, theme, None)

    assert set(size.beat_seconds) == {phase.phase_id for phase in brief.arc}
    assert arrangement is not None
    middle = sum(theme.spec.music.outro_seconds) / 2
    assert size.target_seconds == pytest.approx(arrangement.seconds - middle, abs=0.1)
    # The nearest edit needs the fewest words changed; the others say how many.
    longest = theme.spec.format.max_seconds
    assert [seconds for seconds, _ in size.edits] == [a.seconds for a in arrangements(MAP, longest)]
    assert unscored.target_seconds == unscored.estimate_seconds
    page = "\n".join(render_plan(brief, size))
    assert "### Story Spine" in page and "**P2 · reveal** (but, told with logic, build" in page
    assert "### Left Out" in page and "the nearest, used as planned" in page
