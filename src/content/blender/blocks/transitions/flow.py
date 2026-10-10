"""A smooth, liquid morph: both pictures drift on a slow current while the next one flows in
through the old in soft, cloud-shaped tides. For a calm change."""

from dataclasses import dataclass
from typing import Annotated

from content.blender.blocks.base import Range, Transition
from content.blender.canvas_api import Canvas
from content.blender.patterns import bump, smoothstep


@dataclass(frozen=True)
class Settings:
    current: Annotated[
        float, Range(0, 0.2, "how far the pictures drift, as a share of the frame")
    ] = 0.05
    scale: Annotated[float, Range(0.5, 10, "the size of the tides: larger is finer")] = 2.0


class Flow(Transition):
    name = "flow"
    settings = Settings
    example = Settings()

    def build(self, canvas: Canvas, p: Settings) -> None:
        t = canvas.progress()
        at = canvas.coords()
        x, y = canvas.parts(at)
        strength = canvas.math("multiply", bump(canvas, t), p.current)
        drift_x = canvas.math(
            "multiply", canvas.math("subtract", canvas.noise(at, p.scale), 0.5), strength
        )
        drift_y = canvas.math(
            "multiply",
            canvas.math("subtract", canvas.noise(canvas.point(y, x), p.scale), 0.5),
            strength,
        )
        moved = canvas.point(canvas.math("add", x, drift_x), canvas.math("add", y, drift_y))
        # The tide: where the noise is high, the next picture arrives first.
        tide = canvas.math(
            "add",
            t,
            canvas.math(
                "multiply", canvas.math("subtract", canvas.noise(at, p.scale * 0.7), 0.5), 0.6
            ),
        )
        amount = smoothstep(canvas, 0.2, 0.8, tide)
        canvas.output(
            canvas.mix(canvas.picture("from", moved), canvas.picture("to", moved), amount)
        )
