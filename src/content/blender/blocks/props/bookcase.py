"""A tall bookcase, its shelves filled with books of uneven heights."""

from content.blender.api import Role, Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec
from content.blender.shapes import slab

WIDTH, DEPTH, HEIGHT, SHELVES = 1.0, 0.32, 2.0, 5
COVERS: tuple[Role, ...] = ("leather", "fabric", "card", "paper")


class Bookcase(Prop):
    name = "bookcase"
    names = ("bookshelf", "shelves", "library shelves", "book shelf")

    def build(self, stage: Stage, name: str) -> Thing:
        case = stage.group(name)
        for side in (-1, 1):
            slab(
                stage,
                case,
                f"{name}.side_{side + 1}",
                Vec(0.03, DEPTH, HEIGHT),
                Vec(side * (WIDTH / 2 - 0.015), 0, 0),
                "dark_wood",
            )
        slab(
            stage,
            case,
            f"{name}.back",
            Vec(WIDTH, 0.015, HEIGHT),
            Vec(0, DEPTH / 2 - 0.0075, 0),
            "dark_wood",
        )
        chance = stage.random(name)
        step = HEIGHT / SHELVES
        for shelf in range(SHELVES + 1):
            slab(
                stage,
                case,
                f"{name}.shelf_{shelf}",
                Vec(WIDTH - 0.06, DEPTH, 0.025),
                Vec(0, 0, shelf * step),
                "dark_wood",
            )
            if shelf == SHELVES:
                break
            x = -WIDTH / 2 + 0.05
            while x < WIDTH / 2 - 0.08:
                thick, tall = chance.uniform(0.025, 0.055), chance.uniform(0.6, 0.85) * step
                role = chance.choice(COVERS)
                stage.shape(
                    "box",
                    Vec(thick, DEPTH * 0.8, tall),
                    Vec(x + thick / 2, -0.01, shelf * step + 0.025),
                    role=role,
                    name=f"{name}.book_{shelf}_{round(x * 1000)}",
                    parent=case,
                )
                x += thick + 0.003
        return case
