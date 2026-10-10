"""The picture breaks into a screen of round dots that swell from the centre outward, each
carrying the next picture, until they touch and it is whole: a print's halftone, opening."""

from dataclasses import dataclass
from typing import Annotated

from content.blender.blocks.base import Range, Transition
from content.blender.canvas_api import Canvas
from content.blender.patterns import blend, polar, smoothstep, turn


@dataclass(frozen=True)
class Settings:
    size: Annotated[float, Range(0.005, 0.2, "the dot spacing, in frame heights")] = 0.03
    angle: Annotated[float, Range(0, 90, "the screen's angle, degrees")] = 45.0
    spread: Annotated[float, Range(0, 2, "how much later the edges open than the centre")] = 0.7


class Dots(Transition):
    name = "dots"
    settings = Settings
    example = Settings()

    def build(self, canvas: Canvas, p: Settings) -> None:
        t = canvas.progress()
        at = canvas.coords()
        radius, _ = polar(canvas, at)
        screen = turn(canvas, at, p.angle * 0.01745)
        x, y = canvas.parts(screen)
        # Distance from the nearest dot centre, in units of the spacing.
        cx = canvas.math("subtract", canvas.math("fraction", canvas.math("divide", x, p.size)), 0.5)
        cy = canvas.math("subtract", canvas.math("fraction", canvas.math("divide", y, p.size)), 0.5)
        near = canvas.math(
            "sqrt",
            canvas.math("add", canvas.math("multiply", cx, cx), canvas.math("multiply", cy, cy)),
        )
        # Each dot's own moment: the centre first, the edges `spread` later.
        local = smoothstep(
            canvas,
            0.0,
            1.0,
            canvas.math(
                "subtract",
                canvas.math("multiply", t, 1.0 + p.spread),
                canvas.math("multiply", radius, p.spread),
            ),
        )
        dot = blend(canvas, 0.0, 0.75, local)
        inside = canvas.math("less_than", near, dot)
        canvas.output(canvas.mix(canvas.picture("from", at), canvas.picture("to", at), inside))
