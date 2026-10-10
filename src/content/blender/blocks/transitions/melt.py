"""The old picture melts away along a ragged front spreading from the centre: an ink-dark edge,
the paint ahead of it running down, the new picture behind it."""

from dataclasses import dataclass
from typing import Annotated

from content.blender.blocks.base import About, Range, Transition
from content.blender.canvas_api import Canvas
from content.blender.patterns import polar, smoothstep

# How wide the front's dark edge is, and the running paint ahead of it.
EDGE, RUN = 0.03, 0.18


@dataclass(frozen=True)
class Settings:
    ink: Annotated[str, About("the edge's colour, hex")] = "#07070a"
    rag: Annotated[float, Range(0, 1, "how ragged the front is")] = 0.55
    drip: Annotated[
        float, Range(0, 0.3, "how far the paint runs ahead of it, in frame heights")
    ] = 0.1


class Melt(Transition):
    name = "melt"
    settings = Settings
    example = Settings()

    def build(self, canvas: Canvas, p: Settings) -> None:
        t = canvas.progress()
        at = canvas.coords()
        x, y = canvas.parts(at)
        radius, _ = polar(canvas, at)
        # The order points melt in: distance from the centre, roughened by noise.
        order = canvas.math(
            "add",
            canvas.math("multiply", radius, 1.0 - p.rag),
            canvas.math("multiply", canvas.noise(at, 3.0, 3.0), p.rag),
        )
        # At the end the furthest point (about 0.8 in this order) is past the edge.
        front = canvas.math("subtract", canvas.math("multiply", t, 0.85 + EDGE), order)
        # Ahead of the front, the old paint runs down: looked at from above.
        running = canvas.math("multiply", smoothstep(canvas, -RUN, 0.0, front), p.drip)
        dripped = canvas.point(x, canvas.math("add", y, running))
        old = canvas.picture("from", dripped)
        edge = canvas.math(
            "multiply",
            smoothstep(canvas, -EDGE, 0.0, front),
            canvas.math("subtract", 1.0, smoothstep(canvas, 0.0, EDGE, front)),
        )
        inked = canvas.mix(old, canvas.colour(p.ink), edge)
        canvas.output(
            canvas.mix(inked, canvas.picture("to", at), smoothstep(canvas, 0.0, EDGE, front))
        )
