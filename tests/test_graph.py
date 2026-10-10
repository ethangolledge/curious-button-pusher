import json
from collections.abc import Mapping
from dataclasses import replace
from typing import Any, cast

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from content.config import ContentConfig
from content.providers.fake import FakeDecisionProvider, FakeModelProvider, ResponseValue
from content.schemas.fact_check import FactCheckReport
from content.schemas.judgement import Critique
from content.schemas.package import ReviewHandoff
from content.schemas.plan import EditorialBrief
from content.schemas.references import ReferenceRequest, ReferenceSet
from content.schemas.research import ResearchPack
from content.schemas.review import ReviewRequest, ReviewResponse
from content.schemas.script import LineEditPackage, ScriptPackage
from content.schemas.visuals import VisualPackage
from content.state import ContentOutput
from content.workflow.checkpoint import create_checkpointer
from content.workflow.demo import demo_answer, demo_response
from content.workflow.graph import build_graph
from content.workflow.records import build_review_handoff
from content.workflow.run import create_initial_state, resume_state, run_workflow

# One Jev batch per story node and connection in the demo story: plan (research, plan,
# and its one claim), script (opening + 6 units + 5 transitions + whole), the listener
# test (3 beats + the whole story), visuals (6 scenes + 5 bridges + sequence).
DEMO_JUDGEMENT_BATCHES = 3 + 13 + 4 + 12


def test_clean_pass_uses_one_call_per_artifact_plus_the_critic_and_parallel_judgements(
    app_config: ContentConfig,
) -> None:
    provider = FakeModelProvider(default_factory=demo_response)
    decisions = FakeDecisionProvider(demo_answer)
    result = _invoke(app_config, provider, decisions, "Evidence-led topic")

    assert result["status"] == "approved"
    assert [call.output_type.__name__ for call in provider.calls] == [
        "ResearchPack",
        "EditorialBrief",
        "ScriptPackage",
        "Critique",
        "FactCheckReport",
        # A first-time listener hears the verified narration before anyone signs it off.
        "AudienceReport",
        "VisualPackage",
        "Critique",
    ]
    assert [call.model.model for call in provider.calls] == [
        "deterministic-accurate",
        "deterministic-accurate",
        "deterministic-creative",
        "deterministic-accurate",
        "deterministic-accurate",
        "deterministic-accurate",
        "deterministic-creative",
        "deterministic-accurate",
    ]
    assert len(decisions.calls) == DEMO_JUDGEMENT_BATCHES
    assert {judgement.outcome for judgement in result["judgements"]} == {"pass"}
    package = result["final_package"]
    assert package is not None
    assert package.fact_check_report.routing_result == "verified"
    assert package.human_decisions == []
    assert len(result["call_log"]) == 8 + DEMO_JUDGEMENT_BATCHES


def test_model_inputs_are_lean(app_config: ContentConfig) -> None:
    provider = FakeModelProvider(default_factory=demo_response)
    _invoke(app_config, provider, FakeDecisionProvider(demo_answer), "Lean inputs")

    writer_input = json.loads(_inputs(provider, ScriptPackage)[0])
    assert "research_pack" not in writer_input
    assert [claim["claim_id"] for claim in writer_input["evidence"]["claims"]] == ["C1"]
    checker_input = json.loads(_inputs(provider, FactCheckReport)[0])
    assert "research_pack" not in checker_input
    assert "hook" not in checker_input["units_to_audit"][0]
    assert [claim["claim_id"] for claim in checker_input["evidence"]["claims"]] == ["C1"]


def test_research_with_nothing_documented_can_only_be_revised_or_stopped(
    app_config: ContentConfig,
) -> None:
    provider = FakeModelProvider({ResearchPack: [_research_response("insufficient")]})
    decisions = FakeDecisionProvider(demo_answer)
    reviewer = StaticReviewer(ReviewResponse(action="stop"))

    result = _run(app_config, provider, decisions, reviewer, "Unsupported premise")

    request = reviewer.requests[0]
    assert request.stage == "research"
    assert not request.approvable
    assert request.reason.startswith("The researcher found no focused, truthful story")
    assert result["status"] == "human_review"
    assert len(provider.calls) == 1
    assert decisions.calls == []


def test_plan_review_shows_the_plan_and_records_the_decision(app_config: ContentConfig) -> None:
    config = _with_plan_review(app_config)
    reviewer = StaticReviewer(ReviewResponse(action="approve"))
    provider = FakeModelProvider(default_factory=demo_response)

    result = _run(config, provider, FakeDecisionProvider(demo_answer), reviewer, "Planned story")

    assert result["status"] == "approved"
    request = reviewer.requests[0]
    assert request.stage == "plan"
    assert "**Central question:** What can we actually establish about Planned story?" in (
        request.snapshot
    )
    assert _call_count(provider, "ResearchPack") == 1
    assert [(d.stage, d.action) for d in result["human_decisions"]] == [("plan", "approve")]


def test_plan_feedback_revises_only_the_plan(app_config: ContentConfig) -> None:
    config = _with_plan_review(app_config)
    reviewer = SequenceReviewer(
        [
            ReviewResponse(action="revise", feedback="Centre the story on the evidence gap."),
            ReviewResponse(action="approve"),
        ]
    )
    provider = FakeModelProvider(default_factory=demo_response)

    result = _run(config, provider, FakeDecisionProvider(demo_answer), reviewer, "Redirected")

    assert result["status"] == "approved"
    assert result["plan_revision_count"] == 1
    assert _call_count(provider, "ResearchPack") == 1
    assert "Centre the story on the evidence gap." in _inputs(provider, EditorialBrief)[1]


def test_programmatic_caller_receives_pending_plan_review(app_config: ContentConfig) -> None:
    graph = build_graph(
        config=_with_plan_review(app_config),
        providers={"fake": FakeModelProvider(default_factory=demo_response)},
        decision_provider=FakeDecisionProvider(demo_answer),
        checkpointer=create_checkpointer(),
    )
    runtime: RunnableConfig = {"configurable": {"thread_id": "pending-plan"}}
    result = cast(dict[str, Any], graph.invoke(_initial(app_config, "Pending"), runtime))

    assert ReviewRequest.model_validate(result["__interrupt__"][0].value).stage == "plan"
    assert result.get("script_package") is None


def test_confident_blocking_failure_sends_targeted_correction(
    app_config: ContentConfig,
) -> None:
    provider = FakeModelProvider(default_factory=demo_response)
    decisions = FakeDecisionProvider(
        _fail_once("unit_supported", "U3", {"kind": "noul", "noul": 0.05})
    )

    result = _invoke(app_config, provider, decisions, "Overstated unit")

    assert result["status"] == "approved"
    assert result["script_revision_count"] == 1
    # A correction that names its line is a line edit of that line alone.
    assert _call_count(provider, "ScriptPackage") == 1
    assert _line_notes(provider) == {
        "U3": ["U3: state only what its cited claims support, keeping their qualifications."]
    }
    # The failure belonged to revision 0; the verdict on revision 1 ignored it.
    stale = [j for j in result["judgements"] if j.outcome == "fail"]
    assert [(j.revision, j.target_id) for j in stale] == [(0, "U3")]


def test_transition_that_contradicts_the_plan_is_revised(app_config: ContentConfig) -> None:
    provider = FakeModelProvider(default_factory=demo_response)
    decisions = FakeDecisionProvider(
        _fail_once(
            "transition_tension",
            "U2",
            {"kind": "choice", "choice": "release", "confidence": 0.9},
        )
    )

    result = _invoke(app_config, provider, decisions, "Flat middle")

    assert result["status"] == "approved"
    join = "U1->U2: the plan asks this unit to build tension, but it reads as release."
    assert _line_notes(provider) == {"U1": [join], "U2": [join]}


def test_the_critic_settles_jevs_doubts_instead_of_a_person(app_config: ContentConfig) -> None:
    reviewer = StaticReviewer(ReviewResponse(action="approve"))
    decisions = FakeDecisionProvider(
        _fail_once(
            "opening_hook",
            "opening",
            {"kind": "score", "score": 1.0, "confidence": 0.3, "probabilities": {"1": 0.5}},
        )
    )
    provider = FakeModelProvider(default_factory=demo_response)

    result = _run(app_config, provider, decisions, reviewer, "Ambiguous hook")

    assert result["status"] == "approved"
    assert reviewer.requests == []
    critique = json.loads(_inputs(provider, Critique)[0])
    assert critique["stage"] == "script"
    assert any("opening_hook (blocking): unsure" in doubt for doubt in critique["doubts"])
    assert _call_count(provider, "ScriptPackage") == 1


def test_only_one_weighty_line_is_allowed(app_config: ContentConfig) -> None:
    provider = FakeModelProvider(default_factory=demo_response)
    solemn = {"kind": "noul", "noul": 0.05}
    spent: list[str] = []

    def respond(asked: str, state: Mapping[str, Any]) -> dict[str, Any]:
        unit = _target(asked, state)
        if asked == "unit_plain" and unit in {"U2", "U5"} and unit not in spent:
            spent.append(unit)
            return solemn
        return demo_answer(asked, state)

    result = _invoke(app_config, provider, FakeDecisionProvider(respond), "Portentous")

    assert result["status"] == "approved"
    assert _line_notes(provider) == {
        "U2": ["U2: say it plainly; save the weighty line for the ending."]
    }


def test_an_abstract_scene_returns_to_the_visual_director(app_config: ContentConfig) -> None:
    provider = FakeModelProvider(default_factory=demo_response)
    decisions = FakeDecisionProvider(
        _fail_once("scene_concrete", "S2", {"kind": "noul", "noul": 0.05})
    )

    result = _invoke(app_config, provider, decisions, "Abstract")

    assert result["status"] == "approved"
    assert json.loads(_inputs(provider, VisualPackage)[1])["corrections"] == [
        "S2: anchor it on a concrete person, place, or object from its narration; keep any "
        "symbolism around that."
    ]


def test_the_critics_corrections_go_back_to_the_writer(app_config: ContentConfig) -> None:
    provider = FakeModelProvider(
        {
            Critique: [
                Critique(
                    verdict="revise",
                    corrections=["U3: open with the number, then the name."],
                    reasoning="The middle drags.",
                )
            ]
        },
        default_factory=demo_response,
    )

    result = _invoke(app_config, provider, FakeDecisionProvider(demo_answer), "Dragging middle")

    assert result["status"] == "approved"
    assert result["script_revision_count"] == 1
    assert _line_notes(provider) == {"U3": ["U3: open with the number, then the name."]}


def test_advisory_failures_are_recorded_but_do_not_route(app_config: ContentConfig) -> None:
    config = replace(
        app_config,
        decisions=replace(
            app_config.decisions,
            blocking=app_config.decisions.blocking - {"unit_pace"},
        ),
    )
    decisions = FakeDecisionProvider(
        _always(
            "unit_pace",
            {"kind": "choice", "choice": "overloaded", "confidence": 0.95},
            fallback=demo_answer,
        )
    )
    provider = FakeModelProvider(default_factory=demo_response)

    result = _invoke(config, provider, decisions, "Dense but acceptable")

    assert result["status"] == "approved"
    assert _call_count(provider, "ScriptPackage") == 1
    pace = [j for j in result["judgements"] if j.question_id == "unit_pace"]
    assert {(j.outcome, j.blocking) for j in pace} == {("fail", False)}


def test_structural_blockers_cannot_be_approved(app_config: ContentConfig) -> None:
    config = _with_limits(app_config, script=1)
    provider = FakeModelProvider(
        {ScriptPackage: [_script_without_required_claim()] * 2},
        default_factory=demo_response,
    )
    graph = build_graph(
        config=config,
        providers={"fake": provider},
        decision_provider=FakeDecisionProvider(demo_answer),
        checkpointer=create_checkpointer(),
    )
    runtime: RunnableConfig = {"configurable": {"thread_id": "structural"}}
    interrupted = cast(dict[str, Any], graph.invoke(_initial(config, "Missing claim"), runtime))
    request = ReviewRequest.model_validate(interrupted["__interrupt__"][0].value)

    assert request.stage == "script"
    assert not request.approvable
    assert request.required_changes[0] == "Script omits required research claims: C1."
    assert any("the hook must rest only on verified" in line for line in request.required_changes)
    with pytest.raises(ValueError, match="Approval is not permitted"):
        graph.invoke(Command[Any](resume=ReviewResponse(action="approve").model_dump()), runtime)


def test_human_can_accept_a_fact_check_without_rewriting_it(app_config: ContentConfig) -> None:
    provider = FakeModelProvider(
        {FactCheckReport: [_fact_check_response("human_review")]},
        default_factory=demo_response,
    )
    reviewer = StaticReviewer(ReviewResponse(action="approve", feedback="Checked the archive."))

    result = _run(
        app_config, provider, FakeDecisionProvider(demo_answer), reviewer, "Judgement call"
    )

    package = result["final_package"]
    assert package is not None
    assert reviewer.requests[0].stage == "fact_check"
    assert package.fact_check_report.routing_result == "human_review"
    assert [(d.stage, d.action, d.feedback) for d in package.human_decisions] == [
        ("fact_check", "approve", "Checked the archive.")
    ]
    assert _call_count(provider, "ScriptPackage") == 1


def test_fact_check_must_account_for_every_unit(app_config: ContentConfig) -> None:
    incomplete = {**_fact_check_response("verified"), "non_factual_unit_ids": []}
    incomplete["claim_findings"] = [
        {**incomplete["claim_findings"][0], "status": "passed", "severity": "none"}
    ]
    provider = FakeModelProvider({FactCheckReport: [incomplete]}, default_factory=demo_response)
    reviewer = StaticReviewer(ReviewResponse(action="stop"))

    result = _run(app_config, provider, FakeDecisionProvider(demo_answer), reviewer, "Gaps")

    request = reviewer.requests[0]
    assert request.stage == "fact_check"
    assert not request.approvable
    assert request.required_changes == ["Fact check gives no disposition for script units: U1."]
    assert result["status"] == "human_review"


def test_failed_fact_check_returns_corrections_to_the_writer(app_config: ContentConfig) -> None:
    provider = FakeModelProvider(
        {FactCheckReport: [_fact_check_response("revise_script")]},
        default_factory=demo_response,
    )
    result = _invoke(app_config, provider, FakeDecisionProvider(demo_answer), "Overreach")

    assert result["status"] == "approved"
    assert result["script_revision_count"] == 1
    # The writer gets the evidence boundary as a constraint, never a sentence to use.
    revision = json.loads(_inputs(provider, ScriptPackage)[1])
    assert revision["corrections"] == [
        "U2, U3, U4, U5, U6 (exaggerated): The script is broader than the research. "
        "The evidence supports: C1 documents only what the material discusses. "
        "It must carry: That this is what the material discusses. "
        "It must not imply: That the account is established."
    ]
    (constraint,) = revision["fact_constraints"]
    assert set(constraint) == {
        "claim_id",
        "script_unit_ids",
        "issue",
        "evidence_boundary",
        "required_qualification",
        "forbidden_implication",
    }
    assert result["revision_history"][0]["stage"] == "script"


def test_duplicating_visual_returns_to_visual_director(app_config: ContentConfig) -> None:
    provider = FakeModelProvider(default_factory=demo_response)
    decisions = FakeDecisionProvider(
        _fail_once(
            "scene_duplication",
            "S1",
            {"kind": "choice", "choice": "duplicates", "confidence": 0.9},
        )
    )

    result = _invoke(app_config, provider, decisions, "Literal visuals")

    assert result["status"] == "approved"
    assert result["visual_revision_count"] == 1
    assert _call_count(provider, "ScriptPackage") == 1
    assert json.loads(_inputs(provider, VisualPackage)[1])["corrections"] == [
        "S1: show something the narration does not already say."
    ]


def test_script_revision_limit_asks_a_person(app_config: ContentConfig) -> None:
    provider = FakeModelProvider(
        {FactCheckReport: [_fact_check_response("revise_script")] * 2},
        default_factory=demo_response,
    )
    reviewer = StaticReviewer(ReviewResponse(action="stop"))

    result = _run(
        _with_limits(app_config, script=1),
        provider,
        FakeDecisionProvider(demo_answer),
        reviewer,
        "Repeatedly inaccurate script",
    )

    assert reviewer.requests[0].stage == "fact_check"
    assert reviewer.requests[0].reason == "The automatic revision limit was reached."
    assert result["status"] == "human_review"
    assert result["script_revision_count"] == 1
    assert result.get("final_package") is None


def test_separate_runs_do_not_share_state() -> None:
    first = run_workflow("First topic")
    second = run_workflow("Second topic")

    assert first.require_final_package().topic == "First topic"
    assert second.require_final_package().topic == "Second topic"
    assert first.state["events"] is not second.state["events"]
    assert len(first.state["events"]) == len(second.state["events"]) == 15


# Helpers


def _invoke(
    config: ContentConfig,
    provider: FakeModelProvider,
    decisions: FakeDecisionProvider,
    topic: str,
) -> ContentOutput:
    graph = build_graph(config=config, providers={"fake": provider}, decision_provider=decisions)
    return cast(ContentOutput, graph.invoke(_initial(config, topic)))


def _run(
    config: ContentConfig,
    provider: FakeModelProvider,
    decisions: FakeDecisionProvider,
    reviewer: "StaticReviewer | SequenceReviewer",
    topic: str,
) -> ContentOutput:
    graph = build_graph(
        config=config,
        providers={"fake": provider},
        decision_provider=decisions,
        checkpointer=create_checkpointer(),
    )
    runtime: RunnableConfig = {"configurable": {"thread_id": f"test-{topic}"}}
    result = cast(dict[str, Any], graph.invoke(_initial(config, topic), runtime))
    while result.get("__interrupt__"):
        request = ReviewRequest.model_validate(result["__interrupt__"][0].value)
        response = reviewer.review(request)
        result = cast(
            dict[str, Any],
            graph.invoke(Command[Any](resume=response.model_dump()), runtime),
        )
    return cast(ContentOutput, result)


def _initial(config: ContentConfig, topic: str) -> Any:
    return create_initial_state(topic, source_material=None, user_instructions=None, config=config)


def _with_plan_review(config: ContentConfig) -> ContentConfig:
    return replace(config, workflow=replace(config.workflow, review_plan=True))


def _with_limits(config: ContentConfig, *, script: int) -> ContentConfig:
    limits = replace(config.workflow.max_revisions, script=script)
    return replace(config, workflow=replace(config.workflow, max_revisions=limits))


def _target(question_id: str, state: Mapping[str, Any]) -> str:
    if "scene" in state:
        return str(state["scene"]["scene_id"])
    if "opening" in state and "ending" not in state:
        return "opening"
    if "unit" in state:
        return str(state["unit"]["unit_id"])
    return question_id


def _fail_once(
    question_id: str,
    target: str,
    answer: dict[str, Any],
) -> Any:
    """Answer one question about one target badly the first time only."""
    spent: list[bool] = []

    def respond(asked: str, state: Mapping[str, Any]) -> dict[str, Any]:
        if asked == question_id and _target(asked, state) == target and not spent:
            spent.append(True)
            return answer
        return demo_answer(asked, state)

    return respond


def _always(question_id: str, answer: dict[str, Any], *, fallback: Any) -> Any:
    def respond(asked: str, state: Mapping[str, Any]) -> dict[str, Any]:
        return answer if asked == question_id else cast(dict[str, Any], fallback(asked, state))

    return respond


class StaticReviewer:
    def __init__(self, response: ReviewResponse) -> None:
        self.response = response
        self.requests: list[ReviewRequest] = []

    def review(self, request: ReviewRequest) -> ReviewResponse:
        self.requests.append(request)
        return self.response


class SequenceReviewer:
    def __init__(self, responses: list[ReviewResponse]) -> None:
        self.responses = list(responses)
        self.requests: list[ReviewRequest] = []

    def review(self, request: ReviewRequest) -> ReviewResponse:
        self.requests.append(request)
        return self.responses.pop(0)


def _call_count(provider: FakeModelProvider, output_name: str) -> int:
    return sum(call.output_type.__name__ == output_name for call in provider.calls)


def _line_notes(provider: FakeModelProvider) -> dict[str, list[str]]:
    """The notes on each line the (only) line edit was asked to rewrite."""
    (edit,) = _inputs(provider, LineEditPackage)
    return {line["unit_id"]: line["notes"] for line in json.loads(edit)["lines"]}


def _inputs(provider: FakeModelProvider, output_type: type[Any]) -> list[str]:
    return [call.input_text for call in provider.calls if call.output_type is output_type]


def _research_response(status: str) -> ResponseValue:
    return {
        "research_summary": "No usable evidence.",
        "timeline": [],
        "verified_facts": [],
        "reported_claims": [],
        "disputed_claims": [],
        "inferences": [],
        "unsupported_claims": [],
        "source_references": [],
        "source_comparisons": [],
        "contradictions": [],
        "missing_evidence": ["Sources"],
        "factual_limitations": ["No verification is possible."],
        "safe_wording": [],
        "research_confidence": "low",
        "evidence_status": "unverified",
        "research_status": status,
    }


def _script_without_required_claim() -> ResponseValue:
    script = cast(dict[str, Any], demo_response(json.dumps({"topic": "x"}), ScriptPackage))
    return {
        **script,
        "script_units": [{**unit, "claim_ids": []} for unit in script["script_units"]],
    }


def _fact_check_response(route: str) -> dict[str, Any]:
    return {
        "claim_findings": [
            {
                "claim": "Overstated claim",
                "claim_id": "C1",
                "script_unit_ids": ["U2", "U3", "U4", "U5", "U6"],
                "source_ids": [],
                "status": "exaggerated",
                "issue": "The script is broader than the research.",
                "evidence_boundary": "C1 documents only what the material discusses.",
                "required_qualification": "That this is what the material discusses.",
                "forbidden_implication": "That the account is established.",
                "severity": "major",
            }
        ],
        "non_factual_unit_ids": ["U1"],
        "routing_result": route,
    }


def test_author_brief_reaches_the_research_plan_and_script(app_config: ContentConfig) -> None:
    provider = FakeModelProvider(default_factory=demo_response)
    graph = build_graph(
        config=app_config,
        providers={"fake": provider},
        decision_provider=FakeDecisionProvider(demo_answer),
    )
    initial = create_initial_state(
        "The Great Stink",
        source_material=None,
        user_instructions="Open on the smell; end on who pays today.",
        config=app_config,
    )

    graph.invoke(initial)

    for output_type in (ResearchPack, EditorialBrief, ScriptPackage):
        assert "Open on the smell; end on who pays today." in _inputs(provider, output_type)[0]


def test_provisional_research_can_be_built_on_or_steered(app_config: ContentConfig) -> None:
    pack = {
        **cast(dict[str, Any], _research_response("sufficient")),
        "evidence_status": "provisional",
        "status_reason": "The corruption premise is alleged; the investment is documented.",
        "verified_facts": [
            {
                "claim_id": "C1",
                "claim": "The fund invested two billion dollars.",
                "source_ids": [],
                "qualification": None,
            }
        ],
    }
    config = replace(
        app_config, workflow=replace(app_config.workflow, allow_provisional_research=False)
    )
    provider = FakeModelProvider({ResearchPack: [pack, pack]}, default_factory=demo_response)
    reviewer = SequenceReviewer(
        [
            ReviewResponse(action="revise", feedback="Find the Senate letters."),
            ReviewResponse(action="approve"),
        ]
    )

    result = _run(config, provider, FakeDecisionProvider(demo_answer), reviewer, "Presupposed")

    first, second = reviewer.requests
    assert first.stage == second.stage == "research"
    assert first.approvable
    assert "The evidence is provisional" in first.reason
    assert "Researcher: The corruption premise is alleged" in first.reason
    assert "Find the Senate letters." in _inputs(provider, ResearchPack)[1]
    assert result["status"] == "approved"
    assert [(d.stage, d.action) for d in result["human_decisions"]] == [
        ("research", "revise"),
        ("research", "approve"),
    ]


def test_fact_check_reaudits_only_changed_units(app_config: ContentConfig) -> None:
    unclear = _fact_check_response("revise_script")
    unclear["claim_findings"] = [
        {**unclear["claim_findings"][0], "script_unit_ids": ["U3"]},
        {
            **unclear["claim_findings"][0],
            "script_unit_ids": ["U2", "U4", "U5", "U6"],
            "status": "passed",
            "severity": "none",
        },
    ]
    provider = FakeModelProvider({FactCheckReport: [unclear]}, default_factory=demo_response)

    result = _invoke(app_config, provider, FakeDecisionProvider(demo_answer), "Incremental")

    assert result["status"] == "approved"
    first, second = (json.loads(text) for text in _inputs(provider, FactCheckReport))
    audited = [unit["unit_id"] for unit in first["units_to_audit"]]
    assert audited == ["U1", "U2", "U3", "U4", "U5", "U6"]
    # The fake writer returns the same script, so every unit is now reused: the second
    # audit covers only U3, the unit that failed, because failures are never remembered.
    assert [unit["unit_id"] for unit in second["units_to_audit"]] == ["U3"]
    assert second["already_verified_unit_ids"] == ["U1", "U2", "U4", "U5", "U6"]


def test_missing_context_alone_does_not_force_a_rewrite(app_config: ContentConfig) -> None:
    context_only = _fact_check_response("revise_script")
    context_only["claim_findings"] = [
        {**context_only["claim_findings"][0], "status": "missing_context"}
    ]
    provider = FakeModelProvider({FactCheckReport: [context_only]}, default_factory=demo_response)

    result = _invoke(app_config, provider, FakeDecisionProvider(demo_answer), "Compressed")

    assert result["status"] == "approved"
    assert _call_count(provider, "ScriptPackage") == 1
    # Advice about this script version, replaced when the writer makes a new one.
    assert any(warning.startswith("Context note:") for warning in result["script_warnings"])


def test_a_stopped_run_resumes_without_paying_for_earlier_stages(
    app_config: ContentConfig,
) -> None:
    provider = FakeModelProvider(
        {FactCheckReport: [_fact_check_response("human_review")]},
        default_factory=demo_response,
    )
    stopped = _run(
        app_config,
        provider,
        FakeDecisionProvider(demo_answer),
        StaticReviewer(ReviewResponse(action="stop")),
        "Resumable",
    )
    # Through JSON, exactly as the CLI saves and reloads it.
    handoff = ReviewHandoff.model_validate_json(build_review_handoff(stopped).model_dump_json())
    resumed_provider = FakeModelProvider(default_factory=demo_response)
    reviewer = StaticReviewer(ReviewResponse(action="approve"))

    graph = build_graph(
        config=app_config,
        providers={"fake": resumed_provider},
        decision_provider=FakeDecisionProvider(demo_answer),
        checkpointer=create_checkpointer(),
    )
    runtime: RunnableConfig = {"configurable": {"thread_id": "resumed"}}
    reopened = resume_state(handoff, app_config, "script", "Open on trust.")
    assert reopened["user_instructions"] == "Open on trust."
    # What code had worked out from the kept plan and script is worked out again.
    size = reopened.get("story_size")
    assert size is not None and reopened["target_seconds"] == size.target_seconds
    assert set(reopened["unit_seconds"]) == {
        unit.unit_id
        for unit in handoff.script_package.script_units  # type: ignore[union-attr]
    }
    assert reopened["unit_feelings"]
    result = cast(dict[str, Any], graph.invoke(reopened, runtime))
    while result.get("__interrupt__"):
        request = ReviewRequest.model_validate(result["__interrupt__"][0].value)
        result = cast(
            dict[str, Any],
            graph.invoke(Command[Any](resume=reviewer.review(request).model_dump()), runtime),
        )

    assert reviewer.requests[0].stage == "script"
    assert result["status"] == "approved"
    assert [call.output_type.__name__ for call in resumed_provider.calls] == [
        "FactCheckReport",
        "AudienceReport",
        "VisualPackage",
        "Critique",
    ]


def test_a_forced_rewrite_also_fixes_narration_past_the_longest_video(
    app_config: ContentConfig,
) -> None:
    # Two rewrites once chased the ending while the script ran past three minutes,
    # and the writer was never told.
    script = cast(dict[str, Any], demo_response(json.dumps({"topic": "Too long"}), ScriptPackage))
    ending = script["script_units"][-1]
    padding = "The record keeps growing as new papers appear. " * 70
    repeated = "Some details are documented in more than one place."
    long_script = {
        **script,
        "script_units": [
            *script["script_units"][:-1],
            {**ending, "text": f"{ending['text']} {repeated} {padding}"},
        ],
    }
    provider = FakeModelProvider({ScriptPackage: [long_script]}, default_factory=demo_response)

    _invoke(app_config, provider, FakeDecisionProvider(demo_answer), "Too long")

    corrections = json.loads(_inputs(provider, ScriptPackage)[1])["corrections"]
    assert any(note.startswith("The ending repeats") for note in corrections)
    assert any("the longest video allows" in note for note in corrections)
    writer_input = json.loads(_inputs(provider, ScriptPackage)[0])
    assert writer_input["length"]["longest_seconds"] > writer_input["length"]["target_seconds"]


def test_a_resumed_storyboard_keeps_its_chosen_reference_photos(
    app_config: ContentConfig,
) -> None:
    # A resume once searched for its references again, chose other photographs,
    # and paid to redraw the five keyframes drawn from them.
    approved = _run(
        app_config,
        FakeModelProvider(default_factory=demo_response),
        FakeDecisionProvider(demo_answer),
        StaticReviewer(ReviewResponse(action="approve")),
        "Resumable",
    )
    stopped = _run(
        app_config,
        FakeModelProvider(
            {FactCheckReport: [_fact_check_response("human_review")]},
            default_factory=demo_response,
        ),
        FakeDecisionProvider(demo_answer),
        StaticReviewer(ReviewResponse(action="stop")),
        "Resumable",
    )
    request = ReferenceRequest(
        ref_id="R1", kind="person", query="Ada Lovelace", unit_ids=["U1"], purpose="likeness"
    )
    chosen = ReferenceSet(request=request, relevant=True, candidates=[], chosen=["portrait.png"])
    saved = build_review_handoff({**stopped, "references": {"R1": chosen}})
    handoff = ReviewHandoff.model_validate_json(saved.model_dump_json()).model_copy(
        update={"visual_package": approved["visual_package"]}
    )

    assert resume_state(handoff, app_config, "visuals")["references"] == {"R1": chosen}
    assert resume_state(handoff, app_config, "script")["references"] == {}


def test_a_resumed_run_keeps_the_story_judgements_for_its_next_save(
    app_config: ContentConfig,
) -> None:
    # The scenes' emotional fields come from the script's judgements. A resumed run that
    # dropped them saved without them, so the resume after it drew neutral scenes.
    stopped = _run(
        app_config,
        FakeModelProvider(
            {FactCheckReport: [_fact_check_response("human_review")]},
            default_factory=demo_response,
        ),
        FakeDecisionProvider(demo_answer),
        StaticReviewer(ReviewResponse(action="stop")),
        "Resumable",
    )
    handoff = ReviewHandoff.model_validate_json(build_review_handoff(stopped).model_dump_json())
    assert any(j.stage == "script" for j in handoff.judgements)

    reopened = resume_state(handoff, app_config, "script")

    assert {j.stage for j in reopened["judgements"]} <= {"plan", "script"}
    assert any(j.stage == "script" for j in reopened["judgements"])


def test_a_person_revising_the_script_sends_only_their_notes(
    app_config: ContentConfig,
) -> None:
    # The writer once also received the fact checker's automatic notes, acted on
    # them, and rewrote an ending the person had asked it to keep word for word.
    config = replace(app_config, workflow=replace(app_config.workflow, review_script=True))
    provider = FakeModelProvider(
        {FactCheckReport: [_fact_check_response("human_review"), _fact_check_response("verified")]},
        default_factory=demo_response,
    )
    reviewer = SequenceReviewer(
        [
            ReviewResponse(action="revise", feedback="Open on the harbour."),
            ReviewResponse(action="approve"),
        ]
    )

    _run(config, provider, FakeDecisionProvider(demo_answer), reviewer, "Two tables")

    assert [request.stage for request in reviewer.requests] == ["fact_check", "fact_check"]
    # The first rewrite is the one answering the person.
    rewrite = [call for call in provider.calls if call.output_type is ScriptPackage][1]
    sent = json.loads(rewrite.input_text)
    assert sent["human_review_feedback"] == "Open on the harbour."
    assert sent["corrections"] == []
