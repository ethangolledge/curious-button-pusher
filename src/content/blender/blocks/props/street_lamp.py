"""A street lamp: a tall post with a lantern arm. Its light is placed at the part named `bulb`."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec

HEIGHT = 5.0


class StreetLamp(Prop):
    name = "street_lamp"
    names = ("lamp post", "streetlight", "lamppost", "street light")
    capabilities = frozenset({"light"})

    def build(self, stage: Stage, name: str) -> Thing:
        lamp = stage.group(name)
        stage.shape(
            "cylinder", Vec(0.22, 0.22, 0.4), Vec(), role="metal", name=f"{name}.foot", parent=lamp
        )
        stage.shape(
            "cylinder",
            Vec(0.11, 0.11, HEIGHT),
            Vec(),
            role="metal",
            name=f"{name}.post",
            parent=lamp,
        )
        stage.shape(
            "box",
            Vec(0.06, 0.9, 0.06),
            Vec(0, -0.42, HEIGHT - 0.06),
            role="metal",
            name=f"{name}.arm",
            parent=lamp,
        )
        stage.shape(
            "funnel",
            Vec(0.45, 0.45, 0.22),
            Vec(0, -0.85, HEIGHT - 0.3),
            role="metal",
            name=f"{name}.hood",
            parent=lamp,
        )
        stage.shape(
            "sphere",
            Vec(0.14, 0.14, 0.14),
            Vec(0, -0.85, HEIGHT - 0.28),
            role="bulb",
            name=f"{name}.bulb",
            parent=lamp,
        )
        return lamp
