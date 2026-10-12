# SPDX-License-Identifier: GPL-3.0-or-later
"""The picture's own look, for a picture shot (`docs/picture-shots.md`): every surface shows
its colour exactly, unlit, through the Standard view transform, so the camera where the
picture was taken sees the picture itself. Its style is the image model's, so no look of
the engine's is laid over it; the cut adds the theme's texture as for any scene."""

from dataclasses import dataclass
from typing import Annotated, Any, ClassVar

import bpy  # type: ignore[import-not-found]

from content.blender.blocks.base import Look, Range
from content.blender.blocks.looks.plain import ENGINE
from content.blender.lift import unlit
from content.blender.materials import REFERENCE, linear


@dataclass(frozen=True)
class Settings:
    sharpness: Annotated[
        float, Range(0.5, 1.5, "pixels the render's anti-aliasing blends across")
    ] = 0.8


class Painted(Look):
    name = "painted"
    settings: ClassVar[type[Any]] = Settings
    example: ClassVar[Any] = Settings()

    def __init__(self, values: Any, palette: Any) -> None:
        super().__init__(values, palette)
        self._made: dict[str, Any] = {}

    def material(self, role: str) -> Any:
        """Anything added to a picture shot is drawn flat in its role's everyday colour."""
        if role not in self._made:
            material = bpy.data.materials.new(role)  # named after its role: checks read it
            material.use_nodes = True
            nodes = material.node_tree.nodes
            nodes.clear()
            glow = nodes.new("ShaderNodeEmission")
            glow.inputs["Color"].default_value = (*linear(REFERENCE[role]), 1.0)
            out = nodes.new("ShaderNodeOutputMaterial")
            material.node_tree.links.new(glow.outputs["Emission"], out.inputs["Surface"])
            self._made[role] = material
        return self._made[role]

    def picture(self, path: str) -> Any:
        if path not in self._made:
            self._made[path] = unlit(bpy.data.images.load(path))
        return self._made[path]

    def world(self, scene: Any) -> None:
        world = bpy.data.worlds.new("world")
        world.use_nodes = True
        world.node_tree.nodes["Background"].inputs["Color"].default_value = (0, 0, 0, 1)
        scene.world = world

    def render(self, scene: Any, quality: str) -> None:
        scene.render.engine = ENGINE
        scene.eevee.taa_render_samples = {"still": 16, "draft": 8, "final": 32}[quality]
        scene.eevee.use_raytracing = False
        scene.render.filter_size = self.values.sharpness
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "None"
        scene.view_settings.exposure = 0.0
        scene.view_settings.gamma = 1.0
