"""A closed hardback book, lying flat."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec


class Book(Prop):
    name = "book"
    names = ("hardback", "ledger", "volume", "diary", "notebook")

    def build(self, stage: Stage, name: str) -> Thing:
        book = stage.group(name)
        stage.shape(
            "box",
            Vec(0.16, 0.24, 0.035),
            Vec(),
            role="leather",
            name=f"{name}.cover",
            parent=book,
            bevel=0.003,
        )
        stage.shape(
            "box",
            Vec(0.152, 0.232, 0.031),
            Vec(0.006, 0, 0.002),
            role="paper",
            name=f"{name}.pages",
            parent=book,
        )
        return book
