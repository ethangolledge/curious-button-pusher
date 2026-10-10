"""The cold viewer: a first-time listener given the narration and nothing else (no plan,
research, claims or theme), so it knows none of what the pipeline knows. What it took from
the story, against the plan, is what the audience missed."""

from content.agents.base import Agent
from content.schemas.audience import AudienceReport
from content.state import ContentState


def listener_input(narration: str) -> dict[str, str]:
    """Everything the cold viewer is given: the narration's words, and nothing else."""
    return {"narration": narration}


class Listener(Agent):
    job = "listener"

    @property
    def model_alias(self) -> str:
        return self.config.listener_model_alias or self.config.model_alias

    def listen(self, state: ContentState) -> ContentState:
        """The cold viewer: a first-time listener hears the narration, and only the
        narration (no plan, research, claims, or fact checks), and says what they took
        from it. The gap between that and the story ledger is what the audience missed."""
        script = state.get("script_package")
        if script is None:
            raise ValueError("The cold viewer needs a script")
        report, call = self.generate(
            listener_input(script.master_script),
            AudienceReport,
            operation="cold_viewer",
            indent=None,
        )
        return {
            "audience_report": report,
            "call_log": [call],
            "events": [
                {
                    "stage": "audience",
                    "message": f"Cold viewer: {len(report.flags)} thing(s) it stumbled on",
                }
            ],
        }
