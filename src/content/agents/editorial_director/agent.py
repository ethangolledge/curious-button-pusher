"""The Editorial Director, as Story Architect: it plans the story (the ledger of beats
and claims) and decides what happens to a required claim the first-time listener stumbled
on. Its other jobs sit beside it: the critic (`critic.py`) and the listener test
(`listener.py`)."""

from content.agents.base import Agent
from content.schemas.audience import StoryDecisions
from content.schemas.plan import ClaimPlan, EditorialBrief
from content.schemas.research import ResearchPack
from content.state import ContentState, RevisionRecord, merge_warnings
from content.story.ledger import apply_story_decisions, listener_findings


class EditorialDirector(Agent):
    """Owns the creative plan, and the only one who may drop a required claim."""

    def create_plan(self, state: ContentState) -> ContentState:
        research_pack = state.get("research_pack")
        if research_pack is None:
            raise ValueError("The creative plan requires a research pack")
        previous = state.get("editorial_brief")
        revision_count = state.get("plan_revision_count", 0)
        revisions: list[RevisionRecord] = []
        feedback = state.get("human_review_feedback")
        if previous is not None:
            revision_count += 1
            revisions.append(
                {
                    "stage": "plan",
                    "revision_number": revision_count,
                    "reason": feedback or "Human review requested a revised plan.",
                }
            )
        generated_brief, call = self.generate(
            {
                "topic": state["topic"],
                "user_instructions": state.get("user_instructions"),
                "human_review_feedback": feedback,
                "previous_plan": previous,
                "research_pack": research_pack,
                "output_requirements": {
                    "preferred_seconds": state["duration_seconds"],
                    "words_at_preferred_length": state["word_budget"],
                    "aspect_ratio": state["aspect_ratio"],
                },
            },
            EditorialBrief,
            operation="plan",
        )
        brief, reference_warnings = self._normalize_brief_claims(generated_brief, research_pack)
        return {
            "editorial_brief": brief,
            "script_package": None,
            "fact_check_report": None,
            "visual_package": None,
            "final_package": None,
            "human_review_feedback": None,
            "revision_notes": [],
            "structural_blockers": False,
            "plan_revision_count": revision_count,
            "current_stage": "plan",
            "status": "running",
            "call_log": [call],
            "events": [{"stage": "plan", "message": f"Creative plan: {brief.central_question}"}],
            "revision_history": revisions,
            "warnings": merge_warnings(state.get("warnings", []), reference_warnings),
        }

    def decide_story(self, state: ContentState) -> ContentState:
        """The Story Architect's call on required claims a listener found confusing or
        unrelated: keep, move, simplify, merge, demote, or cut. Only the Architect may
        drop a required claim, and doing so changes the plan, on the record."""
        brief, script, report = (
            state.get("editorial_brief"),
            state.get("script_package"),
            state.get("audience_report"),
        )
        if brief is None or script is None or report is None:
            raise ValueError("Story decisions need the plan, the script, and the listener test")
        units = {unit.unit_id: unit for unit in script.script_units}
        flagged = [
            {
                "claim": plan.model_dump(),
                "line": units[finding.unit_id].text,
                "listener": {"kind": finding.kind, **finding.flag.model_dump()},
            }
            for finding in listener_findings(report, script.script_units)
            if finding.unit_id is not None
            for claim_id in units[finding.unit_id].claim_ids
            if (plan := brief.claim_plan(claim_id)) is not None
            and claim_id in brief.required_claim_ids
        ]
        payload = {
            "stage": "story_decisions",
            "central_question": brief.central_question,
            "story_chain": brief.story_chain,
            "arc": [beat.model_dump() for beat in brief.arc],
            "flagged_claims": flagged,
        }
        decisions, call = self.generate(payload, StoryDecisions, operation="story_decisions")
        changed = [d for d in decisions.decisions if d.action in {"cut", "demote", "move"}]
        return {
            "editorial_brief": apply_story_decisions(brief, decisions),
            "revision_notes": [
                *state.get("revision_notes", []),
                *(f"{d.claim_id} ({d.action}): {d.note}" for d in decisions.decisions),
            ],
            "call_log": [call],
            "revision_history": [
                RevisionRecord(
                    stage="plan",
                    revision_number=state.get("plan_revision_count", 0),
                    reason=f"{d.claim_id}: {d.action} after the listener test. {d.note}",
                )
                for d in changed
            ],
            "events": [
                {
                    "stage": "plan",
                    "message": f"Story decisions: {decisions.reasoning}",
                }
            ],
        }

    @staticmethod
    def _normalize_brief_claims(
        brief: EditorialBrief,
        research: ResearchPack,
    ) -> tuple[EditorialBrief, list[str]]:
        """Keep the ledger to claims the research has, one entry each, and give every claim
        an explanation rests on a place in it, so the writer has it and the fact checker
        checks the plain version against it."""
        warnings: list[str] = []
        known = {claim.claim_id for claim in research.all_claims}
        explained = [c for explanation in brief.explain for c in explanation.claim_ids]
        unknown = ({plan.claim_id for plan in brief.claims} | set(explained)) - known
        if unknown:
            warnings.append(
                "Editorial brief references unknown research claims: "
                + ", ".join(sorted(unknown))
                + ". Unknown IDs were removed."
            )
        ledger: dict[str, ClaimPlan] = {}
        for plan in brief.claims:
            if plan.claim_id in known:
                ledger.setdefault(plan.claim_id, plan)
        for claim_id in explained:
            if claim_id in known and claim_id not in ledger:
                ledger[claim_id] = ClaimPlan(
                    claim_id=claim_id,
                    story_role="supporting_evidence",
                    narrative_job="Explains a term the listener needs.",
                    meaning="",
                    requires_explanation=False,
                )
        explain = [
            explanation.model_copy(
                update={"claim_ids": [c for c in explanation.claim_ids if c in known]}
            )
            for explanation in brief.explain
        ]
        normalized = brief.model_copy(update={"claims": list(ledger.values()), "explain": explain})
        return normalized, warnings
