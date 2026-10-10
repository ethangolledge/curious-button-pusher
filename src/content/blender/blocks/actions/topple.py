"""Something falls over under gravity: a stack collapses, a glass tips off a table, a chair
goes over. The actor (or each item of a stack, the parts named `item…`) is pushed as it is
let go, and real collisions decide the rest."""

from dataclasses import dataclass
from typing import Annotated, Literal

from content.blender.api import Box, Stage
from content.blender.blocks.base import About, Action, Range, Ref
from content.blender.maths import UP, Vec

DIRECTIONS = {
    "towards": Vec(0, -1, 0),
    "away": Vec(0, 1, 0),
    "left": Vec(-1, 0, 0),
    "right": Vec(1, 0, 0),
}


@dataclass(frozen=True)
class Settings:
    actor: Annotated[Ref, About("the actor (or stack) that falls")]
    onto: Annotated[Ref, About("the mark whose surface it stands on (the floor is always solid)")]
    when: Annotated[float, Range(0, 0.9, "when it is let go, as a fraction of the shot")] = 0.2
    push: Literal["towards", "away", "left", "right"] = "towards"
    strength: Annotated[float, Range(0, 10, "metres a second it is pushed")] = 1.0


class Topple(Action):
    name = "topple"
    settings = Settings
    example = Settings(actor=Ref("thing"), onto=Ref("centre"))

    def build(self, stage: Stage, p: Settings) -> None:
        actor = stage.actor(p.actor.name)
        bodies = stage.parts(actor, "item") or [actor]
        surface = stage.find_mark(p.onto.name).surface
        floors = [Box(Vec(-200, -200, -1), Vec(200, 200, 0))]
        if surface is not None:
            floors.append(surface)
        # Pushed high up, so it tips over rather than sliding away whole.
        top = stage.bounds(actor)
        tipping = top.low.z + top.size.z * 0.6
        shove = (DIRECTIONS[p.push] + UP * 0.05) * p.strength
        push = {
            b.name: shove for b in bodies if stage.bounds(b).centre.z >= tipping or len(bodies) == 1
        }
        start = max(2, round(p.when * stage.frames))
        stage.simulate(bodies, floors=floors, start_frame=start, push=push)
