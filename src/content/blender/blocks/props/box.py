"""A box of any kind: a cardboard carton or archive box, a wooden box, a metal strongbox;
lidded or open; of any size."""

from dataclasses import dataclass
from typing import Annotated, Literal

from content.blender.api import Role, Stage, Thing
from content.blender.blocks.base import Prop, Range
from content.blender.maths import Vec


@dataclass(frozen=True)
class Settings:
    width: Annotated[float, Range(0.05, 3, "metres wide")] = 0.42
    depth: Annotated[float, Range(0.05, 3, "metres deep")] = 0.32
    height: Annotated[float, Range(0.02, 3, "metres tall")] = 0.28
    material: Literal["card", "wood", "metal", "plastic"] = "card"
    lid: bool = True


class Box(Prop):
    name = "box"
    names = ("cardboard box", "archive box", "evidence box", "carton", "packing box",
             "ballot box", "strongbox", "chest")  # fmt: skip
    capabilities = frozenset({"surface"})
    settings = Settings
    example = Settings()

    def build(self, stage: Stage, name: str) -> Thing:
        p: Settings = self.p
        role: Role = p.material
        box = stage.group(name)
        rim = 0.03 if p.lid else 0.0
        stage.shape("box", Vec(p.width, p.depth, p.height - rim), Vec(), role=role,
                    name=f"{name}.body", parent=box, bevel=0.003)  # fmt: skip
        if p.lid:
            stage.shape("box", Vec(p.width + 0.006, p.depth + 0.006, rim),
                        Vec(0, 0, p.height - rim), role=role, name=f"{name}.lid",
                        parent=box, bevel=0.002)  # fmt: skip
        return box
