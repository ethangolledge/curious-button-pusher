"""The camera circles a subject, looking at it: a slow arc of a few degrees for unease, a half
turn to examine, a full 360. It can rise or sink as it goes, and close in (a spiral)."""

import math
from dataclasses import dataclass
from typing import Annotated

from content.blender.api import Stage
from content.blender.blocks.base import About, Move, Range, Ref
from content.blender.camera import Framing, Shot, around, film
from content.blender.maths import Arc, Still
from content.blender.motion import front, where


@dataclass(frozen=True)
class Settings:
    subject: Annotated[Ref, About("an actor or a mark")]
    degrees: Annotated[float, Range(-720, 720, "how far round; negative goes clockwise")] = 60.0
    start: Annotated[float, Range(-180, 180, "degrees round from the subject's front")] = -30.0
    framing: Framing = "medium"
    elevation: Annotated[float, Range(-60, 85, "degrees above the subject")] = 12.0
    rise: Annotated[float, Range(-60, 60, "degrees the elevation changes by the end")] = 0.0
    closer: Annotated[float, Range(-1, 0.9, "how much nearer by the end: a spiral in")] = 0.0
    lens: Annotated[float, Range(14, 135, "mm")] = 35.0
    drift: Annotated[float, Range(0, 0.2, "metres of handheld sway")] = 0.0


class Orbit(Move):
    name = "orbit"
    settings = Settings
    example = Settings(subject=Ref("centre"))

    def build(self, stage: Stage, p: Settings) -> None:
        box = where(stage, p.subject.name)
        start = front(stage, p.subject.name) + p.start
        stand = around(stage, box, p.framing, p.lens, start, p.elevation, sweep=p.degrees)
        end = stand.radius * (1 - p.closer)
        risen = end * math.tan(math.radians(p.elevation + p.rise))
        path = Arc(box.centre, stand.radius, stand.degrees, p.degrees, stand.height, risen, end)
        film(
            stage,
            Shot(path, Still(box.centre), stand.lens, stand.lens),
            drift=p.drift,
            watching=box,
        )
