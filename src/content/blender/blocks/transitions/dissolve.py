"""A plain dissolve: one picture fades into the next. The quietest join."""

from dataclasses import dataclass

from content.blender.blocks.base import Transition
from content.blender.canvas_api import Canvas


@dataclass(frozen=True)
class Settings:
    pass


class Dissolve(Transition):
    name = "dissolve"
    settings = Settings
    example = Settings()

    def build(self, canvas: Canvas, p: Settings) -> None:
        at = canvas.coords()
        canvas.output(
            canvas.mix(canvas.picture("from", at), canvas.picture("to", at), canvas.progress())
        )
