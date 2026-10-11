"""A character standing on a mark, playing one of its motions: a rigged figure from the model
library (a public figure made once and kept), or any model with a skeleton."""

from dataclasses import dataclass
from typing import Annotated

from content.blender.api import Stage
from content.blender.blocks.base import About, Actor, Range, Ref
from content.blender.sets import moved, stand


@dataclass(frozen=True)
class Settings:
    at: Annotated[Ref, About("a mark in the layout")]
    motion: Annotated[str, About("one of the model's motions; empty keeps it still")] = ""
    start: Annotated[float, Range(0, 1, "when the motion starts, as a fraction of the shot")] = 0.0
    speed: Annotated[float, Range(0.1, 4, "how fast the motion plays")] = 1.0
    turn: Annotated[float, Range(-180, 180, "degrees from the way the mark faces")] = 0.0
    height: Annotated[float, Range(0, 3, "metres tall; 0 keeps the model's own size")] = 0.0
    across: Annotated[float, Range(-20, 20, "metres to the right of the mark")] = 0.0
    along: Annotated[float, Range(-20, 20, "metres behind the mark")] = 0.0


class Figure(Actor):
    name = "figure"
    settings = Settings
    example = Settings(at=Ref("centre"))

    def build(self, stage: Stage, p: Settings, actor_id: str, model: str) -> None:
        figure = stage.model(model, name=actor_id, height=p.height or None)
        mark = moved(stage.find_mark(p.at.name), turn=p.turn, across=p.across, along=p.along)
        stand(stage, figure, mark)
        if p.motion:
            stage.play(
                figure, p.motion, start_frame=round(p.start * stage.frames) + 1, speed=p.speed
            )
        stage.cast(actor_id, figure)
