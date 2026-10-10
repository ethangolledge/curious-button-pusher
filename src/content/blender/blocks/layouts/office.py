"""A small office: a room with a desk under the window, a chair behind it and a lamp on it.
Actors: desk, chair, desk_lamp. Marks: desk_top (stand props on the desk), desk_front,
chair, and the room's marks."""

from dataclasses import dataclass
from typing import Annotated

from content.blender.api import Mark, Stage
from content.blender.blocks.base import Layout, Range
from content.blender.maths import FRONT, Vec
from content.blender.sets import room, stand, surface_mark


@dataclass(frozen=True)
class Settings:
    width: Annotated[float, Range(3, 12, "metres")] = 4.5
    depth: Annotated[float, Range(3, 12, "metres")] = 4.0
    blinds: bool = True
    lamp: bool = True


class Office(Layout):
    name = "office"
    settings = Settings
    example = Settings()

    def build(self, stage: Stage, p: Settings) -> None:
        shell = room(stage, p.width, p.depth, 2.8, window=True, blinds=p.blinds, door=True)
        # The desk faces into the room, its back to the window, so whoever sits faces us.
        desk = stage.model("desk", name="desk")
        stage.place(desk, Vec(0, shell.back - 1.1, 0), facing=FRONT)
        stage.cast("desk", desk)
        top = surface_mark("desk_top", stage.bounds(desk))
        stage.mark(top)
        chair = stage.model("chair", name="chair")
        stage.place(chair, Vec(0, shell.back - 0.45, 0), facing=FRONT)
        stage.cast("chair", chair)
        stage.mark(Mark("chair", Vec(0, shell.back - 0.45, 0), FRONT))
        stage.mark(Mark("desk_front", Vec(0, shell.back - 1.9, 0), -FRONT))
        if p.lamp:
            lamp = stage.model("desk_lamp", name="desk_lamp")
            spot = Mark("lamp_spot", top.at + Vec(-0.5, 0.1, 0), Vec(0.6, -1, 0), top.surface)
            stand(stage, lamp, spot)
            stage.cast("desk_lamp", lamp)
