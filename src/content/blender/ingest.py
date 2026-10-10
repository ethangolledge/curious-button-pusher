# SPDX-License-Identifier: GPL-3.0-or-later
"""Runs inside Blender: brings a downloaded model into the library's form.

    blender -b --factory-startup --python-exit-code 1 \\
        -P src/content/blender/ingest.py -- model.glb out.glb facts.json <height> <max_faces>

Every library model is the same shape of thing, so no block has to allow for its quirks: one
object hierarchy, transforms applied, standing on the origin and centred over it, in metres
(scaled to `height` if given, or from millimetres or centimetres when its size says so), at
most `max_faces` faces, saved as a binary glTF. Writes its
size and face count to `facts.json`."""

import json
import sys
from pathlib import Path

import bpy  # type: ignore[import-not-found]
from mathutils import Vector  # type: ignore[import-not-found]

IMPORTERS = {
    ".glb": lambda path: bpy.ops.import_scene.gltf(filepath=path),
    ".gltf": lambda path: bpy.ops.import_scene.gltf(filepath=path),
    ".obj": lambda path: bpy.ops.wm.obj_import(filepath=path),
    ".fbx": lambda path: bpy.ops.import_scene.fbx(filepath=path),
    ".stl": lambda path: bpy.ops.wm.stl_import(filepath=path),
}


def main(source: Path, target: Path, facts: Path, height: float, max_faces: int) -> int:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    IMPORTERS[source.suffix.lower()](str(source))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise SystemExit(f"{source} has no meshes")
    with bpy.context.temp_override(selected_editable_objects=list(bpy.context.scene.objects)):
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    low, high = _extent(meshes)
    size = high - low
    scale = height / size.z if height and size.z > 0 else _units(size.z)
    offset = Vector(((low.x + high.x) / 2, (low.y + high.y) / 2, low.z))
    for obj in bpy.context.scene.objects:
        if obj.parent is None:
            obj.location = (obj.location - offset) * scale
            obj.scale = obj.scale * scale
    faces = sum(len(obj.data.polygons) for obj in meshes)
    if faces > max_faces:
        for obj in meshes:
            modifier = obj.modifiers.new("simplify", "DECIMATE")
            modifier.ratio = max_faces / faces
    bpy.ops.export_scene.gltf(filepath=str(target), export_format="GLB", export_apply=True)
    bpy.context.view_layer.update()
    low, high = _extent(meshes)
    size = high - low
    facts.write_text(
        json.dumps(
            {
                "width": round(size.x, 3),
                "depth": round(size.y, 3),
                "height": round(size.z, 3),
                "faces": min(faces, max_faces),
            }
        )  # fmt: skip
    )
    return 0


def _units(tallest: float) -> float:
    """Many files are in millimetres or centimetres; nothing in a shot is taller than about
    fifty metres, so a taller model is read in the unit that makes it a plausible size."""
    if tallest <= 50:
        return 1.0
    return 0.001 if tallest / 1000 >= 0.02 else 0.01


def _extent(meshes: list[object]) -> tuple[Vector, Vector]:
    bpy.context.view_layer.update()
    corners = [obj.matrix_world @ Vector(c) for obj in meshes for c in obj.bound_box]  # type: ignore[attr-defined]
    low = Vector([min(c[i] for c in corners) for i in range(3)])
    high = Vector([max(c[i] for c in corners) for i in range(3)])
    return low, high


if __name__ == "__main__":
    arguments = sys.argv[sys.argv.index("--") + 1 :]
    source, target, facts, height, max_faces = arguments
    sys.exit(main(Path(source), Path(target), Path(facts), float(height), int(max_faces)))
