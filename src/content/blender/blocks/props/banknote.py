"""A single banknote, lying flat."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec


class Banknote(Prop):
    name = "banknote"
    names = ("bill", "note", "cash", "money", "dollar bill", "currency")

    def build(self, stage: Stage, name: str) -> Thing:
        return stage.shape("box", Vec(0.156, 0.066, 0.0004), Vec(), role="money", name=name)
