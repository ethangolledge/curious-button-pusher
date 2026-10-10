"""A leafy plant in a pot."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec


class PottedPlant(Prop):
    name = "potted_plant"
    names = ("plant", "house plant", "pot plant", "fern")

    def build(self, stage: Stage, name: str) -> Thing:
        plant = stage.group(name)
        stage.shape(
            "funnel",
            Vec(0.32, 0.32, 0.34),
            Vec(0, 0, 0),
            role="paint",
            name=f"{name}.pot",
            parent=plant,
            turn=Vec(180, 0, 0),
        )
        chance = stage.random(name)
        for index in range(6):
            offset = Vec(
                chance.uniform(-0.12, 0.12), chance.uniform(-0.12, 0.12), chance.uniform(0.35, 0.65)
            )
            stage.shape(
                "sphere",
                Vec(0.28, 0.28, 0.24),
                offset,
                role="foliage",
                name=f"{name}.leaves_{index}",
                parent=plant,
            )
        return plant
