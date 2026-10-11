"""Light from above: a soft ceiling panel, or a hard bare bulb hanging over a mark or an
actor (an interrogation table, a kitchen at night)."""

from dataclasses import dataclass
from typing import Annotated, Literal

from content.blender.api import Stage
from content.blender.blocks.base import About, Light, Range, Ref
from content.blender.lighting import flicker
from content.blender.maths import Vec
from content.blender.motion import where


@dataclass(frozen=True)
class Settings:
    over: Annotated[Ref, About("an actor or mark it hangs over")] = Ref("centre")
    kind: Literal["panel", "bulb"] = "panel"
    height: Annotated[float, Range(1, 30, "metres above the floor")] = 2.6
    colour: Annotated[str, About("hex")] = "#fff4e6"
    power: Annotated[float, Range(1, 5000, "watts")] = 300.0
    flicker: Annotated[float, Range(0, 1, "0 steady, 1 failing")] = 0.0


class Overhead(Light):
    name = "overhead"
    settings = Settings
    example = Settings()

    def build(self, stage: Stage, p: Settings) -> None:
        box = where(stage, p.over.name)
        # Above the floor, whatever it hangs over (a table, or a light's mark on the ceiling).
        at = Vec(box.centre.x, box.centre.y, p.height)
        if p.kind == "panel":
            light = stage.light(
                "area",
                name=f"overhead_{p.over.name}",
                at=at,
                colour=p.colour,
                power=p.power,
                aim=at - Vec(0, 0, 1),
                size=1.2,
            )
        else:
            light = stage.light(
                "point",
                name=f"overhead_{p.over.name}",
                at=at,
                colour=p.colour,
                power=p.power / 3,
                size=0.02,
            )
        flicker(stage, light, p.power, p.flicker)
