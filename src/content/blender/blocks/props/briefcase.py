"""A hard leather briefcase with a handle, standing upright."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec


class Briefcase(Prop):
    name = "briefcase"
    names = ("attache case", "case", "suitcase", "document case")

    def build(self, stage: Stage, name: str) -> Thing:
        case = stage.group(name)
        stage.shape(
            "box",
            Vec(0.45, 0.11, 0.33),
            Vec(),
            role="leather",
            name=f"{name}.body",
            parent=case,
            bevel=0.008,
        )
        stage.shape(
            "box",
            Vec(0.12, 0.025, 0.035),
            Vec(0, 0, 0.33),
            role="leather",
            name=f"{name}.handle",
            parent=case,
            bevel=0.005,
        )
        for side in (-1, 1):
            stage.shape(
                "box",
                Vec(0.03, 0.115, 0.02),
                Vec(side * 0.13, 0, 0.29),
                role="metal",
                name=f"{name}.latch_{side + 1}",
                parent=case,
            )
        return case
