"""An actor travels along one of the layout's paths, facing the way it goes: a figure crossing
a room, a boat along a river, a plane across the sky (not upright, banking into turns)."""

from dataclasses import dataclass
from typing import Annotated, Literal

from content.blender.api import Stage
from content.blender.blocks.base import About, Action, Range, Ref
from content.blender.motion import route, travel


@dataclass(frozen=True)
class Settings:
    actor: Annotated[Ref, About("the actor that travels")]
    path: Annotated[Ref, About("a path in the layout")]
    start: Annotated[float, Range(0, 1, "when it sets off, as a fraction of the shot")] = 0.0
    end: Annotated[float, Range(0, 1, "when it arrives, as a fraction of the shot")] = 1.0
    ease: Literal["linear", "in", "out", "in_out"] = "in_out"
    bank: Annotated[float, Range(0, 1, "how much it leans into bends")] = 0.0
    upright: Annotated[
        bool, About("keep its nose level; no lets it climb and dive with the path")
    ] = True


class Travel(Action):
    name = "travel"
    settings = Settings
    example = Settings(actor=Ref("thing"), path=Ref("across"))

    def build(self, stage: Stage, p: Settings) -> None:
        poses = travel(
            route(stage, p.path.name),
            stage.frames,
            ease=p.ease,
            start=p.start,
            end=p.end,
            bank=p.bank,
            upright=p.upright,
        )
        stage.animate(stage.actor(p.actor.name), poses)
