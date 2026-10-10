"""A writing desk: a top on two drawer pedestals, a modesty panel at the front."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec
from content.blender.shapes import drawers, slab

WIDTH, DEPTH, HEIGHT = 1.5, 0.75, 0.76


class Desk(Prop):
    name = "desk"
    names = ("writing desk", "office desk", "bureau", "work desk")

    def build(self, stage: Stage, name: str) -> Thing:
        desk = stage.group(name)
        slab(stage, desk, f"{name}.top", Vec(WIDTH, DEPTH, 0.04), Vec(0, 0, HEIGHT - 0.04), "wood")
        pedestal = 0.42
        for side in (-1, 1):
            x = side * (WIDTH / 2 - pedestal / 2 - 0.02)
            slab(
                stage,
                desk,
                f"{name}.pedestal_{side + 1}",
                Vec(pedestal, DEPTH - 0.06, HEIGHT - 0.06),
                Vec(x, 0, 0.02),
                "wood",
            )
            # Drawers face whoever sits at the desk, behind it (+Y).
            drawers(
                stage,
                desk,
                f"{name}.side_{side + 1}",
                at=Vec(x, DEPTH / 2 - 0.03, 0.02),
                width=pedestal,
                height=HEIGHT - 0.08,
                count=3,
                facing_y=1,
            )
        slab(
            stage,
            desk,
            f"{name}.panel",
            Vec(WIDTH - 2 * pedestal, 0.02, 0.4),
            Vec(0, -DEPTH / 2 + 0.06, HEIGHT - 0.45),
            "wood",
        )
        return desk
