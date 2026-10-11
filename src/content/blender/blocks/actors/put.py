"""A model put exactly where the shot's composer worked out it goes (`staging/compose.py`):
standing at a point, turned to a heading, and, for a figure with a skeleton, playing one of
its motions (breathing, talking, walking) all through the shot. What the composer places,
every placed thing is: a cup on a table, a man in a chair, a chair round a table, a glass
in a hand (held by its holder, it moves with them)."""

from dataclasses import dataclass
from typing import Annotated

from content.blender.api import Stage
from content.blender.blocks.base import About, Actor, Range
from content.blender.maths import FRONT, UP, Vec, axis_angle


@dataclass(frozen=True)
class Settings:
    x: Annotated[float, Range(-500, 500, "metres right of the centre")] = 0.0
    y: Annotated[float, Range(-500, 500, "metres back from the centre")] = 0.0
    z: Annotated[float, Range(-50, 200, "metres up: where its base stands")] = 0.0
    heading: Annotated[float, Range(-360, 360, "degrees turned from facing the front")] = 0.0
    height: Annotated[float, Range(0, 200, "metres tall; 0 keeps the model's own size")] = 0.0
    motion: Annotated[str, About("one of the model's motions; empty keeps it still")] = ""
    start: Annotated[float, Range(0, 1, "when the motion starts, as a fraction of the shot")] = 0.0
    speed: Annotated[float, Range(0.1, 4, "how fast the motion plays")] = 1.0
    # A picture (a map, a painting) on a card this wide, lying flat or upright.
    picture: Annotated[float, Range(0, 200, "metres wide, when the model is a picture")] = 0.0
    lying: bool = False
    held_by: Annotated[str, About("the actor holding it: it moves with them")] = ""


class Put(Actor):
    name = "put"
    settings = Settings
    example = Settings(x=0.2, z=0.75, heading=30)

    def build(self, stage: Stage, p: Settings, actor_id: str, model: str) -> None:
        thing = (
            stage.picture(model, name=actor_id, width=p.picture, lying=p.lying)
            if p.picture
            else stage.model(model, name=actor_id, height=p.height or None)
        )
        stage.place(thing, Vec(p.x, p.y, p.z), facing=axis_angle(UP, p.heading).rotate(FRONT))
        if p.motion:
            begins = round(p.start * stage.frames) + 1
            stage.play(thing, p.motion, start_frame=begins, speed=p.speed)
        if p.held_by:
            stage.hold(thing, stage.actor(p.held_by))
        stage.cast(actor_id, thing)
