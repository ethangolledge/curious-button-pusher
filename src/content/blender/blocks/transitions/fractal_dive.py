"""The psychedelic dive: the picture opens into an endless spiral of copies of itself, turning
inward ever smaller; copies of the next picture flood in from the edges ring by ring until
they fill it, and the spiral closes on the new picture. The Droste effect, in motion."""

from dataclasses import dataclass
from typing import Annotated

from content.blender.blocks.base import Range, Transition
from content.blender.canvas_api import Canvas
from content.blender.patterns import smoothstep, spiral, turn

# Rings past this number are the next picture's: they arrive at the edge once the spiral moves.
NEXT_RINGS = 1


@dataclass(frozen=True)
class Settings:
    rings: Annotated[float, Range(2, 20, "how many rings flow inward over the transition")] = 9.0
    period: Annotated[
        float, Range(1.5, 6, "how much smaller each copy is than the one round it")
    ] = 2.6
    arms: Annotated[int, Range(1, 4, "how many spiral arms")] = 1
    spin: Annotated[float, Range(-2, 2, "extra turns of the whole spiral")] = 0.4
    reach: Annotated[
        float, Range(0.1, 0.6, "how much of each picture a copy shows, from its centre")
    ] = 0.42


class FractalDive(Transition):
    name = "fractal_dive"
    settings = Settings
    example = Settings()

    def build(self, canvas: Canvas, p: Settings) -> None:
        t = canvas.progress("in_out")
        at = canvas.coords()
        turned = turn(canvas, at, canvas.math("multiply", t, p.spin * 6.2832))
        look, ring = spiral(
            canvas,
            turned,
            canvas.math("multiply", t, p.rings),
            period=p.period,
            reach=p.reach,
            twist=p.arms,
        )
        nested = canvas.mix(
            canvas.picture("from", look, "mirror"),
            canvas.picture("to", look, "mirror"),
            canvas.math("greater_than", ring, NEXT_RINGS - 0.5),
        )
        # It opens from the plain picture and closes on the plain next one.
        opened = canvas.mix(canvas.picture("from", at), nested, smoothstep(canvas, 0.0, 0.18, t))
        canvas.output(
            canvas.mix(opened, canvas.picture("to", at), smoothstep(canvas, 0.82, 1.0, t))
        )
