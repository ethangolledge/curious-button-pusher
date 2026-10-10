"""The camera stands still and turns: a pan across a room, or a full panorama around the
place it stands, as a person looking round would see it."""

import math
from dataclasses import dataclass
from typing import Annotated, Literal

from content.blender.api import Stage
from content.blender.blocks.base import About, Move, Range, Ref
from content.blender.camera import Shot, film
from content.blender.maths import Arc, Still, Vec
from content.blender.motion import front, where


@dataclass(frozen=True)
class Settings:
    at: Annotated[Ref, About("where the camera stands: an actor (looking from its eyes) or a mark")]
    degrees: Annotated[float, Range(-360, 360, "how far it turns; negative turns right")] = 90.0
    start: Annotated[
        float, Range(-180, 180, "degrees from the way the mark or actor faces")
    ] = -45.0
    tilt: Annotated[float, Range(-60, 60, "degrees up (positive) or down")] = 0.0
    eye: Annotated[float, Range(0.1, 50, "metres above the ground")] = 1.6
    lens: Annotated[float, Range(14, 135, "mm")] = 28.0
    ease: Literal["linear", "in", "out", "in_out"] = "in_out"


class Pan(Move):
    name = "pan"
    settings = Settings
    example = Settings(at=Ref("centre"))

    def build(self, stage: Stage, p: Settings) -> None:
        box = where(stage, p.at.name)
        eye = Vec(box.centre.x, box.centre.y, box.low.z + p.eye)
        # It looks out along a circle round where it stands: the target travels, it does not.
        lift = 5 * math.tan(math.radians(p.tilt))
        start = front(stage, p.at.name) + p.start
        target = Arc(eye, 5.0, start, p.degrees, lift, lift)
        film(stage, Shot(Still(eye), target, p.lens, p.lens), ease=p.ease)
