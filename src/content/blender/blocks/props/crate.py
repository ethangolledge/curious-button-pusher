"""A wooden shipping crate made of planks."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec

SIZE = 0.8


class Crate(Prop):
    name = "crate"
    names = ("wooden crate", "shipping crate", "box of goods", "cargo crate")

    def build(self, stage: Stage, name: str) -> Thing:
        crate = stage.group(name)
        stage.shape(
            "box",
            Vec(SIZE * 0.96, SIZE * 0.96, SIZE * 0.96),
            Vec(0, 0, SIZE * 0.02),
            role="wood",
            name=f"{name}.body",
            parent=crate,
        )
        for level in range(4):
            z = level * SIZE / 3 - (0.04 if level == 3 else 0)
            stage.shape(
                "box",
                Vec(SIZE, SIZE, 0.04),
                Vec(0, 0, max(z, 0)),
                role="dark_wood",
                name=f"{name}.band_{level}",
                parent=crate,
                bevel=0.004,
            )
        return crate
