"""A single printed sheet of paper (A4), lying flat."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec


class Document(Prop):
    name = "document"
    names = ("paper", "sheet of paper", "page", "letter", "report", "memo", "contract")

    def build(self, stage: Stage, name: str) -> Thing:
        return stage.shape("box", Vec(0.21, 0.297, 0.0006), Vec(), role="paper", name=name)
