"""Sign-offs and reviews: what the person is asked, how they answer, and the record of it."""

from typing import Literal

from pydantic import Field

from content.schemas.base import ImmutableModel

ReviewStage = Literal[
    "brief",
    "research",
    "plan",
    "script",
    "fact_check",
    "visuals",
    "listen",
    "storyboard",
    "final_cut",
]

# The person's sign-offs: each comes before money is spent on the next step (writing,
# narration, pictures, morphs) or the video is called finished. They always stop the run.
# The story plan is one whenever it is reviewed: always for formats that ask for it (long
# form), and whenever the plan's checks have doubts. Every other review is the assistant's
# to answer, and it escalates anything substantive.
SIGN_OFF_STAGES: dict[ReviewStage, str] = {
    "brief": "Start",
    "plan": "Story plan",
    "fact_check": "Script",
    "listen": "Narration",
    "storyboard": "Pictures",
    "final_cut": "Final cut",
}


ReviewAction = Literal["approve", "revise", "stop"]


# Who made a review decision. Only a person's decisions teach the learning loop; an
# assistant answering review files is recorded as such, and older runs are unknown.
DecidedBy = Literal["person", "assistant", "unknown"]


class ReviewItem(ImmutableModel):
    """One thing on a sign-off page the person looks at and may comment on: a script unit,
    a narration passage, or a scene. Its ID prefixes the comment ("S4: …"), which is how
    director notes reach the right agent."""

    item_id: str
    title: str
    text: str = ""
    # A picture or clip to show with it.
    media: str = ""
    # Where it starts in the narration or the cut, in seconds, to play from there.
    start: float | None = None
    # What the checks noticed about it, in plain words.
    flags: list[str] = Field(default_factory=list)
    # Who last changed it, and why: a script line's provenance.
    provenance: str = ""
    # A script line the person may rewrite in their own words, used exactly.
    editable: bool = False
    # What a comment on it may be about, each fixed its own way (a narration passage's
    # `director.PASSAGE_CLASSES`); the comment is sent as "P2 [kind]: …".
    note_kinds: list[str] = Field(default_factory=list)


class ReviewRequest(ImmutableModel):
    stage: ReviewStage
    reason: str
    findings: list[str] = Field(default_factory=list)
    required_changes: list[str] = Field(default_factory=list)
    # Readable copy of the material being decided on, and files to look at or play.
    snapshot: str = ""
    attachments: list[str] = Field(default_factory=list)
    # False while structural blockers remain: a person may revise or stop, not approve.
    approvable: bool = True
    # At a sign-off: the pieces to look at, and what approving sets in motion and costs.
    items: list[ReviewItem] = Field(default_factory=list)
    unlocks: str = ""

    @property
    def sign_off(self) -> bool:
        return self.stage in SIGN_OFF_STAGES


# How far a person's script revision reaches: only the lines they commented on, or the
# whole script rewritten around their notes. Unset, code decides from the notes.
RevisionScope = Literal["lines", "script"]


class ReviewResponse(ImmutableModel):
    action: ReviewAction
    feedback: str | None = None
    # A person's own words for script lines, by unit ID: used exactly, by code.
    edits: dict[str, str] = Field(default_factory=dict)
    scope: RevisionScope | None = None
    # Whoever answers says so: a response that does not is never taken as the person's.
    decided_by: DecidedBy = "unknown"


class HumanDecision(ImmutableModel):
    """A person's decision, recorded beside the findings it answered rather than over them."""

    stage: ReviewStage
    revision: int
    action: ReviewAction
    feedback: str | None = None
    # The script revision the person was looking at: notes on units refer to it.
    script_revision: int | None = None
    decided_by: DecidedBy = "unknown"
