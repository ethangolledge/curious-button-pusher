"""The dolly zoom: the camera travels towards (or away from) a subject while its lens widens
(or narrows) to keep the subject the same size, so the world behind it stretches away or
rushes in. The classic shot of a realisation, or of the ground giving way."""

from dataclasses import dataclass
from typing import Annotated, Literal

from content.blender.api import Stage
from content.blender.blocks.base import About, Move, Range, Ref
from content.blender.camera import Framing, Shot, around, film
from content.blender.maths import Line, Still
from content.blender.motion import front, where


@dataclass(frozen=True)
class Settings:
    subject: Annotated[Ref, About("an actor or a mark")]
    direction: Literal["in", "out"] = "in"
    amount: Annotated[float, Range(0.1, 0.8, "how far it travels, as a share of the distance")] = (
        0.5
    )
    start: Annotated[float, Range(-180, 180, "degrees round from the subject's front")] = 0.0
    framing: Framing = "medium"
    elevation: Annotated[float, Range(-30, 60, "degrees above the subject")] = 5.0
    lens: Annotated[float, Range(14, 135, "mm at the start")] = 50.0
    ease: Literal["linear", "in", "out", "in_out"] = "in_out"


class Vertigo(Move):
    name = "vertigo"
    settings = Settings
    example = Settings(subject=Ref("centre"))

    def build(self, stage: Stage, p: Settings) -> None:
        box = where(stage, p.subject.name)
        stand = around(
            stage, box, p.framing, p.lens, front(stage, p.subject.name) + p.start, p.elevation
        )
        nearer = stand.position.lerp(box.centre, p.amount)
        path = Line(stand.position, nearer) if p.direction == "in" else Line(nearer, stand.position)
        lens = stand.lens if p.direction == "in" else stand.lens * (1 - p.amount)
        shot = Shot(path, Still(box.centre), lens, lens, hold_size=True)
        film(stage, shot, ease=p.ease, watching=box)
