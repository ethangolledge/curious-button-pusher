"""A plain city building of a few storeys, its windows in rows (some lit at night)."""

from content.blender.api import Role, Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec

WIDTH, DEPTH, STOREY, STOREYS = 12.0, 10.0, 3.2, 5


class Building(Prop):
    name = "building"
    names = ("block of flats", "office block", "tower block", "apartment building", "house")

    def build(self, stage: Stage, name: str) -> Thing:
        building = stage.group(name)
        stage.shape(
            "box",
            Vec(WIDTH, DEPTH, STOREY * STOREYS),
            Vec(),
            role="brick",
            name=f"{name}.walls",
            parent=building,
        )
        stage.shape(
            "box",
            Vec(WIDTH + 0.4, DEPTH + 0.4, 0.4),
            Vec(0, 0, STOREY * STOREYS),
            role="concrete",
            name=f"{name}.roof",
            parent=building,
        )
        chance = stage.random(name)
        columns = int(WIDTH / 2.4)
        for storey in range(STOREYS):
            for column in range(columns):
                x = (column - (columns - 1) / 2) * 2.4
                role: Role = "bulb" if chance.random() < 0.18 else "glass"
                stage.shape(
                    "box",
                    Vec(1.2, 0.06, 1.5),
                    Vec(x, -DEPTH / 2 - 0.02, storey * STOREY + 0.9),
                    role=role,
                    name=f"{name}.window_{storey}_{column}",
                    parent=building,
                )
        return building
