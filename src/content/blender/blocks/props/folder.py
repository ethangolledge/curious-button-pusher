"""A closed card folder with papers inside, lying flat: a dossier, a case file."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec


class Folder(Prop):
    name = "folder"
    names = ("file", "dossier", "case file", "manila folder")

    def build(self, stage: Stage, name: str) -> Thing:
        folder = stage.group(name)
        stage.shape(
            "box", Vec(0.24, 0.32, 0.012), Vec(), role="card", name=f"{name}.cover", parent=folder
        )
        stage.shape(
            "box",
            Vec(0.21, 0.297, 0.008),
            Vec(0.01, 0.005, 0.002),
            role="paper",
            name=f"{name}.papers",
            parent=folder,
        )
        return folder
