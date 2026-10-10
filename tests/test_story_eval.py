from pathlib import Path

from content.schemas.script import ScriptUnit
from content.story.regression import ExpectedFailure, Flag, StoryFixture, load_fixtures, score

EXAMPLES = Path(__file__).parents[1] / "themes/starter/examples"


def test_every_story_fixture_loads_and_names_real_lines() -> None:
    fixtures = load_fixtures(EXAMPLES)

    assert fixtures
    for fixture in fixtures:
        unit_ids = {unit.unit_id for unit in fixture.units}
        assert {expected.unit_id for expected in fixture.expected} <= unit_ids
        assert fixture.kind == "positive" or fixture.expected


def test_a_failure_is_caught_only_by_a_flag_on_its_own_line() -> None:
    fixture = StoryFixture(
        name="Synthetic",
        kind="negative",
        audience="Anyone",
        central_question="Why?",
        units=[_unit("U1", "The route began early."), _unit("U2", "No recusal rule exists.")],
        expected=[
            ExpectedFailure(pattern="unexplained reference", unit_id="U1", note=""),
            ExpectedFailure(pattern="untranslated term", unit_id="U2", note=""),
        ],
    )
    raised = [
        Flag("U1", "listener: confusion", "The route began"),
        Flag(None, "listener: lost_thread", "early"),
    ]

    result = score(fixture, raised)

    assert [(expected.unit_id, checks) for expected, checks in result.caught] == [
        ("U1", ["listener: confusion"]),
        ("U2", []),
    ]
    assert result.unexpected == [Flag(None, "listener: lost_thread", "early")]


def _unit(unit_id: str, text: str) -> ScriptUnit:
    return ScriptUnit(
        unit_id=unit_id,
        order=int(unit_id[1:]),
        narrative_function="context",
        arc_phase_id="P1",
        transition_intent="build",
        text=text,
    )
