"""A practical lamp: a warm light at a lamp's bulb (or at a mark), pooling on what is below it.
It can flicker, as a failing bulb does."""

from dataclasses import dataclass
from typing import Annotated

from content.blender.api import Stage
from content.blender.blocks.base import About, Light, Range, Ref
from content.blender.lighting import flicker, source


@dataclass(frozen=True)
class Settings:
    at: Annotated[Ref, About("an actor with a bulb (a lamp), or a mark")]
    colour: Annotated[str, About("hex")] = "#ffc98a"
    power: Annotated[float, Range(1, 2000, "watts")] = 60.0
    flicker: Annotated[float, Range(0, 1, "0 steady, 1 failing")] = 0.0


class Lamp(Light):
    name = "lamp"
    settings = Settings
    example = Settings(at=Ref("centre"))

    def build(self, stage: Stage, p: Settings) -> None:
        light = stage.light(
            "point",
            name=f"lamp_{p.at.name}",
            at=source(stage, p.at.name),
            colour=p.colour,
            power=p.power,
            size=0.03,
        )
        flicker(stage, light, p.power, p.flicker)
