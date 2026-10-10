"""A seated person as a simple figurine, forearms forward as if at a table: the anonymous
figures round a meeting or a desk. Stand it on a seat mark (a boardroom's `seat_…`)."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.shapes_figure import figurine


class SeatedPerson(Prop):
    name = "seated_person"
    names = ("seated figure", "person sitting", "board member", "delegate", "sitting man")
    capabilities = frozenset({"person"})

    def build(self, stage: Stage, name: str) -> Thing:
        return figurine(stage, name, "seated")
