"""The camera starts exactly where a picture was taken from (a lifted picture's `camera`
mark, `docs/picture-shots.md`) and glides a little: in towards what it shows, out, sideways
past it, up or down, or round it. Things near the camera pass faster than things far away,
which a zoom over a still cannot do. It goes only as far as the picture allows: a small move
stays invisible as a trick; a large one shows edges the picture never had."""

import math
from dataclasses import dataclass
from typing import Annotated, Literal

from content.blender.api import Stage
from content.blender.blocks.base import About, Move, Range, Ref
from content.blender.camera import Shot, film
from content.blender.maths import UP, Arc, Line, Still, degrees_round
from content.blender.motion import where

Direction = Literal["in", "out", "left", "right", "up", "down", "round_left", "round_right"]
# How far each way goes unless told, as a fraction of the distance to the subject: going in
# or out reveals little the picture lacks; going sideways or round reveals the most.
AMOUNTS: dict[str, float] = {
    "in": 0.08, "out": 0.08, "up": 0.05, "down": 0.05, "left": 0.035, "right": 0.035,
    "round_left": 0.035, "round_right": 0.035,
}  # fmt: skip


@dataclass(frozen=True)
class Settings:
    origin: Annotated[Ref, About("the mark the picture was taken from")] = Ref("camera")
    subject: Annotated[Ref, About("what it moves towards or round: an actor or a mark")] = Ref(
        "ahead"
    )
    direction: Direction = "in"
    amount: Annotated[
        float,
        Range(0, 0.4, "how far, as a fraction of its distance to the subject; 0: the usual"),
    ] = 0.0
    lens: Annotated[float, Range(8, 200, "mm: the picture's own")] = 35.0
    ease: Literal["linear", "in", "out", "in_out"] = "in_out"
    # None by default: the first frame is the picture itself.
    drift: Annotated[float, Range(0, 0.05, "metres of handheld sway")] = 0.0


class Glide(Move):
    name = "glide"
    settings = Settings
    example = Settings(origin=Ref("centre"), subject=Ref("car"))

    def build(self, stage: Stage, p: Settings) -> None:
        origin = stage.find_mark(p.origin.name)
        subject = where(stage, p.subject.name).centre
        distance = (subject - origin.at).length()
        # The picture's own view: straight along the way its camera faced, as far as the
        # subject is. Every move but a sideways one keeps looking there.
        gaze = origin.at + origin.facing.normalised() * distance
        travel = (p.amount or AMOUNTS[p.direction]) * distance
        towards = (subject - origin.at).normalised()
        across = towards.cross(UP).normalised()
        if p.direction in ("round_left", "round_right"):
            offset = origin.at - gaze
            radius = offset.flat().length()
            sweep = math.degrees(travel / max(radius, 1e-6))
            position = Arc(
                gaze, radius, degrees_round(offset), sweep if p.direction == "round_left" else
                -sweep, offset.z, offset.z,
            )  # fmt: skip
            film(stage, Shot(position, Still(gaze), p.lens, p.lens), ease=p.ease, drift=p.drift)
            return
        step = {
            "in": towards, "out": -towards, "right": across, "left": -across, "up": UP,
            "down": -UP,
        }[p.direction] * travel  # fmt: skip
        sideways = p.direction in ("left", "right")
        target = Line(gaze, gaze + step) if sideways else Still(gaze)
        film(
            stage,
            Shot(Line(origin.at, origin.at + step), target, p.lens, p.lens),
            ease=p.ease,
            drift=p.drift,
        )
