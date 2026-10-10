"""The camera travels with a moving actor, keeping its place beside, behind, ahead of or above
it, a little behind its movements as a camera car would be."""

import math
from dataclasses import dataclass
from typing import Annotated, Literal

from content.blender.api import Stage
from content.blender.blocks.base import About, Move, Range, Ref
from content.blender.camera import Framing, Shot, distance_to_frame, film
from content.blender.maths import FRONT, UP, Samples, Vec

SIDES = {
    "left": (90.0, 0.25),
    "right": (-90.0, 0.25),
    "behind": (180.0, 0.35),
    "ahead": (0.0, 0.3),
    "above": (180.0, 2.5),
}


@dataclass(frozen=True)
class Settings:
    subject: Annotated[Ref, About("a moving actor")]
    side: Literal["left", "right", "behind", "ahead", "above"] = "left"
    framing: Framing = "medium"
    lens: Annotated[float, Range(14, 135, "mm")] = 35.0
    lag: Annotated[float, Range(0, 3, "seconds the camera trails the subject's turns")] = 0.5


class Track(Move):
    name = "track"
    settings = Settings
    example = Settings(subject=Ref("car"))

    def build(self, stage: Stage, p: Settings) -> None:
        actor = stage.actor(p.subject.name)
        poses = stage.poses(actor)
        box = stage.bounds(actor)
        lift = box.size.z / 2
        distance = distance_to_frame(box, p.lens, stage.aspect, p.framing)
        turn, rise = SIDES[p.side]
        smooth = 1 - math.exp(-1 / max(p.lag * stage.fps, 1e-6)) if p.lag else 1.0
        positions, targets = [], []
        offset = None
        for pose in poses:
            heading = pose.rotation.rotate(FRONT)
            angle = math.radians(turn)
            side = Vec(
                heading.x * math.cos(angle) - heading.y * math.sin(angle),
                heading.x * math.sin(angle) + heading.y * math.cos(angle),
                0,
            )
            wanted = side.normalised() * distance + UP * (lift + distance * rise * 0.3)
            offset = wanted if offset is None else offset.lerp(wanted, smooth)
            centre = pose.at + UP * lift
            positions.append(centre + offset)
            targets.append(centre)
        film(
            stage,
            Shot(Samples(tuple(positions)), Samples(tuple(targets)), p.lens, p.lens),
            ease="linear",
        )
