"""A plain four-legged table."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec
from content.blender.shapes import legs, slab

WIDTH, DEPTH, HEIGHT = 1.4, 0.8, 0.75


class Table(Prop):
    name = "table"
    names = ("kitchen table", "dining table", "wooden table", "side table")
    capabilities = frozenset({"surface"})

    def build(self, stage: Stage, name: str) -> Thing:
        table = stage.group(name)
        slab(stage, table, f"{name}.top", Vec(WIDTH, DEPTH, 0.04), Vec(0, 0, HEIGHT - 0.04), "wood")
        legs(stage, table, name, width=WIDTH, depth=DEPTH, height=HEIGHT - 0.04, thickness=0.06)
        return table
