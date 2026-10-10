"""An actor slides to a mark without turning: a document pushed across a desk, a glass
nudged along a bar, a crate shoved across a floor."""

from dataclasses import dataclass
from typing import Annotated, Literal

from content.blender.api import Pose, Stage
from content.blender.blocks.base import About, Action, Range, Ref
from content.blender.maths import Line, progress
from content.blender.sets import resting_on


@dataclass(frozen=True)
class Settings:
    actor: Annotated[Ref, About("the actor that slides")]
    to: Annotated[Ref, About("the mark it ends on")]
    start: Annotated[float, Range(0, 1, "when it starts, as a fraction of the shot")] = 0.2
    end: Annotated[float, Range(0, 1, "when it stops, as a fraction of the shot")] = 0.7
    ease: Literal["linear", "in", "out", "in_out"] = "out"


class Slide(Action):
    name = "slide"
    settings = Settings
    example = Settings(actor=Ref("thing"), to=Ref("centre"))

    def build(self, stage: Stage, p: Settings) -> None:
        actor = stage.actor(p.actor.name)
        rest = stage.poses(actor)[0]
        line = Line(rest.at, resting_on(stage.find_mark(p.to.name)))
        amounts = progress(stage.frames, p.ease, p.start, p.end)
        stage.animate(
            actor, [Pose(i + 1, line.at(u), rest.rotation) for i, u in enumerate(amounts)]
        )
