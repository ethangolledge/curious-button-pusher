"""An actor travels along one of the layout's paths, facing the way it goes: a figure crossing
a room, a boat along a river, a plane across the sky (not upright, banking into turns). A
person walks as they go: their walk played as fast as they travel, so their feet keep pace."""

from dataclasses import dataclass
from typing import Annotated, Literal

from content.blender.api import Stage
from content.blender.blocks.base import About, Action, Range, Ref
from content.blender.maths import Curve, Partway, length
from content.blender.motion import distances, route, travel


@dataclass(frozen=True)
class Settings:
    actor: Annotated[Ref, About("the actor that travels")]
    path: Annotated[Ref, About("a path in the layout")]
    start: Annotated[float, Range(0, 1, "when it sets off, as a fraction of the shot")] = 0.0
    end: Annotated[float, Range(0, 1, "when it arrives, as a fraction of the shot")] = 1.0
    ease: Literal["linear", "in", "out", "in_out"] = "in_out"
    bank: Annotated[float, Range(0, 1, "how much it leans into bends")] = 0.0
    upright: Annotated[
        bool, About("keep its nose level; no lets it climb and dive with the path")
    ] = True
    speed: Annotated[
        float, Range(0, 100, "metres a second at most, 0 for any: a walker goes about 1.4")
    ] = 0.0
    gait: Annotated[str, About("a person's walk (a library motion), played as they go")] = ""
    stride: Annotated[
        float, Range(0, 10, "metres a second the walk carries them at, played as it is")
    ] = 0.0


class Travel(Action):
    name = "travel"
    settings = Settings
    example = Settings(actor=Ref("thing"), path=Ref("across"))

    def build(self, stage: Stage, p: Settings) -> None:
        path: Curve = route(stage, p.path.name)
        if p.speed:
            # No faster than its pace: a walker given too long a path for the time stops short
            # rather than sliding along it.
            seconds = (p.end - p.start) * stage.frames / stage.fps
            fraction = min(1.0, p.speed * seconds / max(length(path), 1e-6))
            path = Partway(path, fraction) if fraction < 1 else path
        poses = travel(
            path,
            stage.frames,
            ease=p.ease,
            start=p.start,
            end=p.end,
            bank=p.bank,
            upright=p.upright,
        )
        actor = stage.actor(p.actor.name)
        stage.animate(actor, poses)
        if p.gait and p.stride:
            # The walk played as fast as they go, so their feet keep pace with the ground.
            walked = distances(poses)[-1]
            seconds = max((p.end - p.start) * stage.frames / stage.fps, 1e-6)
            begins = round(p.start * stage.frames) + 1
            stage.play(actor, p.gait, start_frame=begins, speed=walked / seconds / p.stride)
