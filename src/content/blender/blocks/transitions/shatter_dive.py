"""The frame splits into a mosaic of ever smaller sections while the camera dives into it, each
section a small copy of the old picture or the new; the new copies multiply until they are
all there is, and the mosaic closes on the new picture. Fractal, restless, never a cut."""

import math
from dataclasses import dataclass
from typing import Annotated

from content.blender.blocks.base import Range, Transition
from content.blender.canvas_api import Canvas, Socket
from content.blender.patterns import blend, bump, polar, smoothstep, turn, zoom


@dataclass(frozen=True)
class Settings:
    levels: Annotated[int, Range(1, 7, "how many times the sections split at the height")] = 4
    dive: Annotated[float, Range(1, 8, "how far the camera dives in")] = 2.5
    spin: Annotated[float, Range(-1, 1, "turns of the mosaic as it dives")] = 0.15


class ShatterDive(Transition):
    name = "shatter_dive"
    settings = Settings
    example = Settings()

    def build(self, canvas: Canvas, p: Settings) -> None:
        t = canvas.progress()
        at = canvas.coords()
        height = bump(canvas, t)
        dived = zoom(
            canvas,
            turn(canvas, at, canvas.math("multiply", t, p.spin * 2 * math.pi)),
            blend(canvas, 1.0, p.dive, height),
        )
        radius, _ = polar(canvas, dived)
        # The split deepens to the centre and at the height of the transition.
        depth = canvas.math(
            "floor",
            canvas.math(
                "multiply",
                height,
                canvas.math("add", p.levels, canvas.math("multiply", radius, -2.0)),
            ),
        )
        cells = canvas.math("power", 2.0, canvas.math("maximum", depth, 0.0))
        x, y = canvas.parts(dived)
        # Inside a section: its own small copy of a picture, centred.
        local = canvas.point(
            _within(canvas, x, cells, canvas.aspect), _within(canvas, y, cells, 1.0)
        )
        # Which picture a section shows: the new one claims more sections as time goes on.
        which = canvas.noise(
            canvas.point(
                canvas.math("floor", canvas.math("multiply", x, cells)),
                canvas.math("floor", canvas.math("multiply", y, cells)),
            ),
            3.7,
        )
        new = canvas.math("less_than", which, smoothstep(canvas, 0.15, 0.85, t))
        mosaic = canvas.mix(
            canvas.picture("from", local, "mirror"), canvas.picture("to", local, "mirror"), new
        )
        opened = canvas.mix(canvas.picture("from", at), mosaic, smoothstep(canvas, 0.0, 0.15, t))
        canvas.output(
            canvas.mix(opened, canvas.picture("to", at), smoothstep(canvas, 0.85, 1.0, t))
        )


def _within(canvas: Canvas, value: Socket, cells: Socket, span: float) -> Socket:
    """A coordinate inside its section, stretched back to the whole picture's span."""
    scaled = canvas.math(
        "multiply", canvas.math("add", canvas.math("divide", value, span), 0.5), cells
    )
    return canvas.math(
        "multiply", canvas.math("subtract", canvas.math("fraction", scaled), 0.5), span
    )
