"""Sheets fall and settle on a surface, rocking like leaves as they go: papers off a desk, a
shower of banknotes, letters dropped on a floor. Each lands flat, a little apart from the
rest, at its own moment."""

import math
from dataclasses import dataclass
from typing import Annotated

from content.blender.api import Pose, Stage
from content.blender.blocks.base import About, Action, ModelName, Range, Ref
from content.blender.maths import UP, Vec, axis_angle, progress
from content.blender.sets import resting_on

SHEET = Vec(0.21, 0.297, 0.0006)  # A4


@dataclass(frozen=True)
class Settings:
    onto: Annotated[Ref, About("the mark they land on")]
    count: Annotated[int, Range(1, 200, "how many")] = 12
    item: Annotated[str, ModelName("a model or prop to drop (empty: sheets of paper)")] = ""
    spread: Annotated[float, Range(0.05, 10, "metres round the mark they land within")] = 0.5
    height: Annotated[float, Range(0.2, 20, "metres above the surface they start")] = 1.2
    start: Annotated[float, Range(0, 1, "when the first starts falling")] = 0.0
    end: Annotated[float, Range(0, 1, "when the last has landed")] = 0.9


class Scatter(Action):
    name = "scatter"
    settings = Settings
    example = Settings(onto=Ref("centre"), count=3)

    def build(self, stage: Stage, p: Settings) -> None:
        chance = stage.random(f"scatter:{p.onto.name}")
        ground = resting_on(stage.find_mark(p.onto.name))
        group = stage.group(f"scatter_{p.onto.name}")
        window = p.end - p.start
        for index in range(p.count):
            name = f"scatter_{p.onto.name}.sheet_{index}"
            if p.item:
                sheet = stage.model(p.item, name=name)
                stage.place(sheet, Vec(), parent=group)
            else:
                sheet = stage.shape("box", SHEET, Vec(), role="paper", name=name, parent=group)
            begins = p.start + chance.uniform(0, window * 0.45)
            lands = min(p.end, begins + window * chance.uniform(0.45, 0.55))
            angle, reach = chance.uniform(0, math.tau), p.spread * math.sqrt(chance.random())
            landing = ground + Vec(
                math.cos(angle) * reach, math.sin(angle) * reach, 0.0008 * (index + 1)
            )
            origin = ground + Vec(
                chance.uniform(-0.15, 0.15), chance.uniform(-0.15, 0.15), p.height
            )
            stage.animate(
                sheet,
                _fall(
                    stage, origin, landing, begins, lands, chance.uniform(0, 360), chance.random()
                ),
            )


def _fall(
    stage: Stage, origin: Vec, landing: Vec, begins: float, lands: float, yaw: float, phase: float
) -> list[Pose]:
    """A leaf's fall: down at an easing pace, swaying side to side and rocking up to 35°,
    both dying away to lie flat on landing; it turns slowly about the vertical."""
    poses = []
    for index, u in enumerate(progress(stage.frames, "out", begins, lands)):
        calm = (1 - u) ** 1.5
        sway = math.sin((u * 3.2 + phase) * math.tau)
        at = origin.lerp(landing, u) + Vec(
            sway * 0.12 * calm, math.cos((u * 2.1 + phase) * math.tau) * 0.08 * calm, 0
        )
        rock = axis_angle(Vec(1, 0, 0), 35 * sway * calm) * axis_angle(
            Vec(0, 1, 0), 20 * math.cos((u * 2.6 + phase) * math.tau) * calm
        )
        poses.append(Pose(index + 1, at, axis_angle(UP, yaw + 90 * u) * rock))
    return poses
