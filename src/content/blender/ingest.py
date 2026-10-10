# SPDX-License-Identifier: GPL-3.0-or-later
"""Runs inside Blender: brings a downloaded model into the library's form.

    blender -b --factory-startup --python-exit-code 1 \\
        -P src/content/blender/ingest.py -- model.glb out.glb facts.json <height> <faces> <turn>

Every library model is the same shape of thing, so no block has to allow for its quirks: one
object hierarchy, transforms applied, standing on the origin and centred over it, in metres
(scaled to `height` if given, or from millimetres or centimetres when its size says so), at
most `max_faces` faces, saved as a binary glTF. Writes its
size and face count to `facts.json`."""

import json
import math
import re
import sys
from pathlib import Path
from typing import Any

import bpy  # type: ignore[import-not-found]
from mathutils import Matrix, Vector  # type: ignore[import-not-found]

IMPORTERS = {
    ".glb": lambda path: bpy.ops.import_scene.gltf(filepath=path),
    ".gltf": lambda path: bpy.ops.import_scene.gltf(filepath=path),
    ".obj": lambda path: bpy.ops.wm.obj_import(filepath=path),
    ".fbx": lambda path: bpy.ops.import_scene.fbx(filepath=path),
    ".stl": lambda path: bpy.ops.wm.stl_import(filepath=path),
}


def main(
    source: Path, target: Path, facts: Path, height: float, max_faces: int, turn: float = 0.0
) -> int:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    IMPORTERS[source.suffix.lower()](str(source))
    # Turned so its front faces −Y, as every model's does.
    for obj in bpy.context.scene.objects:
        if obj.parent is None and turn:
            obj.rotation_mode = "XYZ"
            obj.rotation_euler.z += math.radians(turn)
            obj.location = Matrix.Rotation(math.radians(turn), 4, "Z") @ obj.location
    # Shapes a skeleton draws its bones with are never seen in a render: they go.
    shapes = {
        bone.custom_shape
        for rig in bpy.context.scene.objects
        if rig.type == "ARMATURE"
        for bone in rig.pose.bones
        if bone.custom_shape is not None
    }
    for shape in shapes:
        bpy.data.objects.remove(shape, do_unlink=True)
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise SystemExit(f"{source} has no meshes")
    # Meshes take their rotation and scale into their shape; empties keep theirs, because a
    # set's marks face the way their empties do, and so do skinned meshes, which follow their
    # skeleton (a character).
    rigid = [obj for obj in meshes if not _skinned(obj)]
    with bpy.context.temp_override(selected_editable_objects=rigid):
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
            # Simplified now, so the skeleton's own modifier is never baked into the shape.
            with bpy.context.temp_override(object=obj, active_object=obj):
                bpy.ops.object.modifier_move_to_index(modifier="simplify", index=0)
                bpy.ops.object.modifier_apply(modifier="simplify")
    # Animations go with it: a character's motions are played by name.
    bpy.ops.export_scene.gltf(filepath=str(target), export_format="GLB", export_animations=True)
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
                "parts": _parts(),
                "motions": sorted(action.name for action in bpy.data.actions),
            }
        )  # fmt: skip
    )
    return 0


PART_PREFIXES = ("mark_", "surface_", "path_", "actor_", "interior")


def _parts() -> list[dict[str, Any]]:
    """A set's named parts (`blocks/layouts/set.py`): where each is, which way it faces, and
    its size, so a shot using the set can be checked without Blender."""
    found = []
    for obj in bpy.context.scene.objects:
        name = re.sub(r"\.\d+$", "", obj.name)
        if not name.startswith(PART_PREFIXES):
            continue
        location, rotation, _ = obj.matrix_world.decompose()
        facing = rotation @ Vector((0.0, -1.0, 0.0))
        low, high = _extent([obj]) if obj.type == "MESH" else (location, location)
        found.append(
            {
                "name": name,
                "at": [
                    round(v, 3) for v in (location if obj.type != "MESH" else ((low + high) / 2))
                ],
                "facing": [round(v, 3) for v in facing],
                "size": [round(v, 3) for v in (high - low)],
            }
        )
    return found


def _skinned(obj: Any) -> bool:
    return any(modifier.type == "ARMATURE" for modifier in obj.modifiers)


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
    source, target, facts, height, max_faces, turn = arguments
    sys.exit(
        main(Path(source), Path(target), Path(facts), float(height), int(max_faces), float(turn))
    )
