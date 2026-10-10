"""A 20-foot steel shipping container, its sides ribbed."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec

LENGTH, WIDTH, HEIGHT = 6.06, 2.44, 2.59


class ShippingContainer(Prop):
    name = "shipping_container"
    names = ("container", "cargo container", "freight container", "intermodal container")

    def build(self, stage: Stage, name: str) -> Thing:
        box = stage.group(name)
        stage.shape(
            "box", Vec(WIDTH, LENGTH, HEIGHT), Vec(), role="paint", name=f"{name}.body", parent=box
        )
        ribs = 24
        for index in range(ribs):
            y = (index - (ribs - 1) / 2) * LENGTH / ribs
            stage.shape(
                "box",
                Vec(WIDTH + 0.04, 0.06, HEIGHT - 0.2),
                Vec(0, y, 0.1),
                role="paint",
                name=f"{name}.rib_{index}",
                parent=box,
            )
        return box
