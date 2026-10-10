"""What the person chose for one video: its format, length, number of scenes and spending
cap. The channel's look, voice and music stay the theme's; these shape this video only.
Saved in the run folder, so every resume makes the same video."""

from dataclasses import replace
from typing import Self

from pydantic import Field

from content.config import ContentConfig
from content.schemas.base import ImmutableModel

# A chosen length may run this much over before the story is cut back: room for a story
# that needs it, without a ten-minute video becoming twenty.
LENGTH_ALLOWANCE = 1.3


class RunChoices(ImmutableModel):
    # A format name from the theme's `formats`; unset, the theme's default.
    format: str | None = None
    # The length the story is planned to, in seconds; unset, the configured default.
    seconds: int | None = Field(default=None, gt=0)
    # How many scenes (a picture each, a morph between each pair); unset, as many as the
    # story and the budget suggest.
    scenes: int | None = Field(default=None, gt=0)
    # The most the whole run may spend; unset, the configured cap.
    max_usd: float | None = Field(default=None, gt=0)

    def merged(self, newer: Self) -> Self:
        """These choices with every one `newer` sets replaced."""
        return self.model_copy(update=newer.model_dump(exclude_none=True))


def configure_run(config: ContentConfig, choices: RunChoices) -> ContentConfig:
    """The configuration for one video: its format (frame, lengths, subtitles, and whether
    the story plan is signed off), a chosen length's ceiling, and its spending cap."""
    theme = config.theme.with_format(choices.format) if choices.format else config.theme
    shape = theme.spec.format
    if choices.seconds is not None:
        ceiling = min(shape.max_seconds, round(choices.seconds * LENGTH_ALLOWANCE))
        shape = shape.model_copy(update={"max_seconds": max(ceiling, shape.min_seconds)})
        theme = type(theme)(
            theme.root, theme.spec.model_copy(update={"format": shape}), theme.skill
        )
    workflow = replace(
        config.workflow, review_plan=config.workflow.review_plan or shape.review_plan
    )
    production = config.production
    if production is not None and choices.max_usd is not None:
        production = replace(production, max_usd=choices.max_usd)
    return replace(config, theme=theme, workflow=workflow, production=production)
