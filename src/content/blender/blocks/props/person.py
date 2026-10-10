"""A standing person as a simple figurine: the anonymous figures of a story (officials,
guards, a crowd), or anyone whose face is not shown."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.shapes_figure import figurine


class Person(Prop):
    name = "person"
    names = ("figure", "man", "woman", "official", "silhouette", "standing figure", "guard")
    capabilities = frozenset({"person"})

    def build(self, stage: Stage, name: str) -> Thing:
        return figurine(stage, name, "standing")
