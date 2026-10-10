"""The Fact Researcher: the only agent with web search. It classifies what the sources say
(verified, reported, disputed, inference, unsupported) into the research pack every later
stage cites."""

from content.agents.base import Agent
from content.schemas.research import ResearchPack
from content.state import ContentState, RevisionRecord, WorkflowEvent


class FactResearcher(Agent):
    def __call__(self, state: ContentState) -> ContentState:
        previous = state.get("research_pack")
        revision_count = state.get("research_revision_count", 0)
        revisions: list[RevisionRecord] = []
        feedback = state.get("human_review_feedback")
        if previous is not None:
            revision_count += 1
            reason = (
                "; ".join([*previous.integrity_warnings, *([feedback] if feedback else [])])
                or "Research gate requested another pass over the available material."
            )
            revisions.append(
                {"stage": "research", "revision_number": revision_count, "reason": reason}
            )

        pack, call = self.generate(
            {
                "topic": state["topic"],
                "source_material": state.get("source_material", []),
                "user_instructions": state.get("user_instructions"),
                "previous_research_pack": previous,
                "integrity_problems_to_repair": previous.integrity_warnings if previous else [],
                "human_review_feedback": feedback,
                "research_revision_number": revision_count,
            },
            ResearchPack,
            operation="research",
            web_search=True,
        )
        warnings = list(pack.integrity_warnings)
        if pack.evidence_status != "source_backed":
            warnings.append(
                f"Research is {pack.evidence_status}; it has not been independently verified."
            )
        events: list[WorkflowEvent] = [
            {
                "stage": "research",
                "message": (
                    f"Research status: {pack.research_status}; "
                    f"{pack.classified_claim_count} classified claims from "
                    f"{len(pack.source_references)} sources"
                ),
            }
        ]
        return {
            "research_pack": pack,
            "editorial_brief": None,
            "script_package": None,
            "fact_check_report": None,
            "visual_package": None,
            "final_package": None,
            "research_revision_count": revision_count,
            "current_stage": "research",
            "status": "running",
            "call_log": [call],
            "events": events,
            "warnings": warnings,
            "revision_history": revisions,
        }
