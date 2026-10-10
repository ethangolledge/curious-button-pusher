"""The picture is drawn into a whirlpool round the centre and comes out of it as the next one:
strongest at the centre, still at the edges. Swift and hypnotic."""

from dataclasses import dataclass
from typing import Annotated

from content.blender.blocks.base import Range, Transition
from content.blender.canvas_api import Canvas
from content.blender.patterns import bump, polar, smoothstep, turn


@dataclass(frozen=True)
class Settings:
    turns: Annotated[float, Range(0.2, 6, "how many times the centre turns at the height")] = 1.5
    size: Annotated[float, Range(0.2, 2, "how far out the whirl reaches, in frame heights")] = 0.8


class Swirl(Transition):
    name = "swirl"
    settings = Settings
    example = Settings()

    def build(self, canvas: Canvas, p: Settings) -> None:
        t = canvas.progress()
        at = canvas.coords()
        radius, _ = polar(canvas, at)
        # The whirl fades from the centre to `size`.
        falloff = canvas.math(
            "maximum", canvas.math("subtract", 1.0, canvas.math("divide", radius, p.size)), 0.0
        )
        angle = canvas.math(
            "multiply",
            canvas.math("multiply", bump(canvas, t), p.turns * 6.2832),
            canvas.math("multiply", falloff, falloff),
        )
        whirled = turn(canvas, at, angle)
        canvas.output(
            canvas.mix(
                canvas.picture("from", whirled),
                canvas.picture("to", whirled),
                smoothstep(canvas, 0.35, 0.65, t),
            )
        )
