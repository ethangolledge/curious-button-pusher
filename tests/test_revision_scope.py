"""A revision reaches only as far as its notes: a note on a line changes that line, code
keeps every other line exactly, and a person's own words stand through every rewrite."""

import json
from dataclasses import replace
from typing import Any, cast

from content.agents.editorial_director.agent import EditorialDirector
from content.agents.fact_researcher.agent import FactResearcher
from content.agents.script_writer.agent import ScriptWriter
from content.config import ContentConfig
from content.judging.questions import questions_for
from content.providers.fake import FakeModelProvider
from content.schemas.judgement import Answer, Judgement
from content.schemas.review import ReviewResponse
from content.schemas.script import LineEdit, LineEditPackage, ScriptPackage, ScriptUnit
from content.state import ContentState
from content.story.ledger import script_tasks, unjudged
from content.story.revision_scope import line_targets, locked_lines, unchanged_judgements
from content.workflow.demo import demo_response
from content.workflow.gates import check_script
from content.workflow.run import create_initial_state


def _units(count: int) -> list[ScriptUnit]:
    return [
        ScriptUnit(
            unit_id=f"U{n}",
            order=n,
            narrative_function="context",
            arc_phase_id="P1",
            transition_intent="hold",
            text=f"Line {n}.",
        )
        for n in range(1, count + 1)
    ]


def test_notes_that_name_their_lines_are_line_edits() -> None:
    units = _units(9)

    assert line_targets(["U3: plainer.", "U3->U4: join them."], units) == {"U3", "U4"}
    assert line_targets(["U2, U5 (exaggerated): soften."], units) == {"U2", "U5"}
    # A note on the whole, or a line that does not exist, is the whole script's.
    assert line_targets(["U3: plainer.", "End on a question."], units) is None
    assert line_targets(["U12: plainer."], units) is None
    # Too many lines for an edit, unless the person asked for lines.
    four = ["U1: a.", "U3: b.", "U5: c.", "U7: d."]
    assert line_targets(four, units) is None
    assert line_targets(four, units, scope="lines") == {"U1", "U3", "U5", "U7"}
    assert line_targets(["U3: plainer."], units, scope="script") is None
    # The person's own lines are never targets.
    assert line_targets(["U3: plainer.", "U4: shorter."], units, locked={"U4"}) == {"U3"}


def test_a_person_rewriting_their_own_line_replaces_it() -> None:
    def edit(before: str, after: str, author: Any = "person") -> LineEdit:
        return LineEdit(
            unit_id="U2", before=before, after=after, author=author, reason="", script_revision=1
        )

    edits = [edit("Old.", "Mine."), edit("Mine.", "Mine, again."), edit("X.", "Y.", "editor")]

    assert locked_lines(edits) == ["Mine, again."]


def test_a_line_edit_changes_only_its_lines(app_config: ContentConfig) -> None:
    provider = FakeModelProvider(
        {LineEditPackage: [{"lines": [{"unit_id": "U3", "text": "A plainer third line."}]}]},
        default_factory=demo_response,
    )
    state = _state_with_script(app_config, provider)
    before = state["script_package"]
    assert before is not None
    state["revision_notes"] = ["U3: say it plainly."]

    update = _writer(app_config, provider)(state)

    after = cast(ScriptPackage, update["script_package"])
    assert [unit.text for unit in after.script_units] == [
        "A plainer third line." if unit.unit_id == "U3" else unit.text
        for unit in before.script_units
    ]
    # Untouched lines are the same objects, byte for byte.
    for old, new in zip(before.script_units, after.script_units, strict=True):
        if old.unit_id != "U3":
            assert new is old
    (call,) = [c for c in provider.calls if c.output_type is LineEditPackage]
    asked = json.loads(call.input_text)
    assert [line["unit_id"] for line in asked["lines"]] == ["U3"]
    assert set(asked) == {"lines", "voice_direction"}
    assert [(e.unit_id, e.author) for e in update["line_edits"]] == [("U3", "writer")]


def test_the_persons_words_go_in_exactly_without_a_model(app_config: ContentConfig) -> None:
    provider = FakeModelProvider(default_factory=demo_response)
    state = _state_with_script(app_config, provider)
    calls = len(provider.calls)
    state["routing_decision"] = "human_revise"
    state["human_review_response"] = ReviewResponse(
        action="revise", edits={"U2": "  My own second line.  "}, decided_by="person"
    )

    update = _writer(app_config, provider)(state)

    script = cast(ScriptPackage, update["script_package"])
    assert script.script_units[1].text == "My own second line."
    assert len(provider.calls) == calls
    assert [(e.unit_id, e.author) for e in update["line_edits"]] == [("U2", "person")]


def test_a_failed_small_edit_goes_to_the_writers_own_model(app_config: ContentConfig) -> None:
    agent = replace(app_config.agents["script_writer"], edit_model_alias="accurate")
    config = replace(app_config, agents={**app_config.agents, "script_writer": agent})
    provider = FakeModelProvider(default_factory=demo_response)
    state = _state_with_script(config, provider)
    writer = _writer(config, provider)

    state["revision_notes"] = ["U3: say it plainly."]
    state.update(writer(state))
    state["revision_notes"] = ["U3: still not plain."]
    state.update(writer(state))

    models = [c.model.model for c in provider.calls if c.output_type is LineEditPackage]
    assert models == ["deterministic-accurate", config.models.get(agent.model_alias).model]


def test_a_rewrite_that_loses_the_persons_line_is_sent_back(app_config: ContentConfig) -> None:
    provider = FakeModelProvider(default_factory=demo_response)
    state = _state_with_script(app_config, provider)
    state["line_edits"] = [
        LineEdit(
            unit_id="U2",
            before="Old.",
            after="Words the writer dropped.",
            author="person",
            reason="",
            script_revision=1,
        )
    ]

    update = check_script(state, theme=app_config.theme, faithfulness=None)

    assert update["structural_blockers"]
    assert any("Words the writer dropped." in note for note in update["revision_notes"])


def test_lines_a_change_leaves_alone_keep_their_judgements(app_config: ContentConfig) -> None:
    provider = FakeModelProvider(default_factory=demo_response)
    state = _state_with_script(app_config, provider)
    script, brief, research = (
        state["script_package"],
        state["editorial_brief"],
        state["research_pack"],
    )
    assert script is not None and brief is not None and research is not None
    units = script.script_units
    tasks = script_tasks(script, brief, research, 0)
    passed = Answer(kind="noul", noul=0.95)
    judgements = [
        Judgement(
            stage="script",
            revision=0,
            target_id=task["target_id"],
            question_id=question,
            answer=passed,
            expected=None,
            outcome="pass",
            blocking=True,
            model="fake",
        )
        for task in tasks
        for question in _questions(task["target"])
    ]

    carried = unchanged_judgements(judgements, {units[3].unit_id}, units, 1)
    again = unjudged(script_tasks(script, brief, research, 1), carried)

    changed = units[3].unit_id
    assert {(task["target"], task["target_id"]) for task in again} == {
        ("unit", changed),
        ("transition", f"{units[2].unit_id}->{changed}"),
        ("transition", f"{changed}->{units[4].unit_id}"),
        ("script", "script"),
    }
    assert {judgement.revision for judgement in carried} == {1}


def _questions(target: str) -> list[str]:
    return [question.question_id for question in questions_for(cast(Any, target))]


def _state_with_script(config: ContentConfig, provider: FakeModelProvider) -> ContentState:
    state = cast(
        ContentState,
        create_initial_state("Topic", source_material=None, user_instructions=None, config=config),
    )
    editorial = EditorialDirector(**_args("editorial_director", config, provider))
    for operation in (
        FactResearcher(**_args("fact_researcher", config, provider)),
        editorial.create_plan,
        _writer(config, provider),
    ):
        state.update(operation(state))
    return state


def _writer(config: ContentConfig, provider: FakeModelProvider) -> ScriptWriter:
    return ScriptWriter(**_args("script_writer", config, provider))


def _args(name: str, config: ContentConfig, provider: FakeModelProvider) -> dict[str, Any]:
    return {
        "name": name,
        "config": config.agents[name],
        "models": config.models,
        "provider": provider,
    }
