"""An empty room: floor, walls, ceiling, and a window in the back wall (blinds optional).
Marks: centre, back_wall, window, ceiling_centre, door (with a door). Paths: across."""

from dataclasses import dataclass
from typing import Annotated

from content.blender.api import Stage
from content.blender.blocks.base import Layout, Range
from content.blender.sets import room


@dataclass(frozen=True)
class Settings:
    width: Annotated[float, Range(2, 30, "metres")] = 5.0
    depth: Annotated[float, Range(2, 30, "metres")] = 4.5
    height: Annotated[float, Range(2.2, 12, "metres")] = 2.8
    window: bool = True
    blinds: bool = False
    door: bool = False


class Room(Layout):
    name = "room"
    settings = Settings
    example = Settings()

    def build(self, stage: Stage, p: Settings) -> None:
        room(stage, p.width, p.depth, p.height, window=p.window, blinds=p.blinds, door=p.door)
