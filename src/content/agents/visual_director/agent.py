"""The Visual Director: turns the approved narration into a storyboard of scenes, each with its
anchor, focus, camera, motion and the bridge into the next, and the reference photographs it
needs."""

from typing import Any

from content.agents.base import Agent, load_prompt
from content.schemas.staging import StagedVisualPackage
from content.schemas.visuals import Scene, VisualPackage
from content.state import ContentState, RevisionRecord, merge_warnings


class VisualDirector(Agent):
    # What the storyboard is made of; a director that can stage scenes in 3D returns more.
    storyboard: type[VisualPackage] = VisualPackage

    def extra_input(self) -> dict[str, Any]:
        """What this kind of director is shown besides the story."""
        return {}

    def __call__(self, state: ContentState) -> ContentState:
        research_pack = state.get("research_pack")
        editorial_brief = state.get("editorial_brief")
        script_package = state.get("script_package")
        if research_pack is None or editorial_brief is None or script_package is None:
            raise ValueError("Visual direction requires research, a creative plan, and a script")

        previous = state.get("visual_package")
        revision_count = state.get("visual_revision_count", 0)
        revisions: list[RevisionRecord] = []
        waiting = state.get("director_notes", [])
        # Scene notes a person left while the narration was being revised come here now.
        notes = [*state.get("revision_notes", []), *(n for n in waiting if n.startswith("S"))]
        feedback = state.get("human_review_feedback")
        if previous is not None:
            revision_count += 1
            reason = "; ".join([*notes, *([feedback] if feedback else [])])
            revisions.append(
                {
                    "stage": "visuals",
                    "revision_number": revision_count,
                    "reason": reason or "A revision was requested.",
                }
            )

        generated_package, call = self.generate(
            {
                "topic": state["topic"],
                "creative_plan": {
                    "central_question": editorial_brief.central_question,
                    "arc": editorial_brief.arc,
                    "visual_principles": editorial_brief.visual_principles,
                    "style_boundaries": editorial_brief.style_boundaries,
                },
                "approved_script_units": script_package.script_units,
                "predicted_unit_seconds": state.get("unit_seconds", {}),
                # How each line lands on a listener; each scene's space follows it.
                "unit_reactions": {
                    unit_id: feeling.label()
                    for unit_id, feeling in state.get("unit_feelings", {}).items()
                },
                "duration_seconds": state["duration_seconds"],
                # Each scene costs a keyframe and a morph: the most the budget affords.
                "most_scenes": state.get("scene_allowance"),
                # The number the person chose for this video, when they chose one.
                "scenes_wanted": state.get("scenes_wanted"),
                "aspect_ratio": state["aspect_ratio"],
                "previous_storyboard": previous,
                "corrections": notes if previous is not None else [],
                "human_review_feedback": feedback,
                "visual_revision_number": revision_count,
                **self.extra_input(),
            },
            self.storyboard,
            operation="storyboard" if previous is None else "storyboard_revision",
        )
        package, normalization_warnings = self._normalize_scenes(generated_package)
        return {
            "visual_package": package,
            "final_package": None,
            "human_review_feedback": None,
            "revision_notes": [],
            "director_notes": [note for note in waiting if not note.startswith("S")],
            "visual_revision_count": revision_count,
            "current_stage": "visuals",
            "status": "running",
            "call_log": [call],
            "events": [{"stage": "visuals", "message": "Storyboard created"}],
            "revision_history": revisions,
            "warnings": merge_warnings(state.get("warnings", []), normalization_warnings),
        }

    @staticmethod
    def _normalize_scenes(package: VisualPackage) -> tuple[VisualPackage, list[str]]:
        normalized: list[Scene] = []
        changed = False
        for index, scene in enumerate(package.scenes, start=1):
            updated = scene.model_copy(
                update={
                    "scene_id": f"S{index}",
                    "script_unit_ids": list(dict.fromkeys(scene.script_unit_ids)),
                }
            )
            normalized.append(updated)
            changed = changed or updated != scene
        if not changed:
            return package, []
        return (
            package.model_copy(update={"scenes": normalized}),
            ["Scene IDs or repeated script-unit references were normalized."],
        )


class StagedVisualDirector(VisualDirector):
    """The Visual Director for a channel that stages scenes in 3D (`production.pictures`
    "staged"): the same storyboard, and for each scene the toolkit can show, its 3D shot,
    chosen from the catalogue of blocks and models (`staging_prompt.md`, `docs/staging.md`).
    Scenes it cannot stage stay keyframes, and say what was missing."""

    storyboard = StagedVisualPackage

    def __init__(self, *, catalogue: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.catalogue = catalogue

    def prompt(self, job: str | None = None) -> str:
        own = load_prompt(self.config.prompt.with_name("staging_prompt.md"))
        return "\n\n".join(part for part in (super().prompt(job), own) if part)

    def extra_input(self) -> dict[str, Any]:
        return {"staging_catalogue": self.catalogue}
