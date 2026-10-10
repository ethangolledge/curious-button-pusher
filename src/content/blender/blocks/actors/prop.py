"""A model standing on one of the layout's marks (on its surface if it has one): a phone on
the desk, a car in the street. Several props can share a mark, moved apart by `across` and
`along`."""

from dataclasses import dataclass
from typing import Annotated

from content.blender.api import Mark, Stage
from content.blender.blocks.base import About, Actor, Range, Ref
from content.blender.maths import Vec, axis_angle
from content.blender.sets import stand


@dataclass(frozen=True)
class Settings:
    at: Annotated[Ref, About("a mark in the layout")]
    height: Annotated[float, Range(0, 60, "metres tall; 0 keeps the model's own size")] = 0.0
    turn: Annotated[float, Range(-180, 180, "degrees from the way the mark faces")] = 0.0
    across: Annotated[float, Range(-20, 20, "metres to the right of the mark")] = 0.0
    along: Annotated[float, Range(-20, 20, "metres behind the mark")] = 0.0


class Prop(Actor):
    name = "prop"
    settings = Settings
    example = Settings(at=Ref("centre"))

    def build(self, stage: Stage, p: Settings, actor_id: str, model: str) -> None:
        thing = stage.model(model, name=actor_id, height=p.height or None)
        mark = stage.find_mark(p.at.name)
        facing = axis_angle(Vec(0, 0, 1), p.turn).rotate(mark.facing)
        right = Vec(-facing.y, facing.x, 0) * -1
        moved = mark.at + right * p.across - facing * p.along
        stand(stage, thing, Mark(mark.name, moved, facing, mark.surface), facing=facing)
        stage.cast(actor_id, thing)
