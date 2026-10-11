"""Sheets fall and settle on a surface, rocking like leaves as they go: papers off a desk, a
shower of banknotes, letters dropped on a floor. Each lands flat, a little apart from the
rest, at its own moment, on a clear spot: on the surface it falls onto, and never on (or
through) what already stands there."""

import math
import random
from dataclasses import dataclass
from typing import Annotated

from content.blender.api import Box, Pose, Stage
from content.blender.blocks.base import About, Action, ModelName, Range, Ref
from content.blender.maths import UP, Vec, axis_angle, progress
from content.blender.sets import resting_on

SHEET = Vec(0.21, 0.297, 0.0006)  # A4
# Random spots tried for each, to find one clear of everything else.
TRIES = 40


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
        mark = stage.find_mark(p.onto.name)
        ground = resting_on(mark)
        reach = Vec(p.spread, p.spread, 0)
        taken = stage.occupied(Box(ground - reach, ground + reach + Vec(0, 0, p.height)))
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
            size = stage.bounds(sheet).size
            landing = _clear_spot(chance, ground, p.spread, mark.surface, taken, size) + Vec(
                0, 0, 0.0008 * (index + 1)
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


def _clear_spot(
    chance: random.Random,
    ground: Vec,
    spread: float,
    surface: Box | None,
    taken: list[Box],
    size: Vec,
) -> Vec:
    """A random spot within `spread` of the mark, on its surface (if it has one) and clear of
    everything standing there; if none is clear, the first one tried on the surface."""
    half = max(size.x, size.y) / 2
    fallback = None
    for _ in range(TRIES):
        angle, reach = chance.uniform(0, math.tau), spread * math.sqrt(chance.random())
        spot = ground + Vec(math.cos(angle) * reach, math.sin(angle) * reach, 0)
        on = surface is None or (
            surface.low.x + half <= spot.x <= surface.high.x - half
            and surface.low.y + half <= spot.y <= surface.high.y - half
        )
        clear = all(
            spot.x + half <= box.low.x or box.high.x <= spot.x - half
            or spot.y + half <= box.low.y or box.high.y <= spot.y - half
            for box in taken
        )  # fmt: skip
        if on and clear:
            return spot
        if on and fallback is None:
            fallback = spot
    return fallback or ground


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
