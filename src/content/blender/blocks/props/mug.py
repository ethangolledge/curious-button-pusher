"""A mug with a handle."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec


class Mug(Prop):
    name = "mug"
    names = ("cup", "coffee cup", "tea cup", "coffee mug")

    def build(self, stage: Stage, name: str) -> Thing:
        mug = stage.group(name)
        stage.shape(
            "cylinder", Vec(0.085, 0.085, 0.1), Vec(), role="paint", name=f"{name}.body", parent=mug
        )
        stage.shape(
            "box",
            Vec(0.015, 0.035, 0.06),
            Vec(0.05, 0, 0.02),
            role="paint",
            name=f"{name}.handle",
            parent=mug,
            bevel=0.006,
        )
        return mug
