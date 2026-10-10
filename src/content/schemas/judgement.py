"""Judging: Jev's typed answers, each question's outcome, and the critic's findings."""

from typing import Literal

from pydantic import Field

from content.schemas.base import ImmutableModel

JudgedStage = Literal[
    "plan", "script", "audience", "visuals", "references", "keyframes", "segments"
]


Outcome = Literal["pass", "fail", "unsure"]


class Critique(ImmutableModel):
    """The critic's call on a whole script or storyboard: accept it, or name exactly what
    to change. It settles Jev's doubts instead of stopping for a person."""

    verdict: Literal["accept", "revise"]
    # Each names the unit or scene ID it applies to, what is wrong and what it must achieve;
    # never replacement wording, which is the writer's.
    corrections: list[str]
    reasoning: str


class Answer(ImmutableModel):
    """One typed Jev answer.

    `noul` is the probability of "yes". Choice and score answers carry a
    confidence derived from how concentrated their probability distribution is.
    """

    kind: Literal["noul", "choice", "score"]
    noul: float | None = None
    choice: str | None = None
    score: float | None = None
    confidence: float | None = None
    probabilities: dict[str, float] = Field(default_factory=dict)


class Judgement(ImmutableModel):
    """One recorded Jev answer, tied to the artifact revision it judged."""

    stage: JudgedStage
    revision: int
    target_id: str
    question_id: str
    answer: Answer
    expected: str | None
    outcome: Outcome
    blocking: bool
    model: str
