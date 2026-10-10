"""The first-time listener's report, and the story decisions it leads to."""

from typing import Literal

from content.schemas.base import ImmutableModel


class AudienceFlag(ImmutableModel):
    """Something the cold viewer stumbled on, quoted from the narration."""

    quote: str
    note: str


class AudienceReport(ImmutableModel):
    """What a first-time listener took from the narration alone, with no plan, research,
    or claims: the test of whether the story was told, not merely written."""

    about: str
    what_happened: str
    why_it_happened: str
    why_it_matters: str
    key_facts: list[str]
    question: str
    unresolved: str
    confusions: list[AudienceFlag]
    unrelated_facts: list[AudienceFlag]
    # Terms that needed knowledge the listener did not have; `quote` is the term.
    unclear_terms: list[AudienceFlag]
    # Where the listener stopped understanding why one idea followed another.
    lost_thread_at: AudienceFlag | None = None

    @property
    def flags(self) -> list[AudienceFlag]:
        return [
            *self.confusions,
            *self.unrelated_facts,
            *self.unclear_terms,
            *([self.lost_thread_at] if self.lost_thread_at else []),
        ]


class StoryDecision(ImmutableModel):
    """The Story Architect's call on a required claim the listener stumbled on."""

    claim_id: str
    action: Literal["keep", "move", "simplify", "merge", "demote", "cut"]
    # For `move`: the beat it moves to. For `merge`: the claim it merges into.
    target: str | None = None
    # For `demote`: its new, lesser role.
    new_role: Literal["supporting_evidence", "colour"] | None = None
    # What the writer should achieve, as intent; never wording.
    note: str


class StoryDecisions(ImmutableModel):
    decisions: list[StoryDecision]
    reasoning: str
