"""A closed cardboard box: archives, evidence, a house move."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec


class CardboardBox(Prop):
    name = "cardboard_box"
    names = ("box", "archive box", "evidence box", "carton", "packing box")

    def build(self, stage: Stage, name: str) -> Thing:
        box = stage.group(name)
        stage.shape(
            "box",
            Vec(0.42, 0.32, 0.28),
            Vec(),
            role="card",
            name=f"{name}.body",
            parent=box,
            bevel=0.003,
        )
        stage.shape(
            "box",
            Vec(0.425, 0.325, 0.03),
            Vec(0, 0, 0.265),
            role="card",
            name=f"{name}.lid",
            parent=box,
            bevel=0.002,
        )
        return box
