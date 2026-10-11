"""A model put exactly where the shot's composer worked out it goes (`staging/compose.py`):
standing at a point, turned to a heading. What the composer places, every placed thing
is: a cup on a table, a man in a chair, a chair round a table."""

from dataclasses import dataclass
from typing import Annotated

from content.blender.api import Stage
from content.blender.blocks.base import Actor, Range
from content.blender.maths import FRONT, UP, Vec, axis_angle


@dataclass(frozen=True)
class Settings:
    x: Annotated[float, Range(-500, 500, "metres right of the centre")] = 0.0
    y: Annotated[float, Range(-500, 500, "metres back from the centre")] = 0.0
    z: Annotated[float, Range(-50, 200, "metres up: where its base stands")] = 0.0
    heading: Annotated[float, Range(-360, 360, "degrees turned from facing the front")] = 0.0
    height: Annotated[float, Range(0, 200, "metres tall; 0 keeps the model's own size")] = 0.0


class Put(Actor):
    name = "put"
    settings = Settings
    example = Settings(x=0.2, z=0.75, heading=30)

    def build(self, stage: Stage, p: Settings, actor_id: str, model: str) -> None:
        thing = stage.model(model, name=actor_id, height=p.height or None)
        stage.place(thing, Vec(p.x, p.y, p.z), facing=axis_angle(UP, p.heading).rotate(FRONT))
        stage.cast(actor_id, thing)
