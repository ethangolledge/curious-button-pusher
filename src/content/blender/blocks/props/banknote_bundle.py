"""A bundle of banknotes held by a paper band."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec


class BanknoteBundle(Prop):
    name = "banknote_bundle"
    names = ("bundle of cash", "wad of notes", "stack of money", "money bundle", "cash bundle")

    def build(self, stage: Stage, name: str) -> Thing:
        bundle = stage.group(name)
        stage.shape(
            "box",
            Vec(0.156, 0.066, 0.012),
            Vec(),
            role="money",
            name=f"{name}.notes",
            parent=bundle,
            bevel=0.0008,
        )
        stage.shape(
            "box", Vec(0.03, 0.068, 0.0125), Vec(), role="card", name=f"{name}.band", parent=bundle
        )
        return bundle
