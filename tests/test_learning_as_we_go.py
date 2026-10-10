import json
from pathlib import Path
from typing import Any, cast

from content.config import ContentConfig
from content.learning.examples import LearningStore, harvest, jev_label, verdict_labels
from content.providers.fake import FakeDecisionProvider, FakeModelProvider
from content.state import ContentOutput
from content.workflow.demo import demo_answer, demo_response
from content.workflow.graph import build_graph
from content.workflow.records import write_trace
from content.workflow.run import create_initial_state

PERSON_APPROVES_SCRIPT = {
    "stage": "script",
    "revision": 0,
    "action": "approve",
    "decided_by": "person",
}


def test_approving_a_stage_confirms_jevs_passing_answers(
    app_config: ContentConfig, tmp_path: Path
) -> None:
    trace = _trace(app_config, tmp_path)
    failed = next(j for j in trace["judgements"] if j["question_id"] == "unit_pace")
    failed["outcome"] = "fail"
    trace["human_decisions"] = [PERSON_APPROVES_SCRIPT]

    found = harvest(trace)

    examples = {e.example_id: e for e in found.examples}
    reviewed = [label for label in found.labels if label.source == "review"]
    assert reviewed
    # Each confirms Jev's own answer on the approved script.
    assert all(label.answer == jev_label(examples[label.example_id].jev) for label in reviewed)
    # Measurements are never confirmed; a failed answer you approved is flagged instead.
    assert not {label.question_id for label in reviewed} & {"unit_reaction", "unit_intensity"}
    (flag,) = found.flags
    assert flag.question_id == "unit_pace" and flag.note.startswith("You approved this")


def test_story_sheet_notes_become_labels_or_flags(
    app_config: ContentConfig, tmp_path: Path
) -> None:
    trace = _trace(app_config, tmp_path)
    storyboard = next(c for c in trace["calls"] if c["operation"] == "storyboard")["output"]
    storyboard["scenes"][2]["script_unit_ids"] = ["U3", "U4"]
    trace["human_decisions"] = [
        {
            "stage": "storyboard",
            "revision": 0,
            "action": "revise",
            "feedback": "S1: feel brace S3: feel settle U5: this drags S6: wrong room",
            "script_revision": 0,
            "decided_by": "person",
        }
    ]

    found = harvest(trace)

    examples = {e.example_id: e for e in found.examples}
    (label,) = [label for label in found.labels if label.source != "outcome"]
    assert (label.question_id, label.answer, label.source) == ("unit_reaction", "brace", "human")
    assert examples[label.example_id].state["unit"]["text"]
    flagged = {(examples[f.example_id].question_id, f.note) for f in found.flags}
    # A feel note on a scene of two units cannot say which unit it meant.
    assert ("unit_reaction", "S3: feel settle") in flagged
    assert ("unit_pace", "U5: this drags") in flagged
    assert any(note == "S6: wrong room" for _, note in flagged)


def test_our_own_models_answers_are_never_taken_for_jevs(
    app_config: ContentConfig, tmp_path: Path
) -> None:
    trace = _trace(app_config, tmp_path)
    for judgement in trace["judgements"]:
        if judgement["question_id"] == "unit_pace":
            judgement["model"] = "local:words"

    found = harvest(trace)

    assert found.examples
    assert not any(e.question_id == "unit_pace" for e in found.examples)


def test_harvesting_twice_adds_nothing_new(app_config: ContentConfig, tmp_path: Path) -> None:
    trace = _trace(app_config, tmp_path)
    trace["human_decisions"] = [PERSON_APPROVES_SCRIPT]
    store = LearningStore(tmp_path / "learning")

    first = store.add(harvest(trace))
    second = store.add(harvest(trace))

    assert first.examples and first.labels
    assert (second.examples, second.labels, second.flags) == ([], [], [])


def _trace(config: ContentConfig, tmp_path: Path) -> dict[str, Any]:
    graph = build_graph(
        config=config,
        providers={"fake": FakeModelProvider(default_factory=demo_response)},
        decision_provider=FakeDecisionProvider(demo_answer),
    )
    state = cast(
        ContentOutput,
        graph.invoke(
            create_initial_state(
                "Traced", source_material=None, user_instructions=None, config=config
            )
        ),
    )
    trace: dict[str, Any] = json.loads(
        write_trace(state, tmp_path / "run").read_text(encoding="utf-8")
    )
    return trace


def test_only_a_persons_decisions_teach(app_config: ContentConfig, tmp_path: Path) -> None:
    trace = _trace(app_config, tmp_path)
    approval = {"stage": "script", "revision": 0, "action": "approve"}
    trace["human_decisions"] = [{**approval, "decided_by": "assistant"}, approval]

    found = harvest(trace)

    assert not any(label.source == "review" for label in found.labels)
    assert found.flags == []


def test_a_persons_verdict_labels_the_finished_script_and_can_exclude_the_run(
    app_config: ContentConfig, tmp_path: Path
) -> None:
    trace = _trace(app_config, tmp_path)

    labels = verdict_labels(trace, "list", "flat", "Robotic, facts thrown at you.")

    assert {(label.question_id, label.answer, label.source) for label in labels} == {
        ("script_story", "no", "human"),
        ("script_voice", "flat", "human"),
    }
    trace["human_decisions"] = [PERSON_APPROVES_SCRIPT]
    trace["training"] = "exclude"
    assert not any(label.source == "review" for label in harvest(trace).labels)
