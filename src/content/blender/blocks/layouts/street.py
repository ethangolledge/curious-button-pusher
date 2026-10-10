"""A city street: a two-lane road between pavements, buildings along both sides, street lamps.
Paths: road (the near lane, travelling right), road_back (the far lane, travelling left),
pavement. Marks: kerb, crossing, far_side, lamp_0… (each street lamp)."""

from dataclasses import dataclass
from typing import Annotated

from content.blender.api import Box, Mark, Stage
from content.blender.blocks.base import Layout, Range
from content.blender.maths import FRONT, Vec
from content.blender.sets import ground

ROAD, PAVEMENT = 7.0, 3.0


@dataclass(frozen=True)
class Settings:
    length: Annotated[float, Range(20, 400, "metres of street")] = 80.0
    buildings: bool = True
    lamps: Annotated[int, Range(0, 40, "street lamps on each side")] = 4


class Street(Layout):
    name = "street"
    settings = Settings
    example = Settings(length=30, lamps=1)

    def build(self, stage: Stage, p: Settings) -> None:
        ground(stage, role="concrete")
        half = p.length / 2
        stage.shape("box", Vec(p.length, ROAD, 0.02), Vec(), role="road", name="road")
        for side in (-1, 1):
            y = side * (ROAD / 2 + PAVEMENT / 2)
            stage.shape(
                "box",
                Vec(p.length, PAVEMENT, 0.15),
                Vec(0, y, 0),
                role="concrete",
                name=f"pavement_{side + 1}",
            )
        lane = ROAD / 4
        stage.path("road", [Vec(-half + 2, -lane, 0.02), Vec(half - 2, -lane, 0.02)])
        stage.path("road_back", [Vec(half - 2, lane, 0.02), Vec(-half + 2, lane, 0.02)])
        walk = -(ROAD / 2 + PAVEMENT / 2)
        stage.path("pavement", [Vec(-half + 2, walk, 0.15), Vec(half - 2, walk, 0.15)])
        stage.mark(Mark("kerb", Vec(0, walk, 0.15), FRONT))
        stage.mark(Mark("crossing", Vec(0, 0, 0.02), FRONT))
        stage.mark(Mark("far_side", Vec(0, -walk, 0.15), FRONT))
        if p.buildings:
            # Between the building fronts: the camera stays out of the buildings.
            front = ROAD / 2 + PAVEMENT + 0.2
            stage.mark(
                Mark("interior", Vec(), FRONT, Box(Vec(-half, -front, 0), Vec(half, front, 60)))
            )
        if p.buildings:
            count = max(1, int(p.length / 13))
            for side in (-1, 1):
                for index in range(count):
                    x = (index - (count - 1) / 2) * 13
                    building = stage.model("building", name=f"building_{side + 1}_{index}")
                    facing = Vec(0, -side, 0)
                    stage.place(
                        building, Vec(x, side * (ROAD / 2 + PAVEMENT + 5.2), 0), facing=facing
                    )
        for index in range(p.lamps):
            x = (index - (p.lamps - 1) / 2) * (p.length / max(p.lamps, 1))
            for side in (-1, 1):
                lamp = stage.model("street_lamp", name=f"lamp_{side + 1}_{index}")
                at = Vec(x, side * (ROAD / 2 + 0.4), 0.15)
                stage.place(lamp, at, facing=Vec(0, side, 0))
                stage.cast(f"lamp_{side + 1}_{index}", lamp)
                stage.mark(Mark(f"lamp_{side + 1}_{index}", at, Vec(0, side, 0)))
