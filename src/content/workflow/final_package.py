"""The run's last node: everything approved, gathered into the final package."""

from content.schemas.package import FinalContentPackage, ScenePrompts
from content.schemas.review import ReviewStage
from content.schemas.script import ScriptPackage
from content.state import ContentState
from content.story.field import scene_prompts, story_fields
from content.story.ledger import fact_check_issues, script_issues, visual_issues
from content.theme import Theme


def _approved_by_person(state: ContentState, stage: ReviewStage, revision: int) -> bool:
    return any(
        decision.stage == stage and decision.revision == revision and decision.action == "approve"
        for decision in state.get("human_decisions", [])
    )


def _narration_prompt(script: ScriptPackage, duration_seconds: int) -> str:
    pronunciation = (
        "\n".join(f"- {note}" for note in script.voice_direction.pronunciation_notes)
        or "- No special pronunciation notes."
    )
    return "\n".join(
        [
            "Generate one continuous narration performance using the exact script below.",
            "Do not rewrite, summarise, split, or add words.",
            f"Target duration: approximately {duration_seconds} seconds.",
            f"Tone: {script.voice_direction.tone}",
            f"Pace: {script.voice_direction.pace}",
            f"Delivery: {script.voice_direction.delivery}",
            "Pronunciation notes:",
            pronunciation,
            "",
            "SCRIPT",
            script.master_script,
        ]
    )


def assemble_final_package(
    state: ContentState,
    *,
    theme: Theme,
    produced: bool,
) -> ContentState:
    research = state.get("research_pack")
    brief = state.get("editorial_brief")
    script = state.get("script_package")
    fact_check = state.get("fact_check_report")
    visuals = state.get("visual_package")
    if research is None or brief is None or script is None or fact_check is None or visuals is None:
        raise ValueError("Final package assembly requires every workflow artifact")
    # Nothing, including a human approval, can carry a structural problem into the package.
    spec = theme.spec
    blockers = [
        *script_issues(script, brief, research),
        *fact_check_issues(fact_check, script, research),
        *visual_issues(visuals, script, spec.visual.camera_moves),
    ]
    if blockers:
        raise ValueError("Final package blocked by structural problems: " + " ".join(blockers))
    if fact_check.routing_result != "verified" and not _approved_by_person(
        state, "fact_check", state.get("script_revision_count", 0)
    ):
        raise ValueError(
            "Final package requires a verified fact check or a recorded human approval of it"
        )
    production = state.get("production")
    if produced and (
        production is None
        or not _approved_by_person(state, "final_cut", state.get("visual_revision_count", 0))
    ):
        raise ValueError("Final package requires a finished cut approved by a person")

    package = FinalContentPackage(
        topic=state["topic"],
        duration_seconds=state["duration_seconds"],
        aspect_ratio=state["aspect_ratio"],
        research_pack=research,
        editorial_brief=brief,
        approved_script=script,
        narration_prompt=_narration_prompt(script, state["duration_seconds"]),
        fact_check_report=fact_check,
        visual_plan=visuals,
        scene_prompts=[
            ScenePrompts(scene_id=scene_id, keyframe_prompt=keyframe, segment_prompt=segment)
            for scene_id, keyframe, segment in scene_prompts(
                theme,
                visuals,
                story_fields(
                    script,
                    visuals,
                    research,
                    state.get("unit_feelings", {}),
                    state.get("unit_seconds", {}),
                ),
            )
        ],
        production=production if produced else None,
        human_decisions=state.get("human_decisions", []),
        warnings=[*state.get("warnings", []), *state.get("script_warnings", [])],
        approval_status="approved",
    )
    return {
        "final_package": package,
        "current_stage": "final_package",
        "routing_decision": "approved",
        "status": "approved",
        "events": [{"stage": "final_package", "message": "Package assembled"}],
    }
