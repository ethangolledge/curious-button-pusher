"""A vehicle on one of the layout's roads, facing along it, ready to drive."""

from dataclasses import dataclass
from typing import Annotated

from content.blender.api import Stage
from content.blender.blocks.base import About, Actor, Range, Ref
from content.blender.maths import direction_at
from content.blender.motion import route


@dataclass(frozen=True)
class Settings:
    path: Annotated[Ref, About("a road path in the layout")]
    at: Annotated[float, Range(0, 1, "how far along the path it stands")] = 0.0


class Vehicle(Actor):
    name = "vehicle"
    settings = Settings
    example = Settings(path=Ref("road"))

    def build(self, stage: Stage, p: Settings, actor_id: str, model: str) -> None:
        road = route(stage, p.path.name)
        car = stage.model(model, name=actor_id)
        stage.place(car, road.at(p.at), facing=direction_at(road, p.at))
        stage.cast(actor_id, car)
