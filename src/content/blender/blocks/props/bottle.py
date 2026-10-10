"""A glass bottle."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec


class Bottle(Prop):
    name = "bottle"
    names = ("wine bottle", "whisky bottle", "beer bottle", "liquor bottle")

    def build(self, stage: Stage, name: str) -> Thing:
        bottle = stage.group(name)
        stage.shape(
            "cylinder",
            Vec(0.08, 0.08, 0.2),
            Vec(),
            role="glass",
            name=f"{name}.body",
            parent=bottle,
        )
        stage.shape(
            "cone",
            Vec(0.08, 0.08, 0.06),
            Vec(0, 0, 0.2),
            role="glass",
            name=f"{name}.shoulder",
            parent=bottle,
        )
        stage.shape(
            "cylinder",
            Vec(0.028, 0.028, 0.08),
            Vec(0, 0, 0.24),
            role="glass",
            name=f"{name}.neck",
            parent=bottle,
        )
        stage.shape(
            "cylinder",
            Vec(0.084, 0.084, 0.08),
            Vec(0, 0, 0.06),
            role="paper",
            name=f"{name}.label",
            parent=bottle,
        )
        return bottle
