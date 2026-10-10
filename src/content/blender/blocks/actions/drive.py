"""A vehicle drives along one of the layout's paths: it faces the road, its body rolls a
little into bends, and its wheels (parts named `wheel…`) turn with the distance covered."""

import math
from dataclasses import dataclass
from typing import Annotated, Literal

from content.blender.api import Stage
from content.blender.blocks.base import About, Action, Range, Ref
from content.blender.maths import Vec
from content.blender.motion import distances, route, travel


@dataclass(frozen=True)
class Settings:
    vehicle: Annotated[Ref, About("the vehicle actor")]
    path: Annotated[Ref, About("a road path in the layout")]
    start: Annotated[float, Range(0, 1, "when it sets off, as a fraction of the shot")] = 0.0
    end: Annotated[float, Range(0, 1, "when it arrives, as a fraction of the shot")] = 1.0
    ease: Literal["linear", "in", "out", "in_out"] = "linear"
    roll: Annotated[float, Range(0, 1, "how much the body leans into bends")] = 0.15


class Drive(Action):
    name = "drive"
    settings = Settings
    needs = {"vehicle": frozenset({"vehicle"})}
    example = Settings(vehicle=Ref("car"), path=Ref("road"))

    def build(self, stage: Stage, p: Settings) -> None:
        car = stage.actor(p.vehicle.name)
        poses = travel(
            route(stage, p.path.name),
            stage.frames,
            ease=p.ease,
            start=p.start,
            end=p.end,
            bank=p.roll,
        )
        stage.animate(car, poses)
        covered = distances(poses)
        for wheel in stage.parts(car, "wheel"):
            radius = max(stage.bounds(wheel).size.z / 2, 0.05)
            turns = [
                (pose.frame, math.degrees(gone / radius))
                for pose, gone in zip(poses, covered, strict=True)
            ]
            stage.spin(wheel, Vec(1, 0, 0), turns)
