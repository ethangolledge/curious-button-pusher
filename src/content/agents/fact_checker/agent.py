"""The Fact-Checking Editor: audits each narration unit against the claims it cites and sets
what may be said (an evidence boundary, a required qualification, a forbidden implication),
never the wording. Unchanged units keep their audit; a few changed lines get the light audit
first."""

import hashlib
from typing import Any

from content.agents.base import Agent
from content.schemas.fact_check import ClaimFinding, FactCheckReport, UnitAudit
from content.schemas.plan import EditorialBrief
from content.schemas.research import ResearchPack
from content.schemas.script import ScriptUnit
from content.state import CallRecord, ContentState, merge_warnings
from content.story.ledger import fact_check_issues

# Findings that make a line false or misleading. Missing context is advisory: short-form
# narration compresses by design, and treating every omission as an error loops forever.
BLOCKING_STATUSES = frozenset({"failed", "unsupported", "exaggerated"})
# Changed lines audited at the light model's effort; more, or any line it does not pass,
# get the full audit.
LIGHT_AUDIT_UNITS = 3


class FactChecker(Agent):
    def __call__(self, state: ContentState) -> ContentState:
        research = state.get("research_pack")
        brief = state.get("editorial_brief")
        script = state.get("script_package")
        if research is None or brief is None or script is None:
            raise ValueError("Fact checking requires research, a creative plan, and a script")

        # Units whose words and citations already passed an audit are not audited again.
        audits = state.get("unit_audits", {})
        evidence_version = hashlib.sha256(research.model_dump_json().encode()).hexdigest()[:12]
        keys = {unit.unit_id: audit_key(unit, evidence_version) for unit in script.script_units}
        to_audit = [unit for unit in script.script_units if keys[unit.unit_id] not in audits]
        calls: list[CallRecord] = []
        audited = FactCheckReport(
            claim_findings=[],
            non_factual_unit_ids=[],
            routing_result="verified",
        )
        if to_audit:
            payload = {
                "topic": state["topic"],
                "full_narration_for_context": script.master_script,
                "units_to_audit": to_audit,
                "already_verified_unit_ids": [
                    unit.unit_id for unit in script.script_units if unit not in to_audit
                ],
                "evidence": _relevant_evidence(research, brief, to_audit),
                "fact_check_priorities": brief.fact_check_priorities,
                "required_context": brief.required_context,
            }
            light = self.config.light_model_alias
            if light is not None and len(to_audit) <= LIGHT_AUDIT_UNITS:
                audited, call = self.generate(
                    payload, FactCheckReport, operation="fact_check_light", model_alias=light
                )
                calls.append(call)
            if not calls or any(f.status != "passed" for f in audited.claim_findings):
                # A finding from the light audit is confirmed at full effort before it
                # constrains the writer or reaches the person.
                audited, call = self.generate(payload, FactCheckReport, operation="fact_check")
                calls.append(call)

        report = _with_reused_audits(audited, script.script_units, keys, audits)
        report, advisory = decide_route(report)
        issues = fact_check_issues(report, script, research)
        blocking = [f for f in report.claim_findings if f.status in BLOCKING_STATUSES]
        return {
            "fact_check_report": report,
            # Every boundary a line has crossed stays in force for every later rewrite.
            "fact_constraints": blocking,
            "unit_audits": _clean_audits(audited, to_audit, keys),
            "visual_package": None,
            "final_package": None,
            "revision_notes": issues or list(dict.fromkeys(constraint_line(f) for f in blocking)),
            "structural_blockers": bool(issues),
            "current_stage": "fact_check",
            "routing_decision": "human_review" if issues else report.routing_result,
            "status": "running",
            "call_log": calls,
            "events": [
                {
                    "stage": "fact_check",
                    "message": (
                        f"Routing decision: {report.routing_result}; audited "
                        f"{len(to_audit)} of {len(script.script_units)} units"
                    ),
                }
            ],
            "script_warnings": merge_warnings(
                state.get("script_warnings", []), [*advisory, *issues]
            ),
        }


def audit_key(unit: ScriptUnit, evidence_version: str) -> str:
    """Identifies a unit's words and citations against one version of the research; the
    unit's position does not matter."""
    content = "\x1f".join([unit.text.strip(), ",".join(sorted(unit.claim_ids)), evidence_version])
    return hashlib.sha256(content.encode()).hexdigest()[:24]


def constraint_line(finding: ClaimFinding) -> str:
    """A crossed evidence boundary as an instruction about meaning, never wording: the
    writer keeps the line's voice and stays inside the boundary."""
    units = ", ".join(finding.script_unit_ids) or "the narration"
    parts = [
        f"{units} ({finding.status.replace('_', ' ')}): {finding.issue}",
        f"The evidence supports: {finding.evidence_boundary}" if finding.evidence_boundary else "",
        f"It must carry: {finding.required_qualification}"
        if finding.required_qualification
        else "",
        f"It must not imply: {finding.forbidden_implication}"
        if finding.forbidden_implication
        else "",
    ]
    return " ".join(part.rstrip(".") + "." for part in parts if part)


def decide_route(report: FactCheckReport) -> tuple[FactCheckReport, list[str]]:
    """The route follows the findings: only false or misleading lines force a revision.

    Missing context is returned as advisory notes instead. The auditor may still ask for a
    person when the research cannot settle a material point."""
    blocking = [f for f in report.claim_findings if f.status in BLOCKING_STATUSES]
    advisory = [
        f"Context note: {finding.claim}: {finding.issue}"
        for finding in report.claim_findings
        if finding.status == "missing_context"
    ]
    if report.routing_result == "human_review":
        route = "human_review"
    elif blocking:
        route = "human_review" if report.severity == "critical" else "revise_script"
    else:
        route = "verified"
    return report.model_copy(update={"routing_result": route}), advisory


def _relevant_evidence(
    research: ResearchPack,
    brief: EditorialBrief,
    units: list[ScriptUnit],
) -> dict[str, Any]:
    """The claims the audited units cite or the plan selected, and only their sources."""
    wanted = {
        *(claim_id for unit in units for claim_id in unit.claim_ids),
        *brief.required_claim_ids,
        *brief.supporting_claim_ids,
    }
    claims = [claim for claim in research.all_claims if claim.claim_id in wanted]
    sources = {source_id for claim in claims for source_id in claim.source_ids}
    return {
        "research_summary": research.research_summary,
        "claims": claims,
        "sources": [s for s in research.source_references if s.source_id in sources],
        "safe_wording": research.safe_wording,
        "factual_limitations": research.factual_limitations,
    }


def _with_reused_audits(
    audited: FactCheckReport,
    units: list[ScriptUnit],
    keys: dict[str, str],
    audits: dict[str, UnitAudit],
) -> FactCheckReport:
    findings = list(audited.claim_findings)
    non_factual = list(audited.non_factual_unit_ids)
    for unit in units:
        reused = audits.get(keys[unit.unit_id])
        if reused is None:
            continue
        if reused.non_factual:
            non_factual.append(unit.unit_id)
        findings += [
            finding.model_copy(update={"script_unit_ids": [unit.unit_id]})
            for finding in reused.findings
        ]
    return audited.model_copy(
        update={
            "claim_findings": findings,
            "non_factual_unit_ids": list(dict.fromkeys(non_factual)),
        }
    )


def _clean_audits(
    audited: FactCheckReport,
    units: list[ScriptUnit],
    keys: dict[str, str],
) -> dict[str, UnitAudit]:
    """Remember the audit of every unit that came through without a blocking finding."""
    clean: dict[str, UnitAudit] = {}
    for unit in units:
        findings: list[ClaimFinding] = [
            f for f in audited.claim_findings if unit.unit_id in f.script_unit_ids
        ]
        if any(f.status in BLOCKING_STATUSES for f in findings):
            continue
        non_factual = unit.unit_id in audited.non_factual_unit_ids
        if findings or non_factual:
            clean[keys[unit.unit_id]] = UnitAudit(findings=findings, non_factual=non_factual)
    return clean
