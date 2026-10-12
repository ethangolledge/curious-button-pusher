"""An actor turns where it stands: towards something (a figure turning to the window), or by
a number of degrees (a safe's dial, a globe spinning)."""

from dataclasses import dataclass
from typing import Annotated, Literal

from content.blender.api import Pose, Stage
from content.blender.blocks.base import About, Action, Range, Ref
from content.blender.maths import (
    UP,
    angle_between,
    axis_angle,
    heading_rotation,
    progress,
    slerp,
)
from content.blender.motion import where


@dataclass(frozen=True)
class Settings:
    actor: Annotated[Ref, About("the actor that turns")]
    towards: Annotated[str, About("an actor or mark to face, or empty to turn by degrees")] = ""
    degrees: Annotated[float, Range(-3600, 3600, "how far it turns, when not turning towards")] = (
        90.0
    )
    start: Annotated[float, Range(0, 1, "when it starts, as a fraction of the shot")] = 0.2
    end: Annotated[float, Range(0, 1, "when it stops, as a fraction of the shot")] = 0.6
    ease: Literal["linear", "in", "out", "in_out"] = "in_out"
    rate: Annotated[
        float, Range(0, 3600, "degrees a second at most, 0 for any: a person turns about 90")
    ] = 0.0


class Turn(Action):
    name = "turn"
    settings = Settings
    example = Settings(actor=Ref("thing"))

    def build(self, stage: Stage, p: Settings) -> None:
        actor = stage.actor(p.actor.name)
        rest = stage.poses(actor)[0]
        goal = heading_rotation(where(stage, p.towards).centre - rest.at) if p.towards else None
        angle = angle_between(rest.rotation, goal) if goal else abs(p.degrees)
        end, share = p.end, 1.0
        if p.rate and angle:
            # No faster than it can turn: it takes longer, and if the shot ends first it is
            # still turning.
            shot = stage.frames / stage.fps
            needed = angle / p.rate / shot
            end = min(1.0, p.start + max(p.end - p.start, needed))
            share = min(1.0, (end - p.start) / needed)
        amounts = [u * share for u in progress(stage.frames, p.ease, p.start, end)]
        if goal is not None:
            turned = [slerp(rest.rotation, goal, u) for u in amounts]
        else:
            turned = [axis_angle(UP, p.degrees * u) * rest.rotation for u in amounts]
        stage.animate(actor, [Pose(i + 1, rest.at, r) for i, r in enumerate(turned)])
