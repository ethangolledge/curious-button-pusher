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
from mathutils import Matrix, Vector  # type: ignore[import-not-found]

from content.blender.rigging import loop

EXTENSION = "bl_ext.user_default.mpfb"
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
# What a person does with their hands, by pose: where each wrist that moves goes (metres right,
# back and up from the hips, or up from the table top or the floor), how its fingers close, and
# where what they hold goes.
# Body measures are for a 1.8 m person and scale with height; tables and floors do not.
Point = tuple[float, float, float, str]
ACTIVITIES: dict[tuple[str, str], dict[str, Any]] = {
    ("seated", "resting"): {
        "hands": {"L": (0.17, -0.42, 0.06, "table"), "R": (-0.17, -0.42, 0.06, "table")},
        "fingers": {"L": "flat", "R": "flat"},
    },
    ("seated", "drink"): {
        "hands": {"L": (0.17, -0.42, 0.06, "table"), "R": (-0.12, -0.45, 0.08, "table")},
        "fingers": {"L": "flat", "R": "hold"},
        "holds": {"drink": (-0.15, -0.53, 0.0, "table")},
    },
    ("seated", "reading"): {
        "hands": {"L": (0.13, -0.44, 0.06, "table"), "R": (-0.13, -0.44, 0.06, "table")},
        "fingers": {"L": "hold", "R": "hold"},
        "holds": {"document": (0.0, -0.5, 0.0, "table")},
    },
    ("seated", "writing"): {
        "hands": {"L": (0.15, -0.44, 0.06, "table"), "R": (-0.06, -0.47, 0.07, "table")},
        "fingers": {"L": "flat", "R": "hold"},
        "holds": {"paper": (0.02, -0.52, 0.0, "table")},
    },
    ("seated", "pointing"): {
        "hands": {"L": (0.17, -0.42, 0.06, "table"), "R": (-0.14, -0.78, 0.22, "table")},
        "fingers": {"L": "flat", "R": "point"},
    },
    ("seated", "lap"): {
        "hands": {"L": (0.12, -0.24, 0.12, "hips"), "R": (-0.12, -0.24, 0.12, "hips")},
        "fingers": {"L": "rest", "R": "rest"},
    },
    ("seated", "folded"): {
        "hands": {"L": (-0.13, -0.2, 0.3, "hips"), "R": (0.13, -0.22, 0.33, "hips")},
        "fingers": {"L": "rest", "R": "rest"},
    },
    ("standing", "drink"): {
        "hands": {"R": (-0.17, -0.2, 0.12, "hips")},
        "fingers": {"R": "hold"},
        "holds": {"drink": (-0.17, -0.27, 0.06, "hips")},
    },
    ("standing", "phone"): {
        "hands": {"R": (-0.1, -0.02, 0.66, "hips")},
        "fingers": {"R": "hold"},
        "holds": {"phone": (-0.08, -0.06, 0.7, "hips")},
    },
    ("standing", "pockets"): {
        "hands": {"L": (0.19, -0.04, -0.02, "hips"), "R": (-0.19, -0.04, -0.02, "hips")},
        "fingers": {"L": "rest", "R": "rest"},
    },
    ("standing", "folded"): {
        "hands": {"L": (-0.13, -0.2, 0.3, "hips"), "R": (0.13, -0.22, 0.33, "hips")},
        "fingers": {"L": "rest", "R": "rest"},
    },
    ("standing", "pointing"): {
        "hands": {"R": (-0.22, -0.55, 0.45, "hips")},
        "fingers": {"R": "point"},
    },
}
# How far each finger joint closes, by grip (degrees): the thumb, then the four fingers.
GRIPS = {"flat": (5.0, 5.0), "rest": (15.0, 30.0), "hold": (30.0, 70.0), "point": (40.0, 80.0)}
# Where an elbow points as an arm reaches: out to the side and back.
ELBOW = (0.55, 0.45, -0.1)

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
    activity = ACTIVITIES.get((description["pose"], description.get("activity", "")), {})
    held = _act(rig, activity, hips, description) if activity else {}
    motion = description.get("motion", "")
    if motion:
        _move(rig, motion, description["pose"], still=frozenset(activity.get("hands", ())))
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
        # The middle of the room they take up, from where they stand (a seated person's knees
        # and arms reach forward of their hips).
        "middle": [round((low.x + high.x) / 2 - hips.x, 3),
                   round((low.y + high.y) / 2 - hips.y, 3)],
        "faces": sum(len(obj.data.polygons) for obj in meshes),
        # Seated: how high the seat they fit is (the underside of their thighs).
        "seat": round(seat, 3) if description["pose"] == "seated" else 0.0,
        "motions": [motion] if motion else [],
        # Where what they hold goes (its base), from where they stand.
        "holds": {
            name: [round(at.x - hips.x, 3), round(at.y - hips.y, 3), round(at.z - low.z, 3)]
            for name, at in held.items()
        },
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


def _act(
    rig: Any, activity: dict[str, Any], hips: Vector, description: dict[str, Any]
) -> dict[str, Vector]:
    """Hands put where the activity has them, each arm bent to reach by inverse kinematics
    (the elbow out and back), the pose then kept and the fingers closed. Returns where what
    they hold goes, in the world as they stand."""
    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    low, _ = _extent(meshes)
    scale = (description["height"] or 1.8) / 1.8
    # A seated person is raised to sit on the chair: the table top, from their feet.
    lift = (
        description["chair"] - (_seat(meshes, hips) - low.z)
        if description["pose"] == "seated"
        else 0
    )
    table = low.z + description["table"] - max(0.0, lift)

    def where(point: Point) -> Vector:
        x, y, z, ref = point
        base = {"table": table, "floor": low.z, "hips": hips.z}[ref]
        body = scale if ref == "hips" else 1.0
        return Vector((hips.x + x * scale, hips.y + y * scale, base + z * body))

    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="POSE")
    made = []
    for side, point in activity["hands"].items():
        target = bpy.data.objects.new(f"reach.{side}", None)
        pole = bpy.data.objects.new(f"elbow.{side}", None)
        sign = 1 if side == "L" else -1
        target.location = where(point)
        pole.location = hips + Vector((ELBOW[0] * sign, ELBOW[1], ELBOW[2])) * scale
        for empty in (target, pole):
            bpy.context.scene.collection.objects.link(empty)
            made.append(empty)
        reach = rig.pose.bones[f"lowerarm02.{side}"].constraints.new("IK")
        reach.target, reach.pole_target, reach.chain_count = target, pole, 4
        reach.pole_angle = math.radians(-90)
    bpy.context.view_layer.update()
    bpy.ops.pose.select_all(action="SELECT")
    bpy.ops.pose.visual_transform_apply()
    for side in activity["hands"]:
        bone = rig.pose.bones[f"lowerarm02.{side}"]
        for constraint in list(bone.constraints):
            bone.constraints.remove(constraint)
        _close(rig, side, activity["fingers"][side])
    bpy.ops.object.mode_set(mode="OBJECT")
    for empty in made:
        bpy.data.objects.remove(empty)
    bpy.context.view_layer.update()
    return {name: where(point) for name, point in activity.get("holds", {}).items()}


def _close(rig: Any, side: str, grip: str) -> None:
    """A hand's fingers closed for its grip: each joint turned about its own crosswise axis;
    pointing keeps the index finger straight."""
    thumb, fingers = GRIPS[grip]
    for finger in range(1, 6):
        for joint in range(1, 4):
            bone = rig.pose.bones.get(f"finger{finger}-{joint}.{side}")
            if bone is None:
                continue
            bent = thumb if finger == 1 else fingers
            if grip == "point" and finger == 2:
                bent = 0.0
            bone.rotation_mode = "XYZ"
            bone.rotation_euler.x += math.radians(bent)


def _move(rig: Any, motion: str, pose: str, still: frozenset[str] = frozenset()) -> None:
    """A looping motion on top of the pose (`rigging.loop`); every posed bone is keyed too.
    Hands on something keep the body still under them: only the head moves."""
    frames, every = MOTIONS[motion]
    moves = {name: move for name, move in every.items() if not still or name == "head"}
    posed = {f"{limb}.{side}" for limb in POSES[pose] for side in ("L", "R")}
    loop(rig, motion, (frames, moves), keep=posed)


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
