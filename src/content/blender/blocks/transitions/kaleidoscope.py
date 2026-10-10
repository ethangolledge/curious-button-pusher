"""The picture folds into a turning kaleidoscope of mirrored wedges; at its height the wedges
become the next picture's, and the kaleidoscope unfolds into it."""

from dataclasses import dataclass
from typing import Annotated

from content.blender.blocks.base import Range, Transition
from content.blender.canvas_api import Canvas
from content.blender.patterns import mirrored, smoothstep, zoom


@dataclass(frozen=True)
class Settings:
    wedges: Annotated[int, Range(3, 16, "how many mirrored wedges")] = 6
    turns: Annotated[float, Range(0, 3, "how far the kaleidoscope turns")] = 0.5
    closer: Annotated[float, Range(1, 4, "how far it looks in at the height")] = 1.6


class Kaleidoscope(Transition):
    name = "kaleidoscope"
    settings = Settings
    example = Settings()

    def build(self, canvas: Canvas, p: Settings) -> None:
        t = canvas.progress()
        at = canvas.coords()
        folded = mirrored(
            canvas,
            zoom(canvas, at, p.closer),
            p.wedges,
            canvas.math("multiply", t, p.turns * 6.2832),
        )
        inside = canvas.mix(
            canvas.picture("from", folded, "mirror"),
            canvas.picture("to", folded, "mirror"),
            smoothstep(canvas, 0.4, 0.6, t),
        )
        opened = canvas.mix(canvas.picture("from", at), inside, smoothstep(canvas, 0.0, 0.3, t))
        canvas.output(canvas.mix(opened, canvas.picture("to", at), smoothstep(canvas, 0.7, 1.0, t)))
