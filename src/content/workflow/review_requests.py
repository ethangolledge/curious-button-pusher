"""Sign-off and review requests: what the person (or the assistant) is shown at each stop,
built from the run's state, and the Start request with its cost estimate."""

from collections.abc import Callable, Iterable

from langgraph.types import interrupt

from content.choices import RunChoices
from content.config import ContentConfig, WorkflowConfig
from content.judging.outcomes import judgement_line
from content.production.budget import (
    recommended_scenes,
    writing_usd,
)
from content.production.story_sheet import budget_line
from content.review.items import sign_off_items
from content.review.render import (
    render_audience,
    render_fact_check,
    render_plan,
    render_research,
    render_script,
    render_visuals,
)
from content.review.reviewer import HumanReviewer
from content.schemas.media import RenderedAsset
from content.schemas.review import HumanDecision, ReviewRequest, ReviewResponse, ReviewStage
from content.state import ContentState
from content.story.pace import passages
from content.theme import VoiceSpec
from content.workflow.estimate import estimate_table
from content.workflow.gates import (
    judgement_findings,
)
from content.workflow.routing import (
    research_gap_reason,
)


def mark_review_stopped(state: ContentState) -> ContentState:
    request = state.get("human_review_request")
    stage = request.stage if request is not None else state.get("current_stage", "human_review")
    return {
        "current_stage": stage,
        "routing_decision": "human_stop",
        "status": "human_review",
        "events": [{"stage": stage, "message": "Saved and stopped for human review"}],
    }


def _stage_revision(state: ContentState, stage: ReviewStage) -> int:
    if stage == "research":
        return state.get("research_revision_count", 0)
    if stage == "plan":
        return state.get("plan_revision_count", 0)
    if stage in {"visuals", "storyboard", "final_cut"}:
        return state.get("visual_revision_count", 0)
    return state.get("script_revision_count", 0)


def _budget_lines(state: ContentState) -> list[str]:
    budget = state.get("budget")
    return ["", "## Budget", "", budget_line(budget)] if budget else []


def _budget_findings(state: ContentState) -> list[str]:
    budget = state.get("budget")
    if budget is None or budget.projected <= budget.cap:
        return []
    return [
        f"Over budget: the {budget.morphs + 1} pictures and their morphs take the projection "
        f"to ${budget.projected:.2f}, past the ${budget.cap:.2f} cap. Merge scenes (a note "
        "to the storyboard) or raise production.max_usd."
    ]


def _current_passages(state: ContentState) -> list[str]:
    script = state.get("script_package")
    return [passage.passage_id for passage in passages(script.script_units)] if script else []


def _media_findings(assets: Iterable[RenderedAsset]) -> list[str]:
    return [
        judgement_line(judgement)
        for asset in assets
        for judgement in asset.judgements
        if judgement.outcome != "pass"
    ]


def _review_reason(state: ContentState, stage: ReviewStage, workflow: WorkflowConfig) -> str:
    decision = state.get("routing_decision")
    if stage == "research":
        return (
            research_gap_reason(state, workflow=workflow)
            + " Approve to build the story only on what is documented, with anything else "
            "stated as attributed allegation. Revise to steer another research pass with "
            "your feedback (runs research again, roughly $0.30–0.60)."
        )
    if stage == "plan":
        if workflow.review_plan:
            return "Approve, redirect, or stop the creative plan before any narration is written."
        return "Jev flagged the creative plan."
    if stage == "storyboard":
        return (
            "Read the story sheet (narration, scenes, reference images, and the animatic) and "
            "approve before any video is generated. Notes can target U3:, S4:, or R2:."
        )
    if stage == "final_cut":
        return "Watch the finished cut before it is approved."
    if state.get("structural_blockers"):
        return "Structural problems remain after the automatic repair allowance."
    if decision in {"revise", "revise_script"}:
        return "The automatic revision limit was reached."
    if stage == "fact_check":
        report = state.get("fact_check_report")
        if report is not None and report.routing_result == "verified":
            return "Sign off the fact-checked script before the narration is recorded."
        return "The fact check needs a decision before the narration is recorded."
    return "Jev was not confident about a blocking judgement."


def _build_review_request(
    state: ContentState, workflow: WorkflowConfig, voice: VoiceSpec
) -> ReviewRequest:
    stage = state.get("current_stage")
    brief = state.get("editorial_brief")
    script = state.get("script_package")
    report = state.get("fact_check_report")
    visuals = state.get("visual_package")
    review_stage: ReviewStage
    findings: list[str]
    attachments: list[str] = []
    approvable = not state.get("structural_blockers", False)
    research = state.get("research_pack")
    if stage == "research" and research is not None:
        review_stage = "research"
        snapshot = render_research(research)
        findings = [*research.integrity_warnings, *research.missing_evidence]
        # With no claims at all there is nothing documented to build on.
        approvable = research.classified_claim_count > 0
    elif stage == "plan" and brief is not None:
        review_stage = "plan"
        snapshot = render_plan(brief, state.get("story_size"))
        findings = judgement_findings(state, "plan")
    elif stage == "script" and script is not None:
        review_stage = "script"
        snapshot = render_script(script)
        findings = judgement_findings(state, "script")
    elif stage == "fact_check" and script is not None and report is not None:
        review_stage = "fact_check"
        heard = state.get("audience_report")
        snapshot = [
            *render_script(script),
            *render_fact_check(report),
            *(render_audience(heard, brief) if heard is not None and brief is not None else []),
        ]
        findings = [
            *(
                f"{finding.status}: {finding.claim} — {finding.issue}"
                for finding in report.claim_findings
                if finding.status != "passed"
            ),
            # What the listener test still found, when the revisions ran out before it passed.
            *(state.get("revision_notes", []) if heard is not None else []),
        ]
    elif stage == "visuals" and visuals is not None:
        review_stage = "visuals"
        snapshot = render_visuals(visuals)
        findings = judgement_findings(state, "visuals")
    elif stage == "listen" and (timeline := state.get("timeline")) is not None:
        review_stage = "listen"
        clips = state.get("narration", {})
        snapshot = [
            "## Listen before any picture is drawn",
            "",
            *(
                f"- **{clip.passage_id}** ({clip.words_per_minute:.0f} wpm target, "
                f"{clip.tempo:.2f}×): {clip.spoken_text}"
                for clip in clips.values()
                if clip.passage_id in _current_passages(state)
            ),
            *_budget_lines(state),
        ]
        # What the listen checks heard in these takes: read fresh from the current clips,
        # so a re-recorded passage's old warning never lingers.
        findings = [
            *(
                issue
                for clip in clips.values()
                if clip.passage_id in _current_passages(state)
                for issue in clip.issues
            ),
            *_budget_findings(state),
        ]
        attachments = [state.get("listen_mix") or "", timeline.narration_path]
    elif stage == "storyboard" and visuals is not None:
        review_stage = "storyboard"
        keyframes = state.get("keyframes", {})
        snapshot = [*render_visuals(visuals), *_budget_lines(state)]
        findings = [
            *_media_findings(keyframes[scene.scene_id] for scene in visuals.scenes),
            *_budget_findings(state),
        ]
        timeline = state.get("timeline")
        attachments = [
            state.get("story_sheet") or "",
            state.get("animatic") or "",
            state.get("contact_sheet") or "",
            *([timeline.narration_path] if timeline else []),
            *(keyframes[scene.scene_id].path for scene in visuals.scenes),
        ]
    elif stage == "final_cut" and (production := state.get("production")) is not None:
        review_stage = "final_cut"
        segments = state.get("segments", {})
        snapshot = [f"## Final cut — {production.duration:.1f} s", "", production.video_path]
        timeline = state.get("timeline")
        findings = _media_findings(
            segments[transition.from_scene_id]
            for transition in (timeline.transitions if timeline else [])
            if transition.from_scene_id in segments
        )
        attachments = [production.video_path, production.contact_sheet_path]
    else:
        raise ValueError(f"Unsupported human-review stage: {stage}")

    items, unlocks = sign_off_items(state, review_stage, voice)
    return ReviewRequest(
        stage=review_stage,
        reason=_review_reason(state, review_stage, workflow),
        items=items,
        unlocks=unlocks,
        findings=list(
            dict.fromkeys(
                [*findings, *state.get("warnings", []), *state.get("script_warnings", [])]
            )
        ),
        required_changes=state.get("revision_notes", []),
        snapshot="\n".join(snapshot),
        attachments=[path for path in attachments if path],
        approvable=approvable,
    )


def request_human_review(
    state: ContentState,
    *,
    workflow: WorkflowConfig,
    voice: VoiceSpec,
) -> ContentState:
    # Everything before interrupt() is pure: LangGraph re-runs this node on resume.
    request = _build_review_request(state, workflow, voice)
    response = ReviewResponse.model_validate(interrupt(request.model_dump()))
    if response.action == "approve" and not request.approvable:
        raise ValueError("Approval is not permitted while structural problems remain")
    decision = HumanDecision(
        stage=request.stage,
        revision=_stage_revision(state, request.stage),
        action=response.action,
        feedback=response.feedback,
        script_revision=state.get("script_revision_count", 0),
        decided_by=response.decided_by,
    )
    # A revision carries only the person's notes: the automatic findings they saw are
    # theirs to pass on or not. A writer given both rewrote passages the person approved.
    update: ContentState = {"revision_notes": []} if response.action == "revise" else {}
    return {
        **update,
        "human_review_request": request,
        "human_review_response": response,
        "human_review_feedback": response.feedback,
        "human_decisions": [decision],
        "routing_decision": f"human_{response.action}",
        "status": "running",
        "events": [{"stage": request.stage, "message": f"Human decision: {response.action}"}],
    }


def start_request(
    topic: str,
    brief: str | None,
    config: ContentConfig,
    choices: RunChoices | None = None,
) -> ReviewRequest:
    """The Start sign-off: what will be made, in which shape, and roughly what it will
    cost, before anything is spent. `config` is already configured for the video."""
    choices = choices or RunChoices()
    shape = config.theme.spec.format
    seconds = choices.seconds or int(
        min(max(config.content.default_duration_seconds, shape.min_seconds), shape.max_seconds)
    )
    video = [
        f"- Format: {shape.aspect_ratio} ({shape.platforms or 'the channel default'}).",
        f"- Length: about {seconds // 60} min {seconds % 60:02d} s, at most "
        f"{shape.max_seconds // 60:.0f} min {shape.max_seconds % 60:02.0f} s.",
        f"- Scenes: {choices.scenes or 'as the story needs'}"
        + ("" if choices.scenes else f" (about {recommended_scenes(seconds)} recommended)")
        + ".",
        *(
            ["- You also sign off the story plan before any script is written."]
            if config.workflow.review_plan
            else []
        ),
    ]
    low, high = writing_usd(seconds)
    production = config.production
    cost = [
        f"- Research to a fact-checked script and storyboard: about ${low:.2f}–${high:.2f}.",
        *(
            [f"- The whole run is capped at ${production.max_usd:.2f}."]
            if production is not None
            else ["- No video: this configuration stops at the written package."]
        ),
        "- You sign off again before the narration, the pictures and the morphs are paid for.",
    ]
    return ReviewRequest(
        stage="brief",
        reason="Approve to start. Nothing has been spent yet.",
        snapshot="\n".join(
            [
                "## Topic",
                "",
                topic,
                "",
                "## Brief",
                "",
                brief or "None given.",
                "",
                "## This video",
                "",
                *video,
                "",
                "## Cost",
                "",
                *cost,
                *(
                    ["", estimate_table(config, seconds, choices.scenes)]
                    if config.production is not None
                    else []
                ),
            ]
        ),
    )


def confirm_start(
    topic: str,
    brief: str | None,
    config: ContentConfig,
    reviewer: HumanReviewer,
    save_brief: Callable[[str | None], None] | None = None,
    choices: RunChoices | None = None,
) -> tuple[ReviewResponse, str | None]:
    """Ask for the Start sign-off; a revision adds the person's note to the brief (saved
    before asking again) and asks again. Returns the final answer and the brief to run with."""
    while True:
        response = reviewer.review(start_request(topic, brief, config, choices))
        if response.action != "revise":
            return response, brief
        brief = "\n\n".join(part for part in (brief, response.feedback) if part)
        if save_brief is not None:
            save_brief(brief)
