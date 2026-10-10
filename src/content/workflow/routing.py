"""Where the run goes next after each stage: on to the next stage, back for a revision within
the configured limits, or to a person."""

from collections.abc import Callable
from typing import Literal

from langgraph.types import Send

from content.config import WorkflowConfig
from content.judging.outcomes import current_judgements, current_revision
from content.schemas.research import ResearchPack
from content.state import ContentState
from content.story.ledger import audience_tasks, plan_tasks, script_tasks, unjudged, visual_tasks

# The producer's task builders, passed in by the graph: a render stage fans out into one
# task per keyframe or morph, or goes straight on when there is nothing to render.
Tasks = Callable[[ContentState], "list[Send] | str"]

ResearchRoute = Literal["sufficient", "revise", "review"]
PlanRoute = Literal["script_writer", "human_review"]
ScriptRoute = Literal["fact_checker", "script_writer", "human_review"]
FactCheckRoute = Literal["cold_viewer", "script_writer", "human_review"]
AudienceRoute = Literal["human_review", "visual_director", "script_writer", "story_decisions"]
VisualRoute = Literal["final_package", "start_production", "visual_director", "human_review"]
HumanReviewRoute = Literal[
    "stop",
    "fact_researcher",
    "editorial_plan",
    "script_writer",
    "fact_checker",
    "visual_director",
    "price_pictures",
    "start_production",
    "start_keyframes",
    "start_segments",
    "apply_director_notes",
    "final_package",
]


# Graph edges


def route_start(state: ContentState) -> Literal["fact_researcher", "human_review"]:
    """A resumed run reopens its saved review; a new run starts with research."""
    return "human_review" if state.get("current_stage") else "fact_researcher"


def route_research(state: ContentState, *, workflow: WorkflowConfig) -> ResearchRoute:
    """Accept source-backed research; give one automatic repair; otherwise ask a person.

    A gap in the evidence is never a dead end: the person sees what is documented and
    chooses to build on it, steer another research pass, or stop."""
    pack = state.get("research_pack")
    if pack is None or pack.research_status == "insufficient":
        return "review"
    can_revise = state.get("research_revision_count", 0) < workflow.max_revisions.research
    if pack.research_status == "revise" or pack.integrity_warnings:
        # Integrity problems get one targeted repair; if they persist, the plan
        # review shows them to a person rather than hiding them.
        if can_revise:
            return "revise"
        if pack.research_status == "revise":
            return "review"
    if pack.evidence_status == "source_backed" and pack.source_references:
        return "sufficient"
    if pack.evidence_status == "provisional" and workflow.allow_provisional_research:
        return "sufficient"
    return "review"


def research_gap_reason(state: ContentState, *, workflow: WorkflowConfig) -> str:
    """Why the research was not accepted automatically, in words a person can act on."""
    pack = state.get("research_pack")
    if pack is None:
        return "No research pack was produced."
    because = f" Researcher: {pack.status_reason}" if pack.status_reason else ""
    return _stop_reason(pack, workflow) + because


def _stop_reason(pack: ResearchPack, workflow: WorkflowConfig) -> str:
    if pack.research_status == "insufficient":
        return "The researcher found no focused, truthful story that the evidence supports."
    if pack.research_status == "revise":
        return "The researcher still wanted another pass after the allowed revision."
    if pack.evidence_status == "unverified":
        return "The evidence is unverified."
    if pack.evidence_status == "provisional" and not workflow.allow_provisional_research:
        return (
            "The evidence is provisional: part of the central record rests on allegation or "
            "weak sourcing, and this configuration requires source-backed research."
        )
    return "The research is labelled source-backed but lists no sources."


def fan_out_plan(state: ContentState) -> list[Send]:
    brief, research = state.get("editorial_brief"), state.get("research_pack")
    if brief is None or research is None:
        raise ValueError("Plan judgement requires a creative plan and research")
    return [
        Send("judge_plan", task)
        for task in plan_tasks(brief, research, current_revision(state, "plan"))
    ]


def route_plan_verdict(state: ContentState) -> PlanRoute:
    return "script_writer" if state.get("routing_decision") == "accept" else "human_review"


def route_script_gate(
    state: ContentState,
    *,
    workflow: WorkflowConfig,
    intended_voice: str,
) -> list[Send] | ScriptRoute:
    if state.get("structural_blockers"):
        return _script_revision_or_review(state, workflow)
    script, brief, research = (
        state.get("script_package"),
        state.get("editorial_brief"),
        state.get("research_pack"),
    )
    if script is None or brief is None or research is None:
        raise ValueError("Script judgement requires a script, plan, and research")
    revision = current_revision(state, "script")
    tasks = unjudged(
        script_tasks(script, brief, research, revision, intended_voice),
        current_judgements(state, "script"),
    )
    return [Send("judge_script", task) for task in tasks]


def route_script_verdict(
    state: ContentState, *, workflow: WorkflowConfig
) -> Literal["critique_script", "script_writer", "human_review"]:
    """A confident failure goes straight back to the writer; everything else, including
    Jev's doubts, goes to the critic, who reads the whole script."""
    if state.get("routing_decision") == "revise":
        return _script_revision_or_review(state, workflow)
    return "critique_script"


def route_script_critique(state: ContentState, *, workflow: WorkflowConfig) -> ScriptRoute:
    if state.get("routing_decision") == "revise":
        return _script_revision_or_review(state, workflow)
    return "fact_checker"


def route_fact_check(state: ContentState, *, workflow: WorkflowConfig) -> FactCheckRoute:
    report = state.get("fact_check_report")
    if report is None or state.get("structural_blockers"):
        return "human_review"
    if report.routing_result == "verified":
        # Every verified script is heard by a first-time listener before anyone signs it off.
        return "cold_viewer"
    if report.routing_result == "revise_script":
        return _script_revision_or_review(state, workflow)
    return "human_review"


def fan_out_audience(state: ContentState) -> list[Send]:
    """Compare the listener's account with the story ledger, one task per beat and one for
    the whole story, in parallel."""
    report, brief = state.get("audience_report"), state.get("editorial_brief")
    if report is None or brief is None:
        raise ValueError("The audience comparison needs the listener test and the plan")
    revision = current_revision(state, "audience")
    return [Send("judge_audience", task) for task in audience_tasks(report, brief, revision)]


def route_audience_verdict(state: ContentState, *, workflow: WorkflowConfig) -> AudienceRoute:
    """A heard story goes to the Script sign-off; a story the listener missed is revised,
    by the Architect first when it touches what the story requires. Revisions spend the
    script's allowance; when it is spent, the person decides with the listener's report."""
    decision = state.get("routing_decision")
    if decision == "pass":
        return "human_review" if workflow.review_script else "visual_director"
    if _script_revision_or_review(state, workflow) == "human_review":
        return "human_review"
    return "story_decisions" if decision == "story" else "script_writer"


def route_visual_gate(
    state: ContentState,
    *,
    workflow: WorkflowConfig,
) -> list[Send] | VisualRoute:
    if state.get("structural_blockers"):
        return _visual_revision_or_review(state, workflow)
    visuals, script = state.get("visual_package"), state.get("script_package")
    if visuals is None or script is None:
        raise ValueError("Visual judgement requires a visual plan and script")
    revision = current_revision(state, "visuals")
    return [Send("judge_visuals", task) for task in visual_tasks(visuals, script, revision)]


def route_visual_verdict(
    state: ContentState, *, workflow: WorkflowConfig
) -> Literal["critique_visuals", "visual_director", "human_review"]:
    if state.get("routing_decision") == "revise":
        return _visual_revision_or_review(state, workflow)
    return "critique_visuals"


def route_visual_critique(
    state: ContentState,
    *,
    workflow: WorkflowConfig,
    produce: bool,
) -> VisualRoute:
    if state.get("routing_decision") == "revise":
        return _visual_revision_or_review(state, workflow)
    return "start_production" if produce else "final_package"


# Every automatic revision spends from a bounded allowance; exhaustion asks a person.


def _script_revision_or_review(
    state: ContentState,
    workflow: WorkflowConfig,
) -> Literal["script_writer", "human_review"]:
    within_limit = state.get("script_revision_count", 0) < workflow.max_revisions.script
    return "script_writer" if within_limit else "human_review"


def _visual_revision_or_review(
    state: ContentState,
    workflow: WorkflowConfig,
) -> Literal["visual_director", "human_review"]:
    within_limit = state.get("visual_revision_count", 0) < workflow.max_revisions.visuals
    return "visual_director" if within_limit else "human_review"


def route_timing(
    state: ContentState,
    *,
    workflow: WorkflowConfig,
    keyframe_tasks: Tasks,
) -> list[Send] | str:
    decision = state.get("routing_decision")
    if decision == "revise_script":
        return _script_revision_or_review(state, workflow)
    if decision == "revise_visuals":
        return _visual_revision_or_review(state, workflow)
    if decision == "review":
        return "human_review"
    return keyframe_tasks(state)


def route_keyframe_verdict(state: ContentState, *, keyframe_tasks: Tasks) -> list[Send] | str:
    if state.get("routing_decision") == "retry":
        return keyframe_tasks(state)
    return "human_review"


def route_segment_verdict(state: ContentState, *, segment_tasks: Tasks) -> list[Send] | str:
    decision = state.get("routing_decision")
    if decision == "retry":
        return segment_tasks(state)
    return "human_review" if decision == "review" else "assemble"


def route_director_notes(
    state: ContentState,
) -> Literal["script_writer", "visual_director", "find_references"]:
    routes: dict[str, Literal["script_writer", "visual_director", "find_references"]] = {
        "notes_script": "script_writer",
        "notes_visuals": "visual_director",
        "notes_references": "find_references",
    }
    return routes[state.get("routing_decision", "notes_references")]


def route_human_review(state: ContentState, *, produce: bool) -> HumanReviewRoute:
    request = state.get("human_review_request")
    response = state.get("human_review_response")
    if request is None or response is None or response.action == "stop":
        return "stop"
    if response.action == "revise":
        revision_targets: dict[str, HumanReviewRoute] = {
            "research": "fact_researcher",
            "plan": "editorial_plan",
            "script": "script_writer",
            "fact_check": "script_writer",
            "visuals": "visual_director",
            "listen": "apply_director_notes",
            "storyboard": "apply_director_notes",
            "final_cut": "visual_director",
        }
        return revision_targets[request.stage]
    approval_targets: dict[str, HumanReviewRoute] = {
        "research": "editorial_plan",
        "plan": "script_writer",
        "script": "fact_checker",
        "fact_check": "price_pictures" if produce else "visual_director",
        "visuals": "start_production" if produce else "final_package",
        "listen": "start_keyframes",
        "storyboard": "start_segments",
        "final_cut": "final_package",
    }
    return approval_targets[request.stage]
