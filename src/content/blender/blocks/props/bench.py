"""A park bench of slats on iron legs."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec


class Bench(Prop):
    name = "bench"
    names = ("park bench", "seat", "garden bench")
    capabilities = frozenset({"seat"})

    def build(self, stage: Stage, name: str) -> Thing:
        bench = stage.group(name)
        for side in (-1, 1):
            stage.shape(
                "box",
                Vec(0.06, 0.5, 0.45),
                Vec(side * 0.8, 0, 0),
                role="metal",
                name=f"{name}.leg_{side + 1}",
                parent=bench,
            )
            stage.shape(
                "box",
                Vec(0.06, 0.06, 0.45),
                Vec(side * 0.8, 0.22, 0.45),
                role="metal",
                name=f"{name}.post_{side + 1}",
                parent=bench,
            )
        for slat in range(4):
            stage.shape(
                "box",
                Vec(1.8, 0.1, 0.035),
                Vec(0, -0.18 + slat * 0.12, 0.45),
                role="wood",
                name=f"{name}.seat_{slat}",
                parent=bench,
                bevel=0.005,
            )
        for slat in range(2):
            stage.shape(
                "box",
                Vec(1.8, 0.035, 0.1),
                Vec(0, 0.24, 0.62 + slat * 0.14),
                role="wood",
                name=f"{name}.back_{slat}",
                parent=bench,
                bevel=0.005,
            )
        return bench
