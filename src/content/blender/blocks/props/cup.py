"""A cup of any kind: a mug, a teacup on its saucer, an espresso cup, a beaker. One shape,
its proportions and parts set by its style."""

from dataclasses import dataclass
from typing import Annotated, Literal

from content.blender.api import Role, Stage, Thing
from content.blender.blocks.base import Prop, Range
from content.blender.maths import Vec

# Each style: height and width (metres), whether it widens to its rim, and has a handle and
# a saucer.
STYLES = {
    "mug": (0.1, 0.085, False, True, False),
    "teacup": (0.065, 0.09, True, True, True),
    "espresso": (0.06, 0.06, False, True, True),
    "beaker": (0.11, 0.08, True, False, False),
}


@dataclass(frozen=True)
class Settings:
    style: Literal["mug", "teacup", "espresso", "beaker"] = "mug"
    height: Annotated[float, Range(0, 0.4, "metres tall; 0 for the style's own")] = 0.0
    material: Literal["paint", "paper", "metal", "glass"] = "paint"


class Cup(Prop):
    name = "cup"
    names = ("mug", "coffee cup", "tea cup", "teacup", "coffee mug", "espresso cup", "beaker")
    settings = Settings
    example = Settings()

    def build(self, stage: Stage, name: str) -> Thing:
        p: Settings = self.p
        tall, wide, flared, handle, saucer = STYLES[p.style]
        tall = p.height or tall
        role: Role = p.material
        cup = stage.group(name)
        lift = 0.012 if saucer else 0.0
        if saucer:
            stage.shape("cylinder", Vec(wide * 1.7, wide * 1.7, lift), Vec(), role=role,
                        name=f"{name}.saucer", parent=cup, bevel=0.003)  # fmt: skip
        if flared:
            # An open cone turned over, wide at the rim, on a small foot.
            stage.shape("funnel", Vec(wide, wide, tall), Vec(0, 0, lift + tall), role=role,
                        name=f"{name}.bowl", parent=cup, turn=Vec(180, 0, 0))  # fmt: skip
            stage.shape("cylinder", Vec(wide * 0.45, wide * 0.45, 0.008), Vec(0, 0, lift),
                        role=role, name=f"{name}.foot", parent=cup)  # fmt: skip
        else:
            stage.shape("cylinder", Vec(wide, wide, tall), Vec(0, 0, lift), role=role,
                        name=f"{name}.body", parent=cup)  # fmt: skip
        if handle:
            stage.shape("box", Vec(0.012, wide * 0.4, tall * 0.55),
                        Vec(wide / 2 + 0.008, 0, lift + tall * 0.2), role=role,
                        name=f"{name}.handle", parent=cup, bevel=0.005)  # fmt: skip
        return cup
