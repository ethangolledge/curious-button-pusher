"""The story's shared vocabulary: what a line does, how it moves, and how it lands."""

from typing import Literal

from content.schemas.base import ImmutableModel

NarrativeFunction = Literal[
    "hook",
    # Straight after the hook: who and what this is about, and why it matters.
    "orient",
    "context",
    "escalation",
    "reveal",
    "consequence",
    "ending",
    "bridge",
]


# How the audience's tension should move. A unit's `transition_intent` describes
# how it enters from the previous unit; "turn" is a change of direction.
Tension = Literal["build", "hold", "release"]


# What a claim is to the story, which sets how much time it gets: the spine is explained
# and given room; essential context is enough to understand what comes next; supporting
# evidence is concise proof; colour goes in only if time allows; expendable is cut.
StoryRole = Literal["spine", "essential_context", "supporting_evidence", "colour", "expendable"]


Transition = Literal["build", "hold", "release", "turn"]


# What a listener instinctively does on hearing a line: the emotional field's source.
Reaction = Literal["lean_in", "brace", "recoil", "settle"]


# The theme's three wordings for how strongly a feeling lands.
STRENGTHS = ("slight", "clear", "strong")


class Feeling(ImmutableModel):
    """A blend of reactions and how strongly they land (0 barely, 2 strongly)."""

    weights: dict[Reaction, float]
    intensity: float

    @property
    def dominant(self) -> Reaction:
        return max(self.weights, key=lambda reaction: self.weights[reaction])

    @property
    def level(self) -> int:
        """Which of the theme's three wordings applies: slight, clear, or strong."""
        return min(int(self.intensity / 2 * 3), 2)

    def label(self) -> str:
        return f"{self.dominant.replace('_', ' ')} · {STRENGTHS[self.level]}"
