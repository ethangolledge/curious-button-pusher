"""A long corridor with doors along both walls and lights down the ceiling. Paths: corridor
(down its length, away from the near end). Marks: start, end, door_0…, light_0…, and the
room's marks."""

from dataclasses import dataclass
from typing import Annotated

from content.blender.api import Mark, Stage
from content.blender.blocks.base import Layout, Range
from content.blender.maths import FRONT, Vec
from content.blender.sets import room

WIDTH, HEIGHT = 2.2, 2.7


@dataclass(frozen=True)
class Settings:
    length: Annotated[float, Range(6, 80, "metres")] = 24.0
    doors: Annotated[int, Range(0, 20, "doors along each wall")] = 4


class Corridor(Layout):
    name = "corridor"
    settings = Settings
    example = Settings(length=8, doors=1)

    def build(self, stage: Stage, p: Settings) -> None:
        half = p.length / 2
        room(stage, WIDTH, p.length, HEIGHT, window=False)
        for index in range(p.doors):
            y = -half + (index + 1) * p.length / (p.doors + 1)
            for side in (-1, 1):
                name = f"door_{side + 1}_{index}"
                # Set against the wall, standing proud of it.
                stage.shape(
                    "box",
                    Vec(0.06, 0.95, 2.1),
                    Vec(side * (WIDTH / 2 - 0.03), y, 0),
                    role="dark_wood",
                    name=name,
                )
                stage.mark(Mark(name, Vec(side * (WIDTH / 2 - 0.4), y, 0), Vec(-side, 0, 0)))
        lights = max(2, int(p.length / 4))
        for index in range(lights):
            y = -half + (index + 0.5) * p.length / lights
            stage.shape(
                "box",
                Vec(0.5, 1.0, 0.04),
                Vec(0, y, HEIGHT - 0.04),
                role="bulb",
                name=f"panel_{index}",
            )
            stage.mark(Mark(f"light_{index}", Vec(0, y, HEIGHT - 0.1), FRONT))
        stage.mark(Mark("start", Vec(0, -half + 0.8, 0), Vec(0, 1, 0)))
        stage.mark(Mark("end", Vec(0, half - 0.8, 0), FRONT))
        stage.path("corridor", [Vec(0, -half + 0.6, 0), Vec(0, half - 1.2, 0)])
