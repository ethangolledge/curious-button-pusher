"""The Editorial Director's plan: the story ledger (beats and claims) and the story's size."""

from typing import Literal

from content.schemas.base import ImmutableModel
from content.schemas.story import StoryRole, Tension

# The one job a beat does in the story.
BeatRole = Literal[
    "hook",
    "orient",
    "cause",
    "explain",
    "escalate",
    "reveal",
    "contrast",
    "consequence",
    "resolve",
]


class ArcPhase(ImmutableModel):
    """One beat of the story, spoken as one passage: its row in the story ledger. What the
    listener knew and wondered before it is the previous beat's `audience_knows_after` and
    `next_question` (the first beat starts from the plan's `audience_starts_knowing`)."""

    phase_id: str
    role: BeatRole
    audience_feeling: str
    # The beat's purpose: what happens and why it matters, in plain words, as meaning,
    # never as a list of facts to copy.
    narrative_job: str
    # What a first-time listener knows once the beat ends.
    audience_knows_after: str
    # The open question this beat answers, if any.
    question_answered: str
    # The question it leaves the listener with, and what will answer it next.
    next_question: str
    next_reveal: str
    # Why the next beat follows from this one; for the last beat, what the listener is
    # left holding.
    leads_to_next: str
    tension: Tension
    # How this beat follows the last: it overturns it (`but`) or follows from it
    # (`therefore`). The first beat is the `setup`.
    link: Literal["setup", "but", "therefore"] = "therefore"
    # The research claims this beat tells.
    claim_ids: list[str] = []
    # The words this beat is given: set by code from its claims' story roles and weights.
    words: int = 0
    # How the beat is told, set by code from its strongest claim: `logic` (brisk, plain),
    # `feeling` (the line lands, a human reaction allowed), `curiosity` (asked, not
    # asserted, because the evidence cannot carry more).
    telling: Literal["logic", "feeling", "curiosity"] = "logic"


class ClaimPlan(ImmutableModel):
    """One research claim's place in the story: the claims half of the story ledger."""

    claim_id: str
    story_role: StoryRole
    # Why the audience needs it to understand the story.
    narrative_job: str
    # What it shows, plainly and within the evidence: the fact's significance, as distinct
    # from the fact.
    meaning: str
    # The narration must explain it rather than merely state it.
    requires_explanation: bool
    # For supporting evidence, the claim it proves.
    supports_claim: str | None = None


class Explanation(ImmutableModel):
    """A term, institution, deal or figure the listener must understand, said plainly,
    with the research claims that support the plain version."""

    term: str
    plain: str
    claim_ids: list[str] = []


class ClaimWeight(ImmutableModel):
    """A claim's three numbers (0 to 1) and its score, shown at the plan review."""

    claim_id: str
    evidence: float
    worth: float
    connection: float
    score: float


class LeftOut(ImmutableModel):
    """A thread or claim deliberately kept out, and why it does not serve this story."""

    what: str
    why: str


class StorySize(ImmutableModel):
    """The plan's length, estimated by code from its beats' words, and the edits of the
    music it could be told in."""

    estimate_seconds: float
    # The planned length: the estimate, or the music edit nearest it, less its outro.
    target_seconds: float
    beat_seconds: dict[str, float]
    # (edit length, roughly how many words to add or cut to fit it), shortest first.
    edits: list[tuple[float, int]] = []
    # The most narration the longest allowed video holds, in seconds and roughly in words:
    # a hard limit, since the platforms cut the video at `format.max_seconds`.
    longest_seconds: float
    longest_words: int
    # Every measured claim's weights, strongest first.
    claims: list[ClaimWeight] = []


class EditorialBrief(ImmutableModel):
    """The creative plan: the control plane every later stage and judgement works to."""

    central_question: str
    promise: str
    # The single most arresting verified claim, spoken in the first three seconds.
    hook_claim_id: str | None = None
    # What a viewer must know by about eight seconds: who, what, and why it matters.
    orientation: str = ""
    # What the intended listener already knows before the first word.
    audience_starts_knowing: str
    # The whole story as a newcomer could retell it: one plain sentence per step, each
    # following from the one before.
    story_chain: list[str]
    arc: list[ArcPhase]
    # Every research claim the plan considered, with its role in the story.
    claims: list[ClaimPlan]
    # Everything the narration must explain rather than assume.
    explain: list[Explanation] = []
    style_boundaries: list[str]
    central_angle: str
    intended_audience: str
    intended_takeaway: str
    story_assignment: list[str]
    fact_check_priorities: list[str]
    visual_principles: list[str]
    tone: str
    narrative_direction: str
    required_context: list[str]
    editorial_risks: list[str]
    left_out: list[LeftOut] = []
    # Why the story needs the length its beats add up to, when that differs from the
    # preferred length.
    length_note: str = ""

    # The claim lists every stage reads, derived from the ledger's story roles: the story
    # cannot be told without the required ones, the supporting ones may be used, and the
    # excluded ones are never told.
    @property
    def required_claim_ids(self) -> list[str]:
        return self._with_role("spine", "essential_context")

    @property
    def supporting_claim_ids(self) -> list[str]:
        return self._with_role("supporting_evidence", "colour")

    @property
    def excluded_claim_ids(self) -> list[str]:
        return self._with_role("expendable")

    def _with_role(self, *roles: StoryRole) -> list[str]:
        return [claim.claim_id for claim in self.claims if claim.story_role in roles]

    def claim_plan(self, claim_id: str) -> ClaimPlan | None:
        return next((claim for claim in self.claims if claim.claim_id == claim_id), None)
