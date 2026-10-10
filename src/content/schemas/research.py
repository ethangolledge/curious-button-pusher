"""What the Fact Researcher finds: sources, classified claims, the cast and the timeline."""

from typing import Literal

from pydantic import Field

from content.schemas.base import ImmutableModel


class ResearchClaim(ImmutableModel):
    claim_id: str
    claim: str
    source_ids: list[str] = Field(default_factory=list)
    qualification: str | None = None


class EventLink(ImmutableModel):
    """A connection between two claims that the sources themselves make. Only `led_to`
    may be told as cause; the others are told as sequence or contrast."""

    from_claim_id: str
    to_claim_id: str
    relation: Literal["led_to", "in_response_to", "despite", "after"]
    source_ids: list[str] = Field(default_factory=list)


class CastMember(ImmutableModel):
    """Someone the story is about: what they wanted or said (attributed), and the claims
    recording what they did."""

    name: str
    role: str
    wanted: str
    claim_ids: list[str] = Field(default_factory=list)


class TimelineEvent(ImmutableModel):
    date_or_period: str
    event: str
    claim_ids: list[str]


class SourceComparison(ImmutableModel):
    subject: str
    source_ids: list[str]
    consensus: str
    disagreements: list[str] = Field(default_factory=list)
    significance: str


class SourceMaterial(ImmutableModel):
    source_id: str
    title: str
    content: str
    url: str | None = None


class SourceReference(ImmutableModel):
    source_id: str
    title: str
    url: str | None = None
    source_type: Literal[
        "primary",
        "official",
        "academic",
        "quality_secondary",
        "other",
    ]
    credibility_notes: str
    limitations: list[str] = Field(default_factory=list)


class ResearchPack(ImmutableModel):
    research_summary: str
    timeline: list[TimelineEvent]
    # The story's material beyond the bare facts: who wanted what, and which events the
    # sources themselves connect.
    cast: list[CastMember] = Field(default_factory=list)
    links: list[EventLink] = Field(default_factory=list)
    verified_facts: list[ResearchClaim]
    reported_claims: list[ResearchClaim]
    disputed_claims: list[ResearchClaim]
    inferences: list[ResearchClaim]
    unsupported_claims: list[ResearchClaim]
    source_references: list[SourceReference]
    source_comparisons: list[SourceComparison]
    contradictions: list[str]
    missing_evidence: list[str]
    factual_limitations: list[str]
    safe_wording: list[str]
    research_confidence: Literal["low", "medium", "high"]
    evidence_status: Literal["source_backed", "provisional", "unverified"]
    research_status: Literal["sufficient", "revise", "insufficient"]
    # One or two sentences: why this evidence and research status, and what is missing.
    status_reason: str = ""

    @property
    def all_claims(self) -> list[ResearchClaim]:
        return [
            *self.verified_facts,
            *self.reported_claims,
            *self.disputed_claims,
            *self.inferences,
            *self.unsupported_claims,
        ]

    @property
    def classified_claim_count(self) -> int:
        return len(self.all_claims)

    @property
    def integrity_warnings(self) -> list[str]:
        warnings: list[str] = []
        claim_ids = [claim.claim_id for claim in self.all_claims]
        if len(claim_ids) != len(set(claim_ids)):
            warnings.append("Research claim IDs are not unique.")

        source_ids = [source.source_id for source in self.source_references]
        if len(source_ids) != len(set(source_ids)):
            warnings.append("Research source IDs are not unique.")

        known_claims = set(claim_ids)
        known_sources = set(source_ids)
        referenced_sources = {
            source_id for claim in self.all_claims for source_id in claim.source_ids
        }
        compared_sources = {
            source_id
            for comparison in self.source_comparisons
            for source_id in comparison.source_ids
        }
        timeline_claims = {claim_id for event in self.timeline for claim_id in event.claim_ids}

        unknown_sources = (referenced_sources | compared_sources) - known_sources
        if unknown_sources:
            warnings.append(
                "Research references unknown source IDs: "
                + ", ".join(sorted(unknown_sources))
                + "."
            )

        unknown_claims = timeline_claims - known_claims
        if unknown_claims:
            warnings.append(
                "Research references unknown claim IDs: " + ", ".join(sorted(unknown_claims)) + "."
            )

        if self.evidence_status == "source_backed":
            if not self.source_references:
                warnings.append(
                    "Research is labelled source-backed but contains no source references."
                )
            if any(not claim.source_ids for claim in self.verified_facts):
                warnings.append("Some verified facts do not contain supporting source IDs.")
        if self.evidence_status == "unverified" and self.research_status == "sufficient":
            warnings.append("Research is marked sufficient even though its evidence is unverified.")
        return warnings
