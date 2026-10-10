"""Every street lamp in the layout lit (its actors named `lamp_…`), pooling sodium-orange or
cold white light on the ground below."""

from dataclasses import dataclass
from typing import Annotated, Literal

from content.blender.api import Stage
from content.blender.blocks.base import Light, Range
from content.blender.lighting import flicker, source
from content.blender.maths import Vec

COLOURS = {"sodium": "#ffae5c", "white": "#e8f0ff"}


@dataclass(frozen=True)
class Settings:
    colour: Literal["sodium", "white"] = "sodium"
    power: Annotated[float, Range(10, 5000, "watts each")] = 600.0
    flicker: Annotated[float, Range(0, 1, "how much one failing lamp stutters")] = 0.0


class Streetlights(Light):
    name = "streetlights"
    settings = Settings
    example = Settings()

    def build(self, stage: Stage, p: Settings) -> None:
        lamps = [mark.name for mark in stage.marks() if mark.name.startswith("lamp_")]
        for index, name in enumerate(lamps):
            at = source(stage, name)
            light = stage.light(
                "spot",
                name=f"{name}_light",
                at=at,
                colour=COLOURS[p.colour],
                power=p.power,
                aim=at - Vec(0, 0, 1),
                cone_degrees=110,
                size=0.15,
            )
            if index == 0:
                flicker(stage, light, p.power, p.flicker)
