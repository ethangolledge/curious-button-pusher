"""Three-point light on a subject: a key light to one side, a softer fill on the other, a rim
behind to lift it from the background. The classic way to show one thing clearly."""

import math
from dataclasses import dataclass
from typing import Annotated

from content.blender.api import Stage
from content.blender.blocks.base import About, Light, Range, Ref
from content.blender.maths import Vec
from content.blender.motion import front, where


@dataclass(frozen=True)
class Settings:
    subject: Annotated[Ref, About("an actor or mark")]
    key_side: Annotated[float, Range(-120, 120, "degrees round from the front for the key")] = -45.0
    contrast: Annotated[float, Range(1, 16, "key over fill: 2 gentle, 8 dramatic")] = 3.0
    colour: Annotated[str, About("hex")] = "#fff3e2"
    power: Annotated[
        float, Range(10, 5000, "watts of the key for a small thing; larger ones get more")
    ] = 250.0


class Studio(Light):
    name = "studio"
    settings = Settings
    example = Settings(subject=Ref("centre"))

    def build(self, stage: Stage, p: Settings) -> None:
        box = where(stage, p.subject.name)
        reach = max(box.radius * 4, 1.5)
        facing = front(stage, p.subject.name)
        # Lights further away to frame a larger thing are brighter, so it is lit as brightly.
        key = p.power * (reach / 1.5) ** 2
        for role, angle, power, height, size in (
            ("key", p.key_side, key, 0.6, 1.0),
            ("fill", -p.key_side * 0.8, key / p.contrast, 0.2, 2.0),
            ("rim", 170.0, key * 0.8, 0.9, 0.6),
        ):
            turn = math.radians(facing + angle)
            at = box.centre + Vec(math.sin(turn) * reach, -math.cos(turn) * reach, reach * height)
            stage.light(
                "area",
                name=f"{role}_{p.subject.name}",
                at=at,
                colour=p.colour,
                power=power,
                aim=box.centre,
                size=size,
            )
