"""A broad-leaved tree: a trunk under a rounded crown."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec


class Tree(Prop):
    name = "tree"
    names = ("oak", "street tree", "park tree", "elm")

    def build(self, stage: Stage, name: str) -> Thing:
        tree = stage.group(name)
        stage.shape(
            "cylinder",
            Vec(0.4, 0.4, 3.2),
            Vec(),
            role="dark_wood",
            name=f"{name}.trunk",
            parent=tree,
        )
        chance = stage.random(name)
        for index in range(5):
            offset = Vec(
                chance.uniform(-0.9, 0.9), chance.uniform(-0.9, 0.9), chance.uniform(2.6, 3.6)
            )
            size = chance.uniform(2.0, 3.0)
            stage.shape(
                "sphere",
                Vec(size, size, size * 0.85),
                offset,
                role="foliage",
                name=f"{name}.crown_{index}",
                parent=tree,
            )
        return tree
