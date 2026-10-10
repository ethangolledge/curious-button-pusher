from dataclasses import replace
from typing import Any

from content.config import ContentConfig
from content.judging.outcomes import answer_outcome, current_judgements, stage_verdict
from content.judging.questions import QUESTIONS
from content.schemas.fact_check import FactCheckReport
from content.schemas.judgement import Answer, Judgement, Outcome
from content.schemas.research import ResearchPack
from content.state import ContentState
from content.workflow.routing import route_fact_check, route_research, route_script_verdict


def test_noul_answers_use_yes_and_no_thresholds(app_config: ContentConfig) -> None:
    question = QUESTIONS["script_payoff"]
    decisions = app_config.decisions

    def outcome(probability: float) -> Outcome:
        return answer_outcome(question, Answer(kind="noul", noul=probability), None, decisions)

    assert outcome(0.8) == "pass"
    assert outcome(0.5) == "unsure"
    assert outcome(0.2) == "fail"


def test_choice_answers_need_confidence_and_can_compare_with_the_plan(
    app_config: ContentConfig,
) -> None:
    decisions = app_config.decisions
    duplication = QUESTIONS["scene_duplication"]
    tension = QUESTIONS["transition_tension"]

    def choice(value: str, confidence: float) -> Answer:
        return Answer(kind="choice", choice=value, confidence=confidence)

    assert answer_outcome(duplication, choice("duplicates", 0.9), None, decisions) == "fail"
    assert answer_outcome(duplication, choice("duplicates", 0.4), None, decisions) == "unsure"
    assert answer_outcome(duplication, choice("adds", 0.9), None, decisions) == "pass"
    assert answer_outcome(tension, choice("release", 0.9), "release", decisions) == "pass"
    assert answer_outcome(tension, choice("build", 0.9), "release", decisions) == "fail"


def test_score_answers_pass_at_the_questions_level(app_config: ContentConfig) -> None:
    question = QUESTIONS["opening_hook"]

    def score(probabilities: dict[str, float], confidence: float = 0.9) -> Outcome:
        answer = Answer(kind="score", confidence=confidence, probabilities=probabilities)
        return answer_outcome(question, answer, None, app_config.decisions)

    assert score({"0": 0.9, "1": 0.1}) == "fail"
    assert score({"1": 0.8, "2": 0.2}) == "pass"
    assert score({"0": 0.9}, confidence=0.2) == "unsure"


def test_verdict_prefers_revision_then_review_and_ignores_advice() -> None:
    advisory_fail = _judgement("unit_pace", "fail", blocking=False)
    blocking_unsure = _judgement("opening_hook", "unsure")
    blocking_fail = _judgement("unit_supported", "fail", target_id="U2")

    assert stage_verdict([advisory_fail]).route == "accept"
    assert stage_verdict([advisory_fail, blocking_unsure]).route == "human_review"
    verdict = stage_verdict([blocking_unsure, blocking_fail])
    assert verdict.route == "revise"
    assert verdict.corrections == [
        "U2: state only what its cited claims support, keeping their qualifications."
    ]


def test_only_current_revision_judgements_count() -> None:
    stale = _judgement("unit_supported", "fail", revision=0)
    current = _judgement("unit_supported", "pass", revision=1)
    state: ContentState = {"judgements": [stale, current], "script_revision_count": 1}

    assert current_judgements(state, "script") == [current]


def test_research_routing_repairs_integrity_problems_once(app_config: ContentConfig) -> None:
    workflow = app_config.workflow
    state: ContentState = {"research_pack": _research("sufficient", "provisional")}
    assert route_research(state, workflow=workflow) == "sufficient"
    assert (
        route_research(state, workflow=replace(workflow, allow_provisional_research=False))
        == "review"
    )

    broken = _research("sufficient", "provisional", claim_sources=["W9"])
    assert broken.integrity_warnings
    state = {"research_pack": broken, "research_revision_count": 0}
    assert route_research(state, workflow=workflow) == "revise"
    state["research_revision_count"] = workflow.max_revisions.research
    assert route_research(state, workflow=workflow) == "sufficient"

    state = {"research_pack": _research("revise", "provisional"), "research_revision_count": 1}
    assert route_research(state, workflow=workflow) == "review"


def test_script_routes_spend_one_revision_allowance(app_config: ContentConfig) -> None:
    workflow = app_config.workflow
    limit = workflow.max_revisions.script
    revise: ContentState = {"routing_decision": "revise", "script_revision_count": 0}
    assert route_script_verdict(revise, workflow=workflow) == "script_writer"
    revise["script_revision_count"] = limit
    assert route_script_verdict(revise, workflow=workflow) == "human_review"

    state: ContentState = {
        "fact_check_report": _fact_report("revise_script"),
        "script_revision_count": limit,
    }
    assert route_fact_check(state, workflow=workflow) == "human_review"
    state = {"fact_check_report": _fact_report("verified"), "structural_blockers": True}
    assert route_fact_check(state, workflow=workflow) == "human_review"


def _judgement(
    question_id: str,
    outcome: Outcome,
    *,
    blocking: bool = True,
    target_id: str = "U1",
    revision: int = 0,
) -> Judgement:
    return Judgement(
        stage="script",
        revision=revision,
        target_id=target_id,
        question_id=question_id,
        answer=Answer(kind="noul", noul=0.5),
        expected=None,
        outcome=outcome,
        blocking=blocking,
        model="test-jev",
    )


def _research(
    status: str, evidence: str, *, claim_sources: list[str] | None = None
) -> ResearchPack:
    data: dict[str, Any] = {
        "research_summary": "Summary",
        "timeline": [],
        "verified_facts": [],
        "reported_claims": [],
        "disputed_claims": [],
        "inferences": [],
        "unsupported_claims": [],
        "source_references": [],
        "source_comparisons": [],
        "contradictions": [],
        "missing_evidence": [],
        "factual_limitations": [],
        "safe_wording": [],
        "research_confidence": "low",
        "evidence_status": evidence,
        "research_status": status,
    }
    if claim_sources is not None:
        data["verified_facts"] = [
            {"claim_id": "C1", "claim": "Claim", "source_ids": claim_sources, "qualification": None}
        ]
    return ResearchPack.model_validate(data)


def _fact_report(route: str) -> FactCheckReport:
    return FactCheckReport.model_validate(
        {
            "claim_findings": [],
            "non_factual_unit_ids": [],
            "routing_result": route,
        }
    )
