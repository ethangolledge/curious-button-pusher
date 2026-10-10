"""Open ground to the horizon: a field, a desert, a car park, a runway. A road runs across it.
Paths: road (left to right across the view), approach (towards the camera from afar), sky
(a high arc for things that fly). Marks: centre, far."""

from dataclasses import dataclass
from typing import Literal

from content.blender.api import Mark, Stage
from content.blender.blocks.base import Layout
from content.blender.maths import FRONT, Vec
from content.blender.sets import ground


@dataclass(frozen=True)
class Settings:
    surface: Literal["ground", "concrete", "stone", "road"] = "ground"
    road: bool = True


class OpenGround(Layout):
    name = "open_ground"
    settings = Settings
    example = Settings()

    def build(self, stage: Stage, p: Settings) -> None:
        ground(stage, role=p.surface)
        if p.road:
            stage.shape("box", Vec(400, 7, 0.02), Vec(0, 0, 0), role="road", name="road")
        stage.path("road", [Vec(-60, -1.75, 0.02), Vec(60, -1.75, 0.02)])
        stage.path("approach", [Vec(0, 120, 0.02), Vec(0, 8, 0.02)])
        stage.path("sky", [Vec(-150, 80, 40), Vec(0, 40, 60), Vec(150, 80, 40)])
        stage.mark(Mark("centre", Vec(), FRONT))
        stage.mark(Mark("far", Vec(0, 60, 0), FRONT))
