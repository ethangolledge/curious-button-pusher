"""A vehicle's headlights, beams thrown ahead of it; they travel with it."""

from dataclasses import dataclass
from typing import Annotated

from content.blender.api import Stage
from content.blender.blocks.base import About, Light, Range, Ref
from content.blender.maths import FRONT, Vec


@dataclass(frozen=True)
class Settings:
    vehicle: Annotated[Ref, About("the vehicle actor")]
    power: Annotated[float, Range(10, 20000, "watts each")] = 1500.0
    colour: Annotated[str, About("hex")] = "#fff1d6"


class Headlights(Light):
    name = "headlights"
    settings = Settings
    needs = {"vehicle": frozenset({"vehicle"})}
    example = Settings(vehicle=Ref("car"))

    def build(self, stage: Stage, p: Settings) -> None:
        car = stage.actor(p.vehicle.name)
        size = stage.bounds(car).size
        # Its own width, length and height, whichever way it is turned on the road.
        width, length, height = min(size.x, size.y), max(size.x, size.y), size.z
        # Lights hang from the car, so placed in its own frame (front −Y) they move with it.
        for side in (-1, 1):
            at = Vec(side * width * 0.33, -length / 2 - 0.05, height * 0.42)
            stage.light(
                "spot",
                name=f"{p.vehicle.name}_headlight_{side + 1}",
                at=at,
                colour=p.colour,
                power=p.power,
                aim=at + FRONT * 10 - Vec(0, 0, 0.6),
                cone_degrees=55,
                size=0.05,
                parent=car,
            )
