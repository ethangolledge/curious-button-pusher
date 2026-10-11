"""A pendant lamp hanging from the ceiling on a cord. Its light is placed at the part named
`bulb`; stand it on a ceiling mark."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec

DROP = 0.8


class CeilingLamp(Prop):
    name = "ceiling_lamp"
    names = ("pendant lamp", "hanging lamp", "light fitting", "bare bulb")
    capabilities = frozenset({"light", "hanging"})

    def build(self, stage: Stage, name: str) -> Thing:
        lamp = stage.group(name)
        # Built hanging down from its origin, which goes on the ceiling.
        stage.shape(
            "cylinder",
            Vec(0.008, 0.008, DROP),
            Vec(0, 0, -DROP),
            role="rubber",
            name=f"{name}.cord",
            parent=lamp,
        )
        stage.shape(
            "funnel",
            Vec(0.4, 0.4, 0.2),
            Vec(0, 0, -DROP - 0.18),
            role="metal",
            name=f"{name}.shade",
            parent=lamp,
        )
        stage.shape(
            "sphere",
            Vec(0.08, 0.08, 0.08),
            Vec(0, 0, -DROP - 0.16),
            role="bulb",
            name=f"{name}.bulb",
            parent=lamp,
        )
        return lamp
