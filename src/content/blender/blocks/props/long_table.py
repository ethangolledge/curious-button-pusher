"""A long meeting table on two broad pedestals: a boardroom, a committee, a negotiation."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec
from content.blender.shapes import slab

LENGTH, WIDTH, HEIGHT = 4.8, 1.3, 0.75


class LongTable(Prop):
    name = "long_table"
    names = ("boardroom table", "conference table", "meeting table", "committee table")
    capabilities = frozenset({"surface"})

    def build(self, stage: Stage, name: str) -> Thing:
        table = stage.group(name)
        slab(
            stage,
            table,
            f"{name}.top",
            Vec(LENGTH, WIDTH, 0.05),
            Vec(0, 0, HEIGHT - 0.05),
            "dark_wood",
            0.01,
        )
        for side in (-1, 1):
            slab(
                stage,
                table,
                f"{name}.pedestal_{side + 1}",
                Vec(0.5, WIDTH * 0.55, HEIGHT - 0.05),
                Vec(side * LENGTH * 0.3, 0, 0),
                "dark_wood",
            )
        return table
