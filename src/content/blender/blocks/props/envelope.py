"""A sealed envelope, lying flat."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec


class Envelope(Prop):
    name = "envelope"
    names = ("letter", "sealed envelope", "mail", "post")

    def build(self, stage: Stage, name: str) -> Thing:
        envelope = stage.group(name)
        stage.shape(
            "box", Vec(0.22, 0.11, 0.004), Vec(), role="paper", name=f"{name}.body", parent=envelope
        )
        stage.shape(
            "cylinder",
            Vec(0.02, 0.02, 0.002),
            Vec(0, 0.03, 0.004),
            role="leather",
            name=f"{name}.seal",
            parent=envelope,
        )
        return envelope
