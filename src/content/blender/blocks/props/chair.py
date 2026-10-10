"""A plain wooden chair with a back, facing the front."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec
from content.blender.shapes import legs, slab

SEAT, SEAT_HEIGHT, BACK_HEIGHT = 0.44, 0.45, 0.88


class Chair(Prop):
    name = "chair"
    names = ("seat", "wooden chair", "dining chair", "desk chair")
    capabilities = frozenset({"seat"})

    def build(self, stage: Stage, name: str) -> Thing:
        chair = stage.group(name)
        legs(
            stage,
            chair,
            name,
            width=SEAT,
            depth=SEAT,
            height=SEAT_HEIGHT - 0.03,
            thickness=0.035,
            inset=0.02,
        )
        slab(
            stage,
            chair,
            f"{name}.seat",
            Vec(SEAT, SEAT, 0.035),
            Vec(0, 0, SEAT_HEIGHT - 0.035),
            "dark_wood",
        )
        for side in (-1, 1):
            stage.shape(
                "box",
                Vec(0.035, 0.035, BACK_HEIGHT - SEAT_HEIGHT),
                Vec(side * (SEAT / 2 - 0.0375), SEAT / 2 - 0.0375, SEAT_HEIGHT),
                role="wood",
                name=f"{name}.post_{side + 1}",
                parent=chair,
            )
        slab(
            stage,
            chair,
            f"{name}.back",
            Vec(SEAT - 0.04, 0.025, 0.16),
            Vec(0, SEAT / 2 - 0.035, BACK_HEIGHT - 0.2),
            "dark_wood",
        )
        return chair
