"""A steel oil drum."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec


class Barrel(Prop):
    name = "barrel"
    names = ("oil drum", "drum", "oil barrel", "steel drum")

    def build(self, stage: Stage, name: str) -> Thing:
        barrel = stage.group(name)
        stage.shape(
            "cylinder",
            Vec(0.58, 0.58, 0.88),
            Vec(),
            role="paint",
            name=f"{name}.body",
            parent=barrel,
        )
        for ring in (0.29, 0.59):
            stage.shape(
                "cylinder",
                Vec(0.6, 0.6, 0.02),
                Vec(0, 0, ring),
                role="metal",
                name=f"{name}.ring_{round(ring * 100)}",
                parent=barrel,
            )
        return barrel
