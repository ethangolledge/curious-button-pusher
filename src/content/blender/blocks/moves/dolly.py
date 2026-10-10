"""The camera travels in a straight line while it watches a subject: in to reveal, out for
consequence and scale, sideways past it (the subject slides across the frame), or up and
down (a crane rising over it)."""

import math
from dataclasses import dataclass
from typing import Annotated, Literal

from content.blender.api import Stage
from content.blender.blocks.base import About, Move, Range, Ref
from content.blender.camera import Framing, Shot, around, film
from content.blender.maths import UP, Line
from content.blender.motion import front, where


@dataclass(frozen=True)
class Settings:
    subject: Annotated[Ref, About("an actor or a mark")]
    direction: Literal["in", "out", "left", "right", "up", "down"] = "in"
    distance: Annotated[float, Range(0, 100, "metres travelled; 0 is a third of the way in")] = 0.0
    start: Annotated[float, Range(-180, 180, "degrees round from the subject's front")] = 0.0
    framing: Framing = "medium"
    elevation: Annotated[float, Range(-60, 85, "degrees above the subject")] = 8.0
    lens: Annotated[float, Range(14, 135, "mm")] = 35.0
    ease: Literal["linear", "in", "out", "in_out"] = "in_out"


class Dolly(Move):
    name = "dolly"
    settings = Settings
    example = Settings(subject=Ref("centre"))

    def build(self, stage: Stage, p: Settings) -> None:
        box = where(stage, p.subject.name)
        stand = around(
            stage, box, p.framing, p.lens, front(stage, p.subject.name) + p.start, p.elevation
        )
        towards = (box.centre - stand.position).normalised()
        across = towards.cross(UP).normalised()
        travel = p.distance or math.dist(stand.position.tuple(), box.centre.tuple()) / 3
        step = {
            "in": towards, "out": -towards, "right": across, "left": -across, "up": UP, "down": -UP,
        }[p.direction] * travel  # fmt: skip
        # In, out, up and down keep looking at the subject; sideways the gaze travels too.
        sideways = p.direction in ("left", "right")
        start = stand.position - step * 0.5 if sideways else stand.position
        target = (
            Line(box.centre - step * 0.5, box.centre + step * 0.5)
            if sideways
            else Line(box.centre, box.centre)
        )
        film(
            stage,
            Shot(Line(start, start + step), target, stand.lens, stand.lens),
            ease=p.ease,
            watching=box,
        )
