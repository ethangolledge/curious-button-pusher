"""The camera holds on a subject, barely breathing: for a moment that should sit still."""

from dataclasses import dataclass
from typing import Annotated

from content.blender.api import Stage
from content.blender.blocks.base import About, Move, Range, Ref
from content.blender.camera import Framing, Shot, around, film
from content.blender.maths import Still
from content.blender.motion import front, where


@dataclass(frozen=True)
class Settings:
    subject: Annotated[Ref, About("an actor or a mark")]
    start: Annotated[float, Range(-180, 180, "degrees round from the subject's front")] = -20.0
    framing: Framing = "medium"
    elevation: Annotated[float, Range(-60, 85, "degrees above the subject")] = 10.0
    lens: Annotated[float, Range(14, 135, "mm")] = 50.0
    drift: Annotated[float, Range(0, 0.2, "metres of handheld sway")] = 0.015


class Hold(Move):
    name = "hold"
    settings = Settings
    example = Settings(subject=Ref("centre"))

    def build(self, stage: Stage, p: Settings) -> None:
        box = where(stage, p.subject.name)
        stand = around(
            stage, box, p.framing, p.lens, front(stage, p.subject.name) + p.start, p.elevation
        )
        film(
            stage,
            Shot(Still(stand.position), Still(box.centre), stand.lens, stand.lens),
            drift=p.drift,
        )
