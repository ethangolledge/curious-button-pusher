"""The Fact-Checking Editor's audit: per-claim findings and the constraints they set."""

from typing import Literal

from content.schemas.base import ImmutableModel

Severity = Literal["none", "minor", "major", "critical"]
SEVERITY_ORDER: tuple[Severity, ...] = ("none", "minor", "major", "critical")


class ClaimFinding(ImmutableModel):
    """One spoken claim checked against the research. A finding never contains wording:
    when a line crosses the evidence, it says where the boundary lies, and the writer, who
    owns every word, decides how to stay inside it."""

    claim: str
    claim_id: str | None
    script_unit_ids: list[str]
    source_ids: list[str]
    status: Literal[
        "passed",
        "failed",
        "unsupported",
        "exaggerated",
        "missing_context",
    ]
    # What the line gets wrong; for a passed finding, why it holds.
    issue: str
    # What the evidence does support, as a limit the line must stay within.
    evidence_boundary: str = ""
    # A qualification the line must carry, by meaning: who says so, as of when.
    required_qualification: str = ""
    # A conclusion the line must not lead a listener to.
    forbidden_implication: str = ""
    severity: Severity = "none"


class FactCheckReport(ImmutableModel):
    claim_findings: list[ClaimFinding]
    non_factual_unit_ids: list[str]
    routing_result: Literal["verified", "revise_script", "human_review"]

    @property
    def severity(self) -> Severity:
        """The worst finding's severity."""
        return max(
            (finding.severity for finding in self.claim_findings),
            key=SEVERITY_ORDER.index,
            default="none",
        )


class UnitAudit(ImmutableModel):
    """A unit's clean audit, reused while its words and cited claims stay the same."""

    findings: list[ClaimFinding]
    non_factual: bool
