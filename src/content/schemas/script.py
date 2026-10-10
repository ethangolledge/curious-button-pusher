"""The narration: script units, the voice direction, and line edits."""

from typing import Any, Literal

from pydantic import Field, computed_field, model_validator

from content.schemas.base import ImmutableModel
from content.schemas.story import NarrativeFunction, Transition

# Who changed a line: the person directly, the writer's small line-edit model, or the
# writer's own model (a whole rewrite, or a line edit escalated after the small model failed).
LineAuthor = Literal["person", "editor", "writer"]


class LineEdit(ImmutableModel):
    """One line changed, by whom and why: the script's provenance. A person's edit stands
    word for word through every later revision."""

    unit_id: str
    before: str
    after: str
    author: LineAuthor
    reason: str
    script_revision: int


class EditedLine(ImmutableModel):
    unit_id: str
    text: str


class LineEditPackage(ImmutableModel):
    """The Script Writer's line edit: new words for the named lines, and only those."""

    lines: list[EditedLine]


class VoiceDirection(ImmutableModel):
    """How the script is performed, by the writer who knows what each part is for."""

    tone: str
    pace: str
    delivery: str
    pronunciation_notes: list[str] = Field(default_factory=list)
    # How to say each beat, by arc phase ID, in a few plain words ("brisk and matter-of-fact";
    # "slower; let the figure land"). Each passage is spoken with its beat's direction.
    beats: dict[str, str] = Field(default_factory=dict)
    # How the voice should say particular words in this script, after the theme's lexicon:
    # the written word, then how to spell it for the voice.
    say_as: dict[str, str] = Field(default_factory=dict)


class ScriptUnit(ImmutableModel):
    """One sentence or two of narration, with the claims it rests on. Consecutive units
    in the same arc phase form a passage, spoken in one take."""

    unit_id: str
    order: int
    narrative_function: NarrativeFunction
    arc_phase_id: str
    transition_intent: Transition
    text: str
    claim_ids: list[str] = Field(default_factory=list)


class ScriptPackage(ImmutableModel):
    title: str
    script_units: list[ScriptUnit] = Field(min_length=1)
    intended_takeaway: str
    voice_direction: VoiceDirection

    @model_validator(mode="before")
    @classmethod
    def _ignore_saved_computed_fields(cls, data: Any) -> Any:
        """Saved packages include the computed fields below; they are rebuilt, not read."""
        if isinstance(data, dict):
            return {
                key: value
                for key, value in data.items()
                if key not in {"hook", "master_script", "claims_used"}
            }
        return data

    @computed_field  # type: ignore[prop-decorator]
    @property
    def hook(self) -> str:
        return self.script_units[0].text

    @computed_field  # type: ignore[prop-decorator]
    @property
    def master_script(self) -> str:
        return " ".join(unit.text.strip() for unit in self.script_units)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def claims_used(self) -> list[str]:
        return list(
            dict.fromkeys(claim_id for unit in self.script_units for claim_id in unit.claim_ids)
        )
