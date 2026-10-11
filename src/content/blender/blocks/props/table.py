"""A table of any kind: a kitchen or dining table, a low coffee table, a small round side
table, a long boardroom table on pedestals. Its style sets its size and legs; a width or
depth given makes it that size."""

from dataclasses import dataclass
from typing import Annotated, Literal

from content.blender.api import Role, Stage, Thing
from content.blender.blocks.base import Prop, Range
from content.blender.maths import Vec
from content.blender.shapes import legs, slab

# Each style: width, depth and height (metres), round or not, and on legs or pedestals.
STYLES = {
    "kitchen": (1.4, 0.8, 0.75, False, "legs"),
    "dining": (1.9, 0.95, 0.75, False, "legs"),
    "coffee": (1.1, 0.55, 0.45, False, "legs"),
    "side": (0.55, 0.55, 0.6, True, "pedestal"),
    "conference": (4.8, 1.3, 0.75, False, "pedestals"),
}


@dataclass(frozen=True)
class Settings:
    style: Literal["kitchen", "dining", "coffee", "side", "conference"] = "kitchen"
    width: Annotated[float, Range(0, 12, "metres long; 0 for the style's own")] = 0.0
    depth: Annotated[float, Range(0, 4, "metres across; 0 for the style's own")] = 0.0
    material: Literal["wood", "dark_wood", "metal", "glass", "stone"] = "wood"


class Table(Prop):
    name = "table"
    names = (
        "kitchen table", "dining table", "wooden table", "side table", "coffee table",
        "boardroom table", "conference table", "meeting table", "committee table",
    )  # fmt: skip
    capabilities = frozenset({"surface"})
    settings = Settings
    example = Settings()

    def build(self, stage: Stage, name: str) -> Thing:
        p: Settings = self.p
        wide, deep, tall, round_top, stands = STYLES[p.style]
        wide, deep = p.width or wide, p.depth or deep
        role: Role = p.material
        table = stage.group(name)
        top = Vec(wide, deep, 0.045)
        if round_top:
            stage.shape("cylinder", top, Vec(0, 0, tall - 0.045), role=role,
                        name=f"{name}.top", parent=table)  # fmt: skip
        else:
            slab(stage, table, f"{name}.top", top, Vec(0, 0, tall - 0.045), role, 0.01)
        frame: Role = "dark_wood" if role in ("glass", "stone") else role
        if stands == "legs":
            legs(stage, table, name, width=wide, depth=deep, height=tall - 0.045,
                 thickness=0.06, role=frame)  # fmt: skip
        elif stands == "pedestal":
            stage.shape("cylinder", Vec(0.08, 0.08, tall - 0.045), Vec(), role=frame,
                        name=f"{name}.pedestal", parent=table)  # fmt: skip
            stage.shape("cylinder", Vec(deep * 0.6, deep * 0.6, 0.03), Vec(), role=frame,
                        name=f"{name}.foot", parent=table)  # fmt: skip
        else:
            # Between the places where people sit, not where their legs go.
            for side in (-1, 1):
                slab(stage, table, f"{name}.pedestal_{side + 1}",
                     Vec(min(0.5, wide * 0.12), deep * 0.55, tall - 0.045),
                     Vec(side * wide * 0.21, 0, 0), frame)  # fmt: skip
        return table
