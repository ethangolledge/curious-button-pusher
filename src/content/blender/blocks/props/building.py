"""A building of any kind: a house, a block of flats, an office tower, a warehouse; any
number of storeys, its windows in rows (some lit at night)."""

from dataclasses import dataclass
from typing import Annotated, Literal

from content.blender.api import Role, Stage, Thing
from content.blender.blocks.base import Prop, Range
from content.blender.maths import Vec

STOREY = 3.2
# Each style: width, depth, its walls, the storeys it has unless told, and its windows'
# width and how far apart they are.
STYLES: dict[str, tuple[float, float, Role, int, float, float]] = {
    "house": (9.0, 8.0, "brick", 2, 1.2, 2.6),
    "flats": (12.0, 10.0, "brick", 5, 1.2, 2.4),
    "tower": (16.0, 16.0, "glass", 20, 2.6, 2.8),
    "warehouse": (24.0, 16.0, "concrete", 1, 3.0, 6.0),
}


@dataclass(frozen=True)
class Settings:
    style: Literal["house", "flats", "tower", "warehouse"] = "flats"
    storeys: Annotated[int, Range(0, 80, "floors; 0 for the style's own")] = 0
    lit: Annotated[float, Range(0, 1, "the share of windows lit")] = 0.18


class Building(Prop):
    name = "building"
    names = ("block of flats", "office block", "tower block", "apartment building", "house",
             "skyscraper", "office tower", "warehouse")  # fmt: skip
    settings = Settings
    example = Settings()

    def build(self, stage: Stage, name: str) -> Thing:
        p: Settings = self.p
        wide, deep, walls, storeys, window, spacing = STYLES[p.style]
        storeys = p.storeys or storeys
        building = stage.group(name)
        stage.shape("box", Vec(wide, deep, STOREY * storeys), Vec(), role=walls,
                    name=f"{name}.walls", parent=building)  # fmt: skip
        stage.shape("box", Vec(wide + 0.4, deep + 0.4, 0.4), Vec(0, 0, STOREY * storeys),
                    role="concrete", name=f"{name}.roof", parent=building)  # fmt: skip
        chance = stage.random(name)
        columns = max(1, int(wide / spacing))
        for storey in range(storeys):
            for column in range(columns):
                x = (column - (columns - 1) / 2) * spacing
                role: Role = "bulb" if chance.random() < p.lit else "glass"
                stage.shape("box", Vec(window, 0.06, 1.5),
                            Vec(x, -deep / 2 - 0.02, storey * STOREY + 0.9), role=role,
                            name=f"{name}.window_{storey}_{column}", parent=building)  # fmt: skip
        return building
