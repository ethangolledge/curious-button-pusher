"""A steel filing cabinet with four drawers."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec
from content.blender.shapes import drawers, slab

WIDTH, DEPTH, HEIGHT = 0.47, 0.62, 1.32


class FilingCabinet(Prop):
    name = "filing_cabinet"
    names = ("file cabinet", "cabinet", "records cabinet", "archive cabinet")

    def build(self, stage: Stage, name: str) -> Thing:
        cabinet = stage.group(name)
        slab(stage, cabinet, f"{name}.body", Vec(WIDTH, DEPTH, HEIGHT), Vec(), "metal", 0.006)
        drawers(
            stage,
            cabinet,
            name,
            at=Vec(0, -DEPTH / 2, 0),
            width=WIDTH,
            height=HEIGHT,
            count=4,
            facing_y=-1,
            role="metal",
        )
        return cabinet
