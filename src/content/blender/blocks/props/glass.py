"""A tumbler with a finger of drink in it."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec


class Glass(Prop):
    name = "glass"
    names = ("tumbler", "whisky glass", "drink", "glass of water", "shot glass")

    def build(self, stage: Stage, name: str) -> Thing:
        glass = stage.group(name)
        stage.shape(
            "cylinder",
            Vec(0.075, 0.075, 0.09),
            Vec(),
            role="glass",
            name=f"{name}.glass",
            parent=glass,
        )
        stage.shape(
            "cylinder",
            Vec(0.066, 0.066, 0.03),
            Vec(0, 0, 0.006),
            role="wood",
            name=f"{name}.drink",
            parent=glass,
        )
        return glass
