"""A picture from the library in the shot: a map laid flat on a table, a painting or a poster on
a wall, the view through a window (stand it a few metres behind the window's mark)."""

from dataclasses import dataclass
from typing import Annotated

from content.blender.api import Stage
from content.blender.blocks.base import About, Actor, Range, Ref
from content.blender.maths import UP, Vec, axis_angle
from content.blender.sets import resting_on


@dataclass(frozen=True)
class Settings:
    at: Annotated[Ref, About("a mark in the layout")]
    width: Annotated[float, Range(0.05, 200, "metres wide")] = 0.6
    flat: Annotated[bool, About("lying on the mark's surface, like a map on a table")] = False
    raised: Annotated[float, Range(0, 50, "metres above the mark (a picture on a wall)")] = 0.0
    behind: Annotated[float, Range(-50, 200, "metres behind the mark (a view out of a window)")] = (
        0.0
    )
    turn: Annotated[float, Range(-180, 180, "degrees from the way the mark faces")] = 0.0


class Picture(Actor):
    name = "picture"
    settings = Settings
    example = Settings(at=Ref("centre"))
    example_model = "sample_picture"

    def build(self, stage: Stage, p: Settings, actor_id: str, model: str) -> None:
        card = stage.picture(model, name=actor_id, width=p.width, lying=p.flat)
        mark = stage.find_mark(p.at.name)
        facing = axis_angle(UP, p.turn).rotate(mark.facing)
        at = resting_on(mark) - facing.normalised() * p.behind + Vec(0, 0, p.raised)
        stage.place(card, at, facing=facing)
        stage.cast(actor_id, card)
