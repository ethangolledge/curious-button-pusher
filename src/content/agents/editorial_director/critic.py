"""The critic: reads a whole script or storyboard against the plan and the theme, settles
Jev's doubts, and accepts it or names what must change (never the wording, which is the
writer's). It also sorts a person's untargeted notes onto what they are about."""

from typing import Any, Literal

from content.agents.base import Agent
from content.judging.outcomes import current_judgements, judgement_line
from content.schemas.judgement import Critique
from content.state import CallRecord, ContentState


class Critic(Agent):
    job = "critic"

    @property
    def model_alias(self) -> str:
        return self.config.critic_model_alias or self.config.model_alias

    def critique_script(self, state: ContentState) -> ContentState:
        """The critic reads the whole script, settles Jev's doubts, and accepts or revises."""
        script, brief = state.get("script_package"), state.get("editorial_brief")
        if script is None or brief is None:
            raise ValueError("The script critique requires a script and plan")
        seconds = state.get("unit_seconds", {})
        return self._critique(
            state,
            "script",
            {
                "script": [
                    {
                        "unit_id": unit.unit_id,
                        "text": unit.text,
                        "seconds": seconds.get(unit.unit_id),
                    }
                    for unit in script.script_units
                ],
                "duration_seconds": state["duration_seconds"],
            },
            revision=state.get("script_revision_count", 0),
        )

    def critique_visuals(self, state: ContentState) -> ContentState:
        """The critic reads the whole storyboard against the narration it carries."""
        visuals, script = state.get("visual_package"), state.get("script_package")
        if visuals is None or script is None:
            raise ValueError("The storyboard critique requires scenes and a script")
        texts = {unit.unit_id: unit.text for unit in script.script_units}
        return self._critique(
            state,
            "visuals",
            {
                "scenes": [
                    {
                        "scene_id": scene.scene_id,
                        "narration": " ".join(texts[unit] for unit in scene.script_unit_ids),
                        "anchor": scene.anchor.model_dump(),
                        "camera": scene.camera,
                        "morph_bridge": scene.morph_bridge,
                    }
                    for scene in visuals.scenes
                ]
            },
            revision=state.get("visual_revision_count", 0),
        )

    def sort_notes(self, state: ContentState, text: str) -> tuple[list[str], CallRecord]:
        """Turn a person's untargeted notes into notes on the units, scenes and references
        they are about."""
        script, visuals = state.get("script_package"), state.get("visual_package")
        payload = {
            "stage": "director_notes",
            "notes": text,
            "script": [
                {"unit_id": unit.unit_id, "text": unit.text}
                for unit in (script.script_units if script else [])
            ],
            "scenes": [
                {"scene_id": scene.scene_id, "shows": scene.anchor.subject}
                for scene in (visuals.scenes if visuals else [])
            ],
            "references": [
                {"ref_id": reference.ref_id, "query": reference.query}
                for reference in (visuals.references if visuals else [])
            ],
        }
        critique, call = self.generate(payload, Critique, operation="sort_director_notes")
        return critique.corrections, call

    def _critique(
        self,
        state: ContentState,
        stage: Literal["script", "visuals"],
        artifact: dict[str, Any],
        *,
        revision: int,
    ) -> ContentState:
        brief = state.get("editorial_brief")
        payload = {
            "stage": stage,
            "plan": {
                "central_question": brief.central_question if brief else None,
                "promise": brief.promise if brief else None,
                "story_chain": brief.story_chain if brief else [],
                "arc": [phase.model_dump() for phase in brief.arc] if brief else [],
                "explain": [item.model_dump() for item in brief.explain] if brief else [],
            },
            **artifact,
            "doubts": [
                judgement_line(judgement)
                for judgement in current_judgements(state, stage)
                if judgement.outcome != "pass"
            ],
            "revision": revision,
        }
        critique, call = self.generate(payload, Critique, operation=f"critique_{stage}")
        route = "revise" if critique.verdict == "revise" and critique.corrections else "accept"
        return {
            "current_stage": stage,
            "routing_decision": route,
            "revision_notes": critique.corrections if route == "revise" else [],
            "structural_blockers": False,
            "call_log": [call],
            "events": [{"stage": stage, "message": f"Critic: {route}. {critique.reasoning}"}],
        }
