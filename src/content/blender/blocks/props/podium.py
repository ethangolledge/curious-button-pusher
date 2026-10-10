"""A speaker's lectern with a microphone on a stalk."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec


class Podium(Prop):
    name = "podium"
    names = ("lectern", "rostrum", "speaker's stand", "pulpit")

    def build(self, stage: Stage, name: str) -> Thing:
        podium = stage.group(name)
        stage.shape(
            "box",
            Vec(0.65, 0.5, 1.1),
            Vec(),
            role="dark_wood",
            name=f"{name}.body",
            parent=podium,
            bevel=0.01,
        )
        stage.shape(
            "box",
            Vec(0.7, 0.45, 0.04),
            Vec(0, 0.02, 1.1),
            role="dark_wood",
            name=f"{name}.top",
            parent=podium,
            turn=Vec(-12, 0, 0),
            bevel=0.005,
        )
        stage.shape(
            "cylinder",
            Vec(0.01, 0.01, 0.32),
            Vec(0, -0.12, 1.12),
            role="metal",
            name=f"{name}.stalk",
            parent=podium,
            turn=Vec(25, 0, 0),
        )
        stage.shape(
            "cylinder",
            Vec(0.03, 0.03, 0.06),
            Vec(0, -0.26, 1.4),
            role="metal",
            name=f"{name}.microphone",
            parent=podium,
            turn=Vec(60, 0, 0),
        )
        return podium
