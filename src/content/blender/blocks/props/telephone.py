"""An old desk telephone with a handset on its cradle."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec


class Telephone(Prop):
    name = "telephone"
    names = ("phone", "desk phone", "rotary phone", "landline", "receiver")

    def build(self, stage: Stage, name: str) -> Thing:
        phone = stage.group(name)
        stage.shape(
            "box",
            Vec(0.2, 0.22, 0.08),
            Vec(),
            role="plastic",
            name=f"{name}.base",
            parent=phone,
            bevel=0.02,
        )
        stage.shape(
            "cylinder",
            Vec(0.11, 0.11, 0.012),
            Vec(0, -0.04, 0.075),
            role="metal",
            name=f"{name}.dial",
            parent=phone,
            turn=Vec(-20, 0, 0),
        )
        handset = stage.group(f"{name}.handset", Vec(0, 0.05, 0.095), parent=phone)
        stage.shape(
            "box",
            Vec(0.22, 0.045, 0.03),
            Vec(),
            role="plastic",
            name=f"{name}.grip",
            parent=handset,
            bevel=0.012,
        )
        for side in (-1, 1):
            stage.shape(
                "cylinder",
                Vec(0.06, 0.06, 0.04),
                Vec(side * 0.1, 0, -0.005),
                role="plastic",
                name=f"{name}.cup_{side + 1}",
                parent=handset,
            )
        return phone
