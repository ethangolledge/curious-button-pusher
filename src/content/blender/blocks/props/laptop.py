"""An open laptop, its screen lit."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec


class Laptop(Prop):
    name = "laptop"
    names = ("notebook computer", "computer", "macbook", "portable computer")
    capabilities = frozenset({"keyboard", "screen"})

    def build(self, stage: Stage, name: str) -> Thing:
        laptop = stage.group(name)
        stage.shape(
            "box",
            Vec(0.32, 0.22, 0.015),
            Vec(),
            role="metal",
            name=f"{name}.base",
            parent=laptop,
            bevel=0.004,
        )
        stage.shape(
            "box",
            Vec(0.27, 0.1, 0.002),
            Vec(0, -0.02, 0.015),
            role="plastic",
            name=f"{name}.keys",
            parent=laptop,
        )
        lid = stage.group(f"{name}.lid", Vec(0, 0.11, 0.015), parent=laptop)
        stage.shape(
            "box",
            Vec(0.32, 0.008, 0.21),
            Vec(),
            role="metal",
            name=f"{name}.lid_back",
            parent=lid,
            turn=Vec(-15, 0, 0),
            bevel=0.003,
        )
        stage.shape(
            "box",
            Vec(0.29, 0.002, 0.18),
            Vec(0, -0.006, 0.014),
            role="screen",
            name=f"{name}.screen",
            parent=lid,
            turn=Vec(-15, 0, 0),
        )
        return laptop
