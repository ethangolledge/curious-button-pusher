"""The camera flies along one of the layout's paths: down a corridor, along a street, over a
landscape. It looks ahead, or keeps its eyes on a subject as it passes."""

from dataclasses import dataclass
from typing import Annotated, Literal

from content.blender.api import Stage
from content.blender.blocks.base import About, Move, Range, Ref
from content.blender.camera import Shot, film
from content.blender.maths import Curve, Offset, Still, Stretch, Vec
from content.blender.motion import route, where


@dataclass(frozen=True)
class Settings:
    path: Annotated[Ref, About("a path in the layout")]
    look_at: Annotated[str, About("'ahead', or an actor or mark to watch")] = "ahead"
    height: Annotated[float, Range(0.1, 300, "metres above the path")] = 1.6
    lens: Annotated[float, Range(14, 135, "mm")] = 28.0
    start: Annotated[float, Range(0, 1, "how far along the path it starts")] = 0.0
    end: Annotated[float, Range(0, 1, "how far along the path it ends")] = 1.0
    ease: Literal["linear", "in", "out", "in_out"] = "in_out"


class Fly(Move):
    name = "fly"
    settings = Settings
    example = Settings(path=Ref("across"))

    def build(self, stage: Stage, p: Settings) -> None:
        line = route(stage, p.path.name)
        lifted = Offset(line, Vec(0, 0, p.height))
        target: Curve
        if p.look_at == "ahead":
            # It looks a little way down the path, so it stops short of the path's end.
            ahead = 0.08 * abs(p.end - p.start)
            end = min(p.end, 1 - ahead)
            position = Stretch(lifted, p.start, end)
            target = Stretch(Offset(line, Vec(0, 0, p.height * 0.85)), p.start + ahead, end + ahead)
        else:
            position = Stretch(lifted, p.start, p.end)
            target = Still(where(stage, p.look_at).centre)
        film(stage, Shot(position, target, p.lens, p.lens), ease=p.ease)
