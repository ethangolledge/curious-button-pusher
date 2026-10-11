# SPDX-License-Identifier: GPL-3.0-or-later
"""Runs inside Blender: makes a person to a description, as a library model.

    PYTHONPATH=src blender -b --factory-startup --python-use-system-env \\
        --python-exit-code 1 -P src/content/blender/person.py -- person.json out.glb facts.json

One parametric body (MakeHuman, through the MPFB extension; its assets are CC0) shaped by
sex, age and build, made the height asked, dressed (suit, casual, work), with hair, then
posed by code (standing, seated at a table, mid-stride) so the pose fits any body: each
bone is turned to point the way the pose asks, from the hips out. The pose is baked into
plain meshes, each surface named for its role (skin, hair, fabric, leather), so every look
draws it its own way. Writes its size to `facts.json`."""

import json
import math
import sys
from pathlib import Path
from typing import Any

import addon_utils  # type: ignore[import-not-found]
import bpy  # type: ignore[import-not-found]
from mathutils import Matrix, Quaternion, Vector  # type: ignore[import-not-found]

EXTENSION = "bl_ext.user_default.mpfb"
AXES = {"x": (1.0, 0.0, 0.0), "z": (0.0, 0.0, 1.0)}
# The MakeHuman sliders (0 to 1) each word sets.
SEX = {"man": 1.0, "woman": 0.0}
AGE = {"young": 0.4, "middle": 0.6, "old": 0.88}
BUILD = {"slim": (0.3, 0.4), "average": (0.5, 0.5), "heavy": (0.85, 0.45)}  # weight, muscle
# What each person wears, by dress and sex; then shoes and hair (by sex, and for the old).
DRESS = {
    ("suit", "man"): "toigo_male_suit_3", ("suit", "woman"): "toigo_female_suit",
    ("casual", "man"): "male_casualsuit02", ("casual", "woman"): "female_casualsuit01",
    ("work", "man"): "male_worksuit01", ("work", "woman"): "female_casualsuit02",
    ("uniform", "man"): "male_worksuit01", ("uniform", "woman"): "female_sportsuit01",
}  # fmt: skip
SHOES = {"man": "shoes01", "woman": "shoes03"}
HAIR = {("man", False): "short02", ("man", True): "short04", ("woman", False): "bob02",
        ("woman", True): "short03"}  # fmt: skip
# Where each limb points in each pose (x right, y back, z up), from the hips out; each pair
# is the left side's, mirrored for the right.
POSES: dict[str, dict[str, tuple[float, float, float]]] = {
    "standing": {
        "upperarm01": (0.18, 0.0, -1.0), "upperarm02": (0.12, 0.02, -1.0),
        "lowerarm01": (0.05, -0.12, -1.0), "lowerarm02": (0.04, -0.15, -1.0),
    },
    "seated": {
        "upperleg01": (0.08, -1.0, -0.1), "upperleg02": (0.06, -1.0, 0.0),
        "lowerleg01": (0.0, -0.08, -1.0), "lowerleg02": (0.0, -0.05, -1.0),
        "upperarm01": (0.15, -0.35, -1.0), "upperarm02": (0.1, -0.4, -1.0),
        "lowerarm01": (-0.15, -1.0, -0.05), "lowerarm02": (-0.15, -1.0, -0.05),
    },
    "walking": {
        "upperleg01": (0.05, -0.35, -1.0), "upperleg02": (0.04, -0.35, -1.0),
        "lowerleg01": (0.0, 0.05, -1.0), "lowerleg02": (0.0, 0.05, -1.0),
        "upperarm01": (0.15, 0.3, -1.0), "upperarm02": (0.1, 0.3, -1.0),
        "lowerarm01": (0.05, 0.05, -1.0), "lowerarm02": (0.05, 0.0, -1.0),
    },
}  # fmt: skip
# Mid-stride the right side does the opposite.
OPPOSED = {"walking"}
# How each motion moves a body, over one loop of so many frames: each bone turned to and fro
# about an axis of the world (x: nodding forward, z: turning), by up to so many degrees,
# so many times a loop, starting so far round (a fraction of a turn).
MOTIONS: dict[str, tuple[int, dict[str, tuple[str, float, int, float]]]] = {
    "breathing": (120, {
        "spine02": ("x", 1.5, 1, 0.0), "head": ("z", 4.0, 1, 0.25),
        "upperarm01.L": ("x", 1.5, 1, 0.1), "upperarm01.R": ("x", 1.5, 1, 0.6),
    }),
    "talking": (60, {
        "head": ("x", 5.0, 2, 0.0), "spine02": ("z", 2.0, 1, 0.0),
        "lowerarm01.L": ("x", 12.0, 2, 0.0), "lowerarm01.R": ("x", 10.0, 1, 0.5),
    }),
    "walking": (32, {
        "upperleg01.L": ("x", 24.0, 1, 0.0), "upperleg01.R": ("x", 24.0, 1, 0.5),
        "lowerleg01.L": ("x", 18.0, 1, 0.75), "lowerleg01.R": ("x", 18.0, 1, 0.25),
        "upperarm01.L": ("x", 14.0, 1, 0.5), "upperarm01.R": ("x", 14.0, 1, 0.0),
    }),
}  # fmt: skip


def main(description: dict[str, Any], target: Path, facts: Path) -> int:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    addon_utils.enable(EXTENSION, default_set=True)
    from bl_ext.user_default.mpfb.services.humanservice import (  # type: ignore[import-not-found]
        HumanService,
    )
    from bl_ext.user_default.mpfb.services.locationservice import (  # type: ignore[import-not-found]
        LocationService,
    )
    from bl_ext.user_default.mpfb.services.targetservice import (  # type: ignore[import-not-found]
        TargetService,
    )

    sex, old = description["sex"], description["age"] == "old"
    weight, muscle = BUILD[description["build"]]
    macro = TargetService.get_default_macro_info_dict()
    macro.update({"gender": SEX[sex], "age": AGE[description["age"]], "weight": weight,
                  "muscle": muscle})  # fmt: skip
    body = HumanService.create_human(macro_detail_dict=macro, scale=0.1)
    rig = HumanService.add_builtin_rig(body, "default", import_weights=True)
    data = Path(LocationService.get_user_data())
    roles = {body.name: "skin"}
    for folder, kind, role in (
        (f"clothes/{DRESS[(description['dress'], sex)]}", "Clothes", "fabric"),
        (f"clothes/{SHOES[sex]}", "Clothes", "leather"),
        (f"hair/{HAIR[(sex, old)]}", "Hair", "hair"),
        ("eyebrows/eyebrow001", "Eyebrows", "hair"),
    ):
        asset = next((data / folder).glob("*.mhclo"))
        worn = HumanService.add_mhclo_asset(str(asset), body, asset_type=kind, subdiv_levels=0)
        roles[worn.name] = role
    bpy.context.view_layer.update()
    # The height asked, standing: the whole figure scaled before it is posed.
    tall = description["height"]
    if tall:
        low, high = _extent([obj for obj in bpy.data.objects if obj.type == "MESH"])
        rig.scale = (tall / (high.z - low.z),) * 3
        bpy.context.view_layer.update()
    _pose(rig, description["pose"])
    hips = rig.matrix_world @ rig.pose.bones["root"].head
    motion = description.get("motion", "")
    if motion:
        _move(rig, motion, description["pose"])
        _name_roles(roles)
        bpy.context.scene.frame_set(1)  # measured as it starts
    else:
        _bake(rig, roles)
    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    low, high = _extent(meshes)
    seat = _seat(meshes, hips) - low.z
    # Standing on the origin, which is under the hips: where a seated person sits.
    for obj in [rig] if motion else meshes:
        obj.location -= Vector((hips.x, hips.y, low.z))
    bpy.ops.export_scene.gltf(
        filepath=str(target), export_format="GLB", export_apply=True,
        export_animations=bool(motion),
    )  # fmt: skip
    size = high - low
    facts.write_text(json.dumps({
        "width": round(size.x, 3), "depth": round(size.y, 3), "height": round(size.z, 3),
        "faces": sum(len(obj.data.polygons) for obj in meshes),
        # Seated: how high the seat they fit is (the underside of their thighs).
        "seat": round(seat, 3) if description["pose"] == "seated" else 0.0,
        "motions": [motion] if motion else [],
    }))  # fmt: skip
    return 0


def _pose(rig: Any, pose: str) -> None:
    """Each named bone turned to point as the pose asks, parents first, so each child starts
    from where its parent now ends."""
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="POSE")
    world = rig.matrix_world
    for limb, (x, y, z) in POSES[pose].items():
        for side, sign in (("L", 1), ("R", -1)):
            opposed = pose in OPPOSED and side == "R"
            way = Vector((x * sign, -y if opposed else y, z)).normalized()
            bone = rig.pose.bones[f"{limb}.{side}"]
            bpy.context.view_layer.update()
            # The bone's axis (its Y) turned onto the wanted way, in the rig's own space.
            current = (bone.matrix.to_3x3() @ Vector((0, 1, 0))).normalized()
            wanted = (world.to_3x3().inverted() @ way).normalized()
            turn = current.rotation_difference(wanted).to_matrix().to_4x4()
            head = bone.matrix.translation.copy()
            bone.matrix = Matrix.Translation(head) @ turn @ bone.matrix.to_3x3().to_4x4()
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.update()


def _move(rig: Any, motion: str, pose: str) -> None:
    """A looping motion, named for what it is, on top of the pose: each bone keyed every
    few frames, turned about a world axis expressed in the bone's own frame. Every posed
    bone is keyed too, so the pose is part of the motion (an unkeyed bone falls back to
    the skeleton's rest wherever the model is used)."""
    frames, moves = MOTIONS[motion]
    action = bpy.data.actions.new(motion)
    rig.animation_data_create().action = action
    posed = {f"{limb}.{side}" for limb in POSES[pose] for side in ("L", "R")}
    # Each bone's pose as a quaternion (the rig turns its bones by Euler angles).
    rest = {name: rig.pose.bones[name].matrix_basis.to_quaternion() for name in posed | set(moves)}
    axes = {
        name: (rig.pose.bones[name].matrix.to_3x3().inverted() @ Vector(AXES[axis])).normalized()
        for name, (axis, *_) in moves.items()
    }
    for frame in range(1, frames + 2, 4):
        u = (frame - 1) / frames
        for name, held in rest.items():
            bone = rig.pose.bones[name]
            bone.rotation_mode = "QUATERNION"
            bone.rotation_quaternion = held
            if name in moves:
                _, degrees, times, phase = moves[name]
                angle = math.radians(degrees) * math.sin(math.tau * (u * times + phase))
                bone.rotation_quaternion = held @ Quaternion(axes[name], angle)
            bone.keyframe_insert("rotation_quaternion", frame=frame)


def _name_roles(roles: dict[str, str]) -> None:
    """Each surface's material named for its role, the skeleton kept."""
    for obj in [o for o in bpy.data.objects if o.type == "MESH"]:
        obj.data.materials.clear()
        obj.data.materials.append(bpy.data.materials.new(roles.get(obj.name, "fabric")))


def _bake(rig: Any, roles: dict[str, str]) -> None:
    """The posed figure as plain meshes (clothes masks applied, the skeleton gone), each
    surface's material named for its role."""
    graph = bpy.context.evaluated_depsgraph_get()
    for obj in [o for o in bpy.data.objects if o.type == "MESH"]:
        evaluated = obj.evaluated_get(graph)
        mesh = bpy.data.meshes.new_from_object(evaluated)
        placed = evaluated.matrix_world.copy()
        obj.modifiers.clear()
        obj.parent = None
        obj.data = mesh
        obj.matrix_world = placed
        mesh.materials.clear()
        mesh.materials.append(bpy.data.materials.new(roles.get(obj.name, "fabric")))
    bpy.data.objects.remove(rig)
    bpy.context.view_layer.update()


def _seat(meshes: list[Any], hips: Vector) -> float:
    """The underside of a seated figure: its lowest point within a hand's breadth of the
    hips, front to back (what rests on the seat: trousers, or skirt, or skin)."""
    near = [p.z for p in _points(meshes) if abs(p.y - hips.y) < 0.12 and abs(p.x - hips.x) < 0.2]
    return float(min(near, default=hips.z))


def _points(meshes: list[Any]) -> list[Vector]:
    """Every point of the meshes, as they stand (posed, masks applied), in the world."""
    graph = bpy.context.evaluated_depsgraph_get()
    points = []
    for obj in meshes:
        evaluated = obj.evaluated_get(graph)
        points += [evaluated.matrix_world @ v.co for v in evaluated.to_mesh().vertices]
        evaluated.to_mesh_clear()
    return points


def _extent(meshes: list[Any]) -> tuple[Vector, Vector]:
    """Where the meshes reach, as they stand."""
    points = _points(meshes)
    low = Vector([min(p[i] for p in points) for i in range(3)])
    high = Vector([max(p[i] for p in points) for i in range(3)])
    return low, high


if __name__ == "__main__":
    arguments = sys.argv[sys.argv.index("--") + 1 :]
    described, target, facts = arguments
    sys.exit(main(json.loads(Path(described).read_text()), Path(target), Path(facts)))
