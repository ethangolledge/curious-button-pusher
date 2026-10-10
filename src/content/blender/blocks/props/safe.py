"""A heavy steel safe with a dial and a handle."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec


class Safe(Prop):
    name = "safe"
    names = ("strongbox", "vault", "safe box", "lockbox")

    def build(self, stage: Stage, name: str) -> Thing:
        safe = stage.group(name)
        stage.shape(
            "box",
            Vec(0.6, 0.6, 0.75),
            Vec(),
            role="metal",
            name=f"{name}.body",
            parent=safe,
            bevel=0.02,
        )
        stage.shape(
            "box",
            Vec(0.5, 0.02, 0.62),
            Vec(0, -0.3, 0.06),
            role="metal",
            name=f"{name}.door",
            parent=safe,
            bevel=0.006,
        )
        stage.shape(
            "cylinder",
            Vec(0.12, 0.12, 0.03),
            Vec(0.05, -0.32, 0.45),
            role="metal",
            name=f"{name}.dial",
            parent=safe,
            turn=Vec(90, 0, 0),
        )
        stage.shape(
            "box",
            Vec(0.04, 0.06, 0.16),
            Vec(-0.15, -0.33, 0.32),
            role="metal",
            name=f"{name}.handle",
            parent=safe,
            bevel=0.01,
        )
        return safe
