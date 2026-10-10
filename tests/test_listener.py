"""The authority structure around the narration: truth sets the evidence boundary, the
Story Architect decides what matters, the writer owns every word, and a first-time
listener tests whether it was understood."""

import json
from dataclasses import replace
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from content.config import ContentConfig
from content.providers.fake import FakeDecisionProvider, FakeModelProvider
from content.review.render import render_audience
from content.schemas.audience import AudienceReport, StoryDecision, StoryDecisions
from content.schemas.fact_check import ClaimFinding, FactCheckReport
from content.schemas.package import ReviewHandoff
from content.schemas.plan import EditorialBrief
from content.schemas.research import ResearchPack
from content.schemas.review import ReviewRequest, ReviewResponse
from content.schemas.script import ScriptPackage
from content.story.ledger import apply_story_decisions
from content.workflow.checkpoint import create_checkpointer
from content.workflow.demo import demo_answer, demo_response
from content.workflow.graph import build_graph
from content.workflow.run import create_initial_state, resume_state

# A line of the demo script; every demo line carries the story's one spine claim.
SPINE_LINE = "That distinction changes which claims can be stated as fact."


def test_the_cold_viewer_hears_the_narration_and_nothing_else(
    app_config: ContentConfig,
) -> None:
    provider = FakeModelProvider(default_factory=demo_response)

    _invoke(app_config, provider, "Only the words")

    (call,) = [c for c in provider.calls if c.output_type is AudienceReport]
    script = ScriptPackage.model_validate(
        demo_response(json.dumps({"topic": "Only the words"}), ScriptPackage)
    )
    assert json.loads(call.input_text) == {"narration": script.master_script}
    # Its instructions are its own: no theme, plan, or research rides along.
    assert call.instructions.startswith("# Role\n\nYou are a first-time listener.")
    assert "story_chain" not in call.instructions


def test_fact_findings_are_constraints_and_carry_no_wording() -> None:
    assert set(ClaimFinding.model_fields) == {
        "claim",
        "claim_id",
        "script_unit_ids",
        "source_ids",
        "status",
        "issue",
        "evidence_boundary",
        "required_qualification",
        "forbidden_implication",
        "severity",
    }
    assert "required_corrections" not in FactCheckReport.model_fields


def test_a_required_claim_the_listener_stumbles_on_goes_to_the_architect_first(
    app_config: ContentConfig,
) -> None:
    stumbled = _listener(unrelated=[{"quote": SPINE_LINE, "note": "Why am I told this?"}])
    provider = FakeModelProvider(
        {
            AudienceReport: [stumbled, _listener()],
            StoryDecisions: [
                {
                    "decisions": [
                        {"claim_id": "C1", "action": "keep", "note": "Say why it matters."}
                    ],
                    "reasoning": "The story needs it.",
                }
            ],
        },
        default_factory=demo_response,
    )

    result = _invoke(app_config, provider, "Stumbled")

    assert result["status"] == "approved"
    order = [call.output_type.__name__ for call in provider.calls]
    # The revised lines are checked again only where they changed: the demo writer's
    # lines come back the same, so their audits stand and no fact-check call is made.
    assert order[order.index("FactCheckReport") :][:6] == [
        "FactCheckReport",
        "AudienceReport",
        "StoryDecisions",
        "ScriptPackage",
        "Critique",
        "AudienceReport",
    ]
    # The writer revises with what the listener experienced and the Architect's intent,
    # and every fact constraint; the words stay the writer's.
    revision = json.loads(_inputs(provider, ScriptPackage)[1])
    assert revision["listener_report"]["unrelated_facts"][0]["quote"] == SPINE_LINE
    assert any("could not tell why" in note for note in revision["corrections"])
    assert "C1 (keep): Say why it matters." in revision["corrections"]


def test_an_unclear_term_goes_straight_to_the_writer(app_config: ContentConfig) -> None:
    unclear = _listener(terms=[{"quote": "attributed", "note": "Attributed to whom?"}])
    provider = FakeModelProvider(
        {AudienceReport: [unclear, _listener()]}, default_factory=demo_response
    )

    result = _invoke(app_config, provider, "Jargon")

    assert result["status"] == "approved"
    assert not [call for call in provider.calls if call.output_type is StoryDecisions]
    revision = json.loads(_inputs(provider, ScriptPackage)[1])
    assert any('"attributed" needed knowledge' in note for note in revision["corrections"])


def test_when_the_revisions_run_out_the_person_decides_with_the_listener_report(
    app_config: ContentConfig,
) -> None:
    lost = _listener(terms=[{"quote": "attributed", "note": "Attributed to whom?"}])
    provider = FakeModelProvider({AudienceReport: [lost] * 3}, default_factory=demo_response)
    limits = replace(app_config.workflow.max_revisions, script=2)
    config = replace(app_config, workflow=replace(app_config.workflow, max_revisions=limits))
    requests: list[ReviewRequest] = []

    _run(config, provider, "Still lost", requests)

    (request,) = requests
    assert request.stage == "fact_check"
    assert any('"attributed" needed knowledge' in finding for finding in request.findings)
    assert "## What a First-Time Listener Heard" in request.snapshot
    assert len(_inputs(provider, ScriptPackage)) == 3


def test_only_the_architect_changes_what_the_story_requires() -> None:
    brief = EditorialBrief.model_validate(demo_response('{"topic": "x"}', EditorialBrief))
    decisions = StoryDecisions(
        decisions=[StoryDecision(claim_id="C1", action="cut", note="Not needed.")],
        reasoning="",
    )

    cut = apply_story_decisions(brief, decisions)

    assert cut.required_claim_ids == []
    assert cut.excluded_claim_ids == ["C1"]
    assert all("C1" not in beat.claim_ids for beat in cut.arc)


def test_a_claim_moves_and_demotes_only_as_the_architect_says() -> None:
    brief = EditorialBrief.model_validate(demo_response('{"topic": "x"}', EditorialBrief))
    moved = apply_story_decisions(
        brief,
        StoryDecisions(
            decisions=[
                StoryDecision(claim_id="C1", action="move", target="P3", note=""),
                StoryDecision(claim_id="C1", action="demote", new_role="colour", note=""),
            ],
            reasoning="",
        ),
    )
    nowhere = apply_story_decisions(
        brief,
        StoryDecisions(
            decisions=[StoryDecision(claim_id="C1", action="move", target="P9", note="")],
            reasoning="",
        ),
    )

    assert [beat.claim_ids for beat in moved.arc] == [[], [], ["C1"]]
    assert moved.supporting_claim_ids == ["C1"]
    # A move to a beat that does not exist changes nothing.
    assert nowhere == brief


def test_the_sign_off_shows_what_the_listener_heard_beside_the_intended_story() -> None:
    brief = EditorialBrief.model_validate(demo_response('{"topic": "x"}', EditorialBrief))
    report = AudienceReport.model_validate(
        _listener(confusions=[{"quote": "the record", "note": "Which record?"}])
    )

    page = "\n".join(render_audience(report, brief))

    assert "Confused by: “the record” — Which record?" in page
    assert f"1. {brief.story_chain[0]}" in page


def _listener(**flags: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "about": "An account and its evidence.",
        "what_happened": "An account spread.",
        "why_it_happened": "Nobody checked it.",
        "why_it_matters": "It changes what can be concluded.",
        "key_facts": ["The record supports less than the account."],
        "question": "What can we establish?",
        "unresolved": "What the record cannot show.",
        "confusions": flags.get("confusions", []),
        "unrelated_facts": flags.get("unrelated", []),
        "unclear_terms": flags.get("terms", []),
        "lost_thread_at": None,
    }


def _invoke(config: ContentConfig, provider: FakeModelProvider, topic: str) -> Any:
    graph = build_graph(
        config=config,
        providers={"fake": provider},
        decision_provider=FakeDecisionProvider(demo_answer),
    )
    initial = create_initial_state(
        topic, source_material=None, user_instructions=None, config=config
    )
    return graph.invoke(cast(Any, initial))


def _run(
    config: ContentConfig,
    provider: FakeModelProvider,
    topic: str,
    requests: list[ReviewRequest],
) -> None:
    graph = build_graph(
        config=config,
        providers={"fake": provider},
        decision_provider=FakeDecisionProvider(demo_answer),
        checkpointer=create_checkpointer(),
    )
    runtime: RunnableConfig = {"configurable": {"thread_id": f"test-{topic}"}}
    initial = create_initial_state(
        topic, source_material=None, user_instructions=None, config=config
    )
    result = cast(dict[str, Any], graph.invoke(cast(Any, initial), runtime))
    while result.get("__interrupt__"):
        requests.append(ReviewRequest.model_validate(result["__interrupt__"][0].value))
        stop = ReviewResponse(action="stop", decided_by="person")
        result = cast(dict[str, Any], graph.invoke(Command(resume=stop.model_dump()), runtime))


def _inputs(provider: FakeModelProvider, output_type: type[Any]) -> list[str]:
    return [call.input_text for call in provider.calls if call.output_type is output_type]


def test_a_resumed_sign_off_keeps_the_fact_checks_boundaries(app_config: ContentConfig) -> None:
    def demo(output_type: type[Any]) -> Any:
        return output_type.model_validate(demo_response('{"topic": "x"}', output_type))

    crossed = ClaimFinding(
        claim="It happened.",
        claim_id="C1",
        script_unit_ids=["U2"],
        source_ids=[],
        status="exaggerated",
        issue="Stronger than the source.",
        evidence_boundary="The source reports it.",
        severity="major",
    )
    passed = crossed.model_copy(update={"status": "passed", "severity": "none"})
    handoff = ReviewHandoff(
        topic="x",
        duration_seconds=60,
        aspect_ratio="9:16",
        current_stage="fact_check",
        review_request=ReviewRequest(stage="fact_check", reason=""),
        review_response=ReviewResponse(action="stop"),
        research_pack=demo(ResearchPack),
        editorial_brief=demo(EditorialBrief),
        script_package=demo(ScriptPackage),
        fact_check_report=FactCheckReport(
            claim_findings=[crossed, passed],
            non_factual_unit_ids=[],
            routing_result="revise_script",
        ),
        visual_package=None,
        judgements=[],
        human_decisions=[],
        warnings=[],
        status="human_review",
    )

    state = resume_state(handoff, app_config, "fact_check")

    assert state["fact_constraints"] == [crossed]
