"""A deep upholstered armchair."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec


class Armchair(Prop):
    name = "armchair"
    names = ("easy chair", "club chair", "chair", "lounge chair")
    capabilities = frozenset({"seat"})

    def build(self, stage: Stage, name: str) -> Thing:
        chair = stage.group(name)
        stage.shape(
            "box",
            Vec(0.85, 0.85, 0.42),
            Vec(),
            role="leather",
            name=f"{name}.base",
            parent=chair,
            bevel=0.05,
        )
        stage.shape(
            "box",
            Vec(0.85, 0.2, 0.55),
            Vec(0, 0.32, 0.4),
            role="leather",
            name=f"{name}.back",
            parent=chair,
            bevel=0.06,
        )
        for side in (-1, 1):
            stage.shape(
                "box",
                Vec(0.16, 0.8, 0.25),
                Vec(side * 0.345, 0, 0.4),
                role="leather",
                name=f"{name}.arm_{side + 1}",
                parent=chair,
                bevel=0.06,
            )
        return chair
