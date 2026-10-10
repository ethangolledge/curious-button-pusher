"""A swift morph: the camera seems to rush into the old picture, streaking as it goes, and
out into the new one, still moving forward. For a sudden turn."""

from dataclasses import dataclass
from typing import Annotated

from content.blender.blocks.base import Range, Transition
from content.blender.canvas_api import Canvas, Picture, Socket
from content.blender.patterns import blend, bump, smoothstep, zoom


@dataclass(frozen=True)
class Settings:
    depth: Annotated[float, Range(1.5, 12, "how far it rushes in")] = 5.0
    streak: Annotated[float, Range(0, 0.3, "how much the picture streaks outward")] = 0.12


class ZoomThrough(Transition):
    name = "zoom_through"
    settings = Settings
    example = Settings()

    def build(self, canvas: Canvas, p: Settings) -> None:
        t = canvas.progress("in_out")
        at = canvas.coords()
        streak = canvas.math("multiply", bump(canvas, t), p.streak)
        # The old picture grows from life size; the new one arrives large and settles.
        leaving = blend(canvas, 1.0, p.depth, canvas.math("multiply", t, t))
        arriving = blend(
            canvas,
            p.depth * 0.5,
            1.0,
            canvas.math(
                "subtract",
                1.0,
                canvas.math(
                    "multiply", canvas.math("subtract", 1.0, t), canvas.math("subtract", 1.0, t)
                ),
            ),
        )
        old = _streaked(canvas, "from", at, leaving, streak)
        new = _streaked(canvas, "to", at, arriving, streak)
        canvas.output(canvas.mix(old, new, smoothstep(canvas, 0.4, 0.6, t)))


def _streaked(canvas: Canvas, which: Picture, at: Socket, factor: Socket, streak: Socket) -> Socket:
    """A picture zoomed by `factor`, smeared outward along its radius (four looks, averaged)."""
    colour = canvas.picture(which, zoom(canvas, at, factor))
    for step in (1, 2, 3):
        further = canvas.math(
            "multiply", factor, canvas.math("add", 1.0, canvas.math("multiply", streak, step / 3))
        )
        colour = canvas.mix(
            colour, canvas.picture(which, zoom(canvas, at, further)), 1 / (step + 1)
        )
    return colour
