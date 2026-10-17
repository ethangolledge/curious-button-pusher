# SPDX-License-Identifier: GPL-3.0-or-later
"""A shot as a guide for the image model, never shown to a viewer
([docs/3d-reuse.md](../../../../../docs/3d-reuse.md)): every solid in plain clay, a shade of
grey per kind of surface so neighbours stay apart, outlined in ink, lit softly enough that
nothing is lost in shadow, its lamps and screens glowing as they do in the shot. It says where
everything is, how big, how it turns and where the light comes from; the image model repaints
it in the channel's look, from the channel's designs."""

from dataclasses import dataclass
from typing import Annotated, Any, ClassVar

from content.blender.blocks.base import About, Range
from content.blender.blocks.looks.plain import Plain
from content.blender.materials import linear

# What gives light, and glows in the guide as it does in the shot.
GLOWING = frozenset({"bulb", "screen"})
# How light each kind of surface is drawn, 0 to 1: the room recedes, the things in it stand
# out, people stand out most.
LIGHTNESS: dict[str, float] = {
    "wall": 0.55, "floor": 0.4, "ceiling": 0.6, "ground": 0.4, "road": 0.3, "wood": 0.65,
    "dark_wood": 0.5, "metal": 0.75, "glass": 0.85, "paper": 0.95, "card": 0.85,
    "fabric": 0.6, "leather": 0.5, "plastic": 0.7, "stone": 0.6, "brick": 0.5,
    "concrete": 0.55, "money": 0.9, "foliage": 0.45, "rubber": 0.3, "screen": 0.95,
    "lamp_shade": 0.85, "bulb": 1.0, "paint": 0.6, "skin": 0.9, "hair": 0.35,
}  # fmt: skip


@dataclass(frozen=True)
class Settings:
    exposure: Annotated[float, Range(-4, 4, "stops brighter or darker")] = 0.0
    sky: Annotated[str, About("the world's colour, hex")] = "#808080"
    ambience: Annotated[float, Range(0, 3, "how much the world lights the scene")] = 1.0
    ink: Annotated[float, Range(0, 0.03, "the outline's width, metres")] = 0.008


class Guide(Plain):
    name = "guide"
    settings: ClassVar[type[Any]] = Settings
    example: ClassVar[Any] = Settings()

    def colour(self, role: str) -> tuple[float, float, float]:
        grey = f"{round(LIGHTNESS[role] * 255):02x}"
        return linear(f"#{grey}{grey}{grey}")

    def material(self, role: str) -> Any:
        """Clay: no shine, no metal, so light reads only as shape. What gives light (a lamp's
        bulb, a screen) still glows: the layout says it is on, and is drawn on."""
        if role not in self._made:
            material = super().material(role)
            shader = material.node_tree.nodes["Principled BSDF"]
            shader.inputs["Roughness"].default_value = 1.0
            shader.inputs["Metallic"].default_value = 0.0
            if role not in GLOWING:
                shader.inputs["Emission Strength"].default_value = 0.0
            shader.inputs["Transmission Weight"].default_value = 0.0
        return self._made[role]
