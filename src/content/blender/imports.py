# SPDX-License-Identifier: GPL-3.0-or-later
"""Reading a model file into the scene, the same way when a model joins the library
(`ingest.py`) and when a shot uses it (`stage.py`)."""

from pathlib import Path
from typing import Any

import bpy  # type: ignore[import-not-found]
import numpy as np

from content.blender.materials import decoded

# Each kind of file, read with the axis its maker took as up ("Y" or "Z"); glTF always says.
IMPORTERS = {
    ".glb": lambda path, up: bpy.ops.import_scene.gltf(filepath=path),
    ".gltf": lambda path, up: bpy.ops.import_scene.gltf(filepath=path),
    ".obj": lambda path, up: bpy.ops.wm.obj_import(
        filepath=path, up_axis=up, forward_axis="NEGATIVE_Z" if up == "Y" else "Y"
    ),
    ".fbx": lambda path, up: bpy.ops.import_scene.fbx(filepath=path),
    ".stl": lambda path, up: bpy.ops.wm.stl_import(
        filepath=path, up_axis=up, forward_axis="NEGATIVE_Z" if up == "Y" else "Y"
    ),
}


def import_model(path: str, up: str = "Y") -> list[Any]:
    """The objects a file brings in, `up` the axis its maker took as up. The shapes a
    skeleton's bones are drawn with in the viewport (glTF makes an icosphere for them) are
    solids no shot should hold: they go."""
    before = set(bpy.data.objects)
    IMPORTERS[Path(path).suffix.lower()](path, up)
    shapes = {
        bone.custom_shape
        for rig in bpy.data.objects
        if rig not in before and rig.type == "ARMATURE"
        for bone in rig.pose.bones
        if bone.custom_shape is not None
    }
    for shape in shapes:
        bpy.data.objects.remove(shape, do_unlink=True)
    return [obj for obj in bpy.data.objects if obj not in before]


def skinned(obj: Any) -> bool:
    """A mesh a skeleton bends (a character): it keeps its own transforms, and moves."""
    return any(modifier.type == "ARMATURE" for modifier in obj.modifiers)


def surface(material: Any) -> tuple[tuple[float, float, float], float, float]:
    """A material's own colour in linear light (its base colour, or the average of the
    picture painted on it), how metallic it is, and how much light passes through it."""
    shader = next(
        (node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None
    ) if material is not None and material.node_tree else None  # fmt: skip
    if shader is None:
        return (0.5, 0.5, 0.5), 0.0, 0.0
    base = shader.inputs["Base Color"]
    r, g, b, _ = base.default_value
    colour = (r, g, b)
    for link in base.links:
        image = getattr(link.from_node, "image", None)
        if image is not None and image.size[0] > 0:
            colour = _average(image)
    metallic = shader.inputs["Metallic"].default_value
    transmission = shader.inputs["Transmission Weight"].default_value
    return colour, float(metallic), float(transmission)


def _average(image: Any) -> tuple[float, float, float]:
    """An image's average colour, from a small copy of it."""
    small = image.copy()
    small.scale(16, 16)
    pixels = np.empty(16 * 16 * small.channels, dtype=np.float32)
    small.pixels.foreach_get(pixels)
    channels = small.channels
    bpy.data.images.remove(small)
    r, g, b = (float(c) for c in pixels.reshape(-1, channels)[:, :3].mean(axis=0))
    if image.colorspace_settings.name == "sRGB":
        return decoded((r, g, b))
    return r, g, b
