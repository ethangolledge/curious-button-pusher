"""A bottle of any kind: wine, beer, spirits, water, a small medicine bottle; labelled or
plain."""

from dataclasses import dataclass
from typing import Literal

from content.blender.api import Role, Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec

# Each style: the body's height and width, the shoulder's height, the neck's length and
# width, and what it is made of.
STYLES: dict[str, tuple[float, float, float, float, float, Role]] = {
    "wine": (0.2, 0.08, 0.06, 0.08, 0.028, "glass"),
    "beer": (0.13, 0.062, 0.05, 0.06, 0.026, "glass"),
    "spirits": (0.17, 0.09, 0.03, 0.05, 0.03, "glass"),
    "water": (0.2, 0.07, 0.04, 0.03, 0.03, "plastic"),
    "medicine": (0.07, 0.045, 0.012, 0.01, 0.03, "plastic"),
}


@dataclass(frozen=True)
class Settings:
    style: Literal["wine", "beer", "spirits", "water", "medicine"] = "wine"
    label: bool = True


class Bottle(Prop):
    name = "bottle"
    names = ("wine bottle", "whisky bottle", "beer bottle", "liquor bottle", "water bottle",
             "pill bottle", "medicine bottle")  # fmt: skip
    settings = Settings
    example = Settings()

    def build(self, stage: Stage, name: str) -> Thing:
        p: Settings = self.p
        body, wide, shoulder, neck, narrow, role = STYLES[p.style]
        bottle = stage.group(name)
        stage.shape("cylinder", Vec(wide, wide, body), Vec(), role=role, name=f"{name}.body",
                    parent=bottle)  # fmt: skip
        stage.shape("cone", Vec(wide, wide, shoulder), Vec(0, 0, body), role=role,
                    name=f"{name}.shoulder", parent=bottle)  # fmt: skip
        stage.shape("cylinder", Vec(narrow, narrow, neck + shoulder * 0.6),
                    Vec(0, 0, body + shoulder * 0.4), role=role, name=f"{name}.neck",
                    parent=bottle)  # fmt: skip
        if p.label:
            stage.shape("cylinder", Vec(wide * 1.04, wide * 1.04, body * 0.4),
                        Vec(0, 0, body * 0.3), role="paper", name=f"{name}.label",
                        parent=bottle)  # fmt: skip
        return bottle
