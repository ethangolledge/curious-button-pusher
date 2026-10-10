import json
from collections.abc import Sequence
from typing import Any

from content.schemas.fact_check import FactCheckReport
from content.schemas.plan import ClaimPlan, EditorialBrief
from content.schemas.research import ResearchPack
from content.schemas.script import ScriptPackage, ScriptUnit
from content.schemas.visuals import VisualPackage
from content.story.faithfulness import contradiction_issues
from content.story.ledger import (
    fact_check_issues,
    opening_issues,
    script_issues,
    script_tasks,
    visual_issues,
    visual_tasks,
)
from content.workflow.demo import demo_response

CAMERA_MOVES = ("push_in", "pull_out", "drift", "dolly")


def test_demo_story_is_structurally_sound() -> None:
    research, brief, script = _demo(ResearchPack), _demo(EditorialBrief), _demo(ScriptPackage)

    assert script_issues(script, brief, research) == []
    assert fact_check_issues(_demo(FactCheckReport), script, research) == []
    assert visual_issues(_demo(VisualPackage), script, CAMERA_MOVES) == []


def test_script_issues_catch_broken_links() -> None:
    research, brief, script = _demo(ResearchPack), _demo(EditorialBrief), _demo(ScriptPackage)
    units = [unit.model_dump() for unit in script.script_units]
    units[1] |= {"claim_ids": ["C9"], "arc_phase_id": "P9"}
    units[2] |= {"claim_ids": []}
    units[3] |= {"claim_ids": [], "text": "word " * 100}
    for unit in [units[0], *units[4:]]:
        unit["claim_ids"] = []
    broken = script.model_copy(
        update={"script_units": [ScriptUnit.model_validate(unit) for unit in units]}
    )
    expendable = ClaimPlan(
        claim_id="C9",
        story_role="expendable",
        narrative_job="Not this story.",
        meaning="",
        requires_explanation=False,
    )
    brief = brief.model_copy(update={"claims": [*brief.claims, expendable]})

    assert script_issues(broken, brief, research) == [
        "Script cites unknown research claims: C9.",
        "Script omits required research claims: C1.",
        "Script uses excluded research claims: C9.",
        "Units not linked to a creative-plan phase: U2. Use one of: P1, P2, P3.",
    ]


def test_every_story_node_and_connection_becomes_one_focused_task() -> None:
    research, brief, script = _demo(ResearchPack), _demo(EditorialBrief), _demo(ScriptPackage)

    tasks = script_tasks(script, brief, research, revision=2)

    assert [(task["target"], task["target_id"]) for task in tasks] == [
        ("opening", "U1"),
        ("unit", "U1"),
        ("unit", "U2"),
        ("unit", "U3"),
        ("unit", "U4"),
        ("unit", "U5"),
        ("unit", "U6"),
        ("transition", "U1->U2"),
        ("transition", "U2->U3"),
        ("transition", "U3->U4"),
        ("transition", "U4->U5"),
        ("transition", "U5->U6"),
        ("script", "script"),
    ]
    assert {task["revision"] for task in tasks} == {2}
    transition = tasks[8]
    assert transition["expected"] == "turn"
    assert set(transition["state"]) == {"audience", "previous_unit", "unit", "why_next"}
    # Inside one beat there is no new reason to give; between beats, the plan says why
    # the story moves on.
    assert transition["state"]["why_next"] == ""
    assert tasks[7]["state"]["why_next"] == brief.arc[0].leads_to_next

    visual = visual_tasks(_demo(VisualPackage), script, revision=0)
    assert [(task["target"], task["target_id"]) for task in visual] == [
        ("scene", "S1"),
        ("scene", "S2"),
        ("scene", "S3"),
        ("scene", "S4"),
        ("scene", "S5"),
        ("scene", "S6"),
        ("bridge", "S1->S2"),
        ("bridge", "S2->S3"),
        ("bridge", "S3->S4"),
        ("bridge", "S4->S5"),
        ("bridge", "S5->S6"),
        ("visual_sequence", "visuals"),
    ]
    assert visual[0]["state"]["narration"].startswith("One source says it happened")
    assert visual[6]["state"]["morph_bridge"] == "the card's ruled lines"


def test_scenes_must_partition_the_narration_in_order_with_theme_moves() -> None:
    script, storyboard = _demo(ScriptPackage), _demo(VisualPackage)
    scenes = storyboard.scenes
    swapped = storyboard.model_copy(
        update={
            "scenes": [
                scenes[1],
                scenes[0].model_copy(update={"camera": "crash_zoom"}),
                *scenes[2:],
            ]
        }
    )
    missing = storyboard.model_copy(update={"scenes": scenes[:-1]})

    assert visual_issues(swapped, script, CAMERA_MOVES) == [
        "Scenes must cover the script units once each, in narration order: U1, U2, U3, U4, U5, U6.",
        "S2 must open on the hook: start with U1.",
        "Unknown camera moves: crash_zoom. Use one of: dolly, drift, pull_out, push_in.",
    ]
    assert visual_issues(missing, script, CAMERA_MOVES) == ["No scene covers script units: U6."]


def _demo(output_type: type[Any]) -> Any:
    return output_type.model_validate(demo_response(json.dumps({"topic": "x"}), output_type))


def test_fact_check_reads_several_claim_ids_packed_into_one_field() -> None:
    research, script = _demo(ResearchPack), _demo(ScriptPackage)
    report = _demo(FactCheckReport)
    packed = report.model_copy(
        update={
            "claim_findings": [
                report.claim_findings[0].model_copy(update={"claim_id": "C1, C1"}),
            ]
        }
    )

    assert fact_check_issues(packed, script, research) == []


def test_the_opening_hooks_on_verified_fact_then_orients() -> None:
    research, brief, script = _demo(ResearchPack), _demo(EditorialBrief), _demo(ScriptPackage)

    assert opening_issues(script, brief, research) == []

    units = [unit.model_dump() for unit in script.script_units]
    units[0] |= {"claim_ids": []}
    units[1] |= {"narrative_function": "context"}
    unsound = script.model_copy(
        update={"script_units": [ScriptUnit.model_validate(unit) for unit in units]}
    )
    issues = opening_issues(unsound, brief, research)

    assert [issue.split(":")[0] for issue in issues] == ["U1", "U1", "U2"]
    assert "rest only on verified claims" in issues[0]
    assert "orient the viewer" in issues[2]


def test_a_line_its_own_claims_contradict_goes_back_before_the_fact_check() -> None:
    research, script = _demo(ResearchPack), _demo(ScriptPackage)
    units = [unit.model_dump() for unit in script.script_units]
    units[2] |= {"text": "The panel approved the deal. Or had it?"}
    units[3] |= {"text": "The panel approved it too.", "claim_ids": []}
    edited = script.model_copy(
        update={"script_units": [ScriptUnit.model_validate(unit) for unit in units]}
    )
    seen: list[tuple[str, str]] = []

    def infer(pairs: Sequence[tuple[str, str]]) -> list[float]:
        seen.extend(pairs)
        return [1.0 if "approved" in hypothesis else 0.0 for _, hypothesis in pairs]

    issues = contradiction_issues(edited, research, infer)

    assert [issue.split(":")[0] for issue in issues] == ["U3"]
    assert '"The panel approved the deal."' in issues[0]
    # A question asserts nothing; what it implies is the fact checker's to judge.
    assert all(not hypothesis.endswith("?") for _, hypothesis in seen)
    # Units without claims are the writer's framing; they are not checked here.
    assert all(hypothesis != "The panel approved it too." for _, hypothesis in seen)
