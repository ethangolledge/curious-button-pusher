# SPDX-License-Identifier: GPL-3.0-or-later
"""A clean, neutral look: soft physically based materials in quiet colours, gentle daylight
ambience, and a filmic tone curve. The engine's default, and the base to compare a channel's
own look against."""

from dataclasses import dataclass
from typing import Annotated, Any, ClassVar

import bpy  # type: ignore[import-not-found]

from content.blender.blocks.base import About, Look, Range
from content.blender.stage import linear

# Each role: its colour, how rough it is, how metallic, and how brightly it glows.
ROLES: dict[str, tuple[str, float, float, float]] = {
    "wall": ("#b9b2a6", 0.9, 0.0, 0.0),
    "floor": ("#6b5a48", 0.7, 0.0, 0.0),
    "ceiling": ("#d6d1c8", 0.95, 0.0, 0.0),
    "ground": ("#5d6150", 0.95, 0.0, 0.0),
    "road": ("#3b3c3e", 0.9, 0.0, 0.0),
    "wood": ("#8a6440", 0.55, 0.0, 0.0),
    "dark_wood": ("#4a3121", 0.5, 0.0, 0.0),
    "metal": ("#9a9c9f", 0.35, 1.0, 0.0),
    "glass": ("#c9d7dc", 0.05, 0.0, 0.0),
    "paper": ("#e8e2d3", 0.85, 0.0, 0.0),
    "card": ("#c7b796", 0.8, 0.0, 0.0),
    "fabric": ("#5b5f6b", 0.95, 0.0, 0.0),
    "leather": ("#5a3624", 0.45, 0.0, 0.0),
    "plastic": ("#2f3134", 0.4, 0.0, 0.0),
    "stone": ("#8d8a83", 0.85, 0.0, 0.0),
    "brick": ("#7d4a3a", 0.9, 0.0, 0.0),
    "concrete": ("#8f8d88", 0.9, 0.0, 0.0),
    "money": ("#a9b49a", 0.8, 0.0, 0.0),
    "foliage": ("#3f5a35", 0.8, 0.0, 0.0),
    "rubber": ("#1c1c1d", 0.8, 0.0, 0.0),
    "screen": ("#9fc4d9", 0.2, 0.0, 1.5),
    "lamp_shade": ("#d9c7a0", 0.8, 0.0, 0.0),
    "bulb": ("#fff2d6", 0.3, 0.0, 12.0),
    "paint": ("#7a7f86", 0.6, 0.0, 0.0),
    "skin": ("#c79a7e", 0.6, 0.0, 0.0),
    "hair": ("#2b2018", 0.7, 0.0, 0.0),
}
ENGINE = "BLENDER_EEVEE"


@dataclass(frozen=True)
class Settings:
    exposure: Annotated[float, Range(-4, 4, "stops brighter or darker")] = 0.0
    sky: Annotated[str, About("the world's colour, hex")] = "#3a4452"
    ambience: Annotated[float, Range(0, 3, "how much the world lights the scene")] = 0.6


class Plain(Look):
    """Its parts are small methods, so a channel's look can subclass it and change only what
    differs: the colours, the world, the tone."""

    name = "plain"
    # Typed loosely so a look built on this one can bring its own settings.
    settings: ClassVar[type[Any]] = Settings
    example: ClassVar[Any] = Settings()

    def __init__(self, values: Any, palette: Any) -> None:
        super().__init__(values, palette)
        self._made: dict[str, Any] = {}

    def colour(self, role: str) -> tuple[float, float, float]:
        """A role's colour, in linear light."""
        return linear(ROLES[role][0])

    def sky(self) -> tuple[tuple[float, float, float], float]:
        """The world's colour, and how strongly it lights the scene."""
        return linear(self.values.sky), self.values.ambience

    def tone(self) -> tuple[str, float]:
        """The tone curve's look ("None" or an AgX look) and the exposure in stops."""
        return "None", self.values.exposure

    def material(self, role: str) -> Any:
        if role not in self._made:
            _, roughness, metallic, glow = ROLES[role]
            material = bpy.data.materials.new(role)  # named after its role: checks read it
            shader = material.node_tree.nodes["Principled BSDF"]
            shader.inputs["Base Color"].default_value = (*self.colour(role), 1.0)
            shader.inputs["Roughness"].default_value = roughness
            shader.inputs["Metallic"].default_value = metallic
            if glow:
                shader.inputs["Emission Color"].default_value = (*self.colour(role), 1.0)
                shader.inputs["Emission Strength"].default_value = glow
            if role == "glass":
                shader.inputs["Transmission Weight"].default_value = 0.9
            self._made[role] = material
        return self._made[role]

    def restyle(self, obj: Any) -> None:
        if obj.type == "MESH" and not obj.data.materials:
            obj.data.materials.append(self.material("paint"))

    def world(self, scene: Any) -> None:
        colour, strength = self.sky()
        world = bpy.data.worlds.new("world")
        background = world.node_tree.nodes["Background"]
        background.inputs["Color"].default_value = (*colour, 1.0)
        background.inputs["Strength"].default_value = strength
        scene.world = world

    def render(self, scene: Any, quality: str) -> None:
        look, exposure = self.tone()
        scene.render.engine = ENGINE
        scene.eevee.taa_render_samples = {"still": 32, "draft": 12, "final": 64}[quality]
        scene.eevee.use_raytracing = quality != "draft"
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = look
        scene.view_settings.exposure = exposure
