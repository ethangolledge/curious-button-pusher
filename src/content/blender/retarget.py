# SPDX-License-Identifier: GPL-3.0-or-later
"""Runs inside Blender: a stretch of a motion capture recording, retargeted onto the skeleton
every person shares, as a library motion (`staging/motions.py`).

    PYTHONPATH=src blender -b --factory-startup --python-use-system-env \\
        --python-exit-code 1 -P src/content/blender/retarget.py -- request.json out.blend facts.json

The recording is read (BVH), scaled so its legs are as long as the shared skeleton's, and
turned so the performer faces −Y as the stretch begins. Each of the skeleton's bones that has a
match in the recording then turns, frame by frame, as its match turned from where it stood at
rest (the skeleton first set in the recording's own rest pose, so an arm held out in the
recording is held out here); the hips also move as the performer's did. Bones without a match
(twist halves, fingers, the face) follow their parents. A loop (a walk) is cut where its last
frame comes back to its first, and its travel taken out, so it plays on the spot while the
shot carries the person along at its pace. Every person is made on the same skeleton, so a
motion retargeted once moves everyone alike. Writes the motion's length and pace to
`facts.json`."""

import json
import math
import sys
from pathlib import Path
from typing import Any

import bpy  # type: ignore[import-not-found]
from mathutils import Matrix, Vector  # type: ignore[import-not-found]

from content.blender.person import made

# Each recording's skeleton: the shared skeleton's bones, and the bone of the recording each
# turns with (a recording's bone runs from its joint to the next: `LeftArm` is the upper arm).
SIDES = (("L", "Left"), ("R", "Right"))
SKELETONS: dict[str, dict[str, str]] = {
    "cmu": {
        "root": "Hips", "spine05": "LowerBack", "spine03": "Spine", "spine01": "Spine1",
        "neck01": "Neck", "head": "Head",
        **{f"{bone}.{side}": f"{word}{name}" for side, word in SIDES for bone, name in (
            ("clavicle", "Shoulder"), ("upperarm01", "Arm"), ("lowerarm01", "ForeArm"),
            ("wrist", "Hand"), ("upperleg01", "UpLeg"), ("lowerleg01", "Leg"), ("foot", "Foot"),
        )},
    },
    "100style": {
        "root": "Hips", "spine05": "Chest", "spine03": "Chest2", "spine02": "Chest3",
        "spine01": "Chest4", "neck01": "Neck", "head": "Head",
        **{f"{bone}.{side}": f"{word}{name}" for side, word in SIDES for bone, name in (
            ("clavicle", "Collar"), ("upperarm01", "Shoulder"), ("lowerarm01", "Elbow"),
            ("wrist", "Wrist"), ("upperleg01", "Hip"), ("lowerleg01", "Knee"),
            ("foot", "Ankle"),
        )},
    },
}  # fmt: skip
# The skeleton motions are made for: an average man of the standard height.
STANDARD = {"sex": "man", "age": "middle", "build": "average", "dress": "casual", "height": 1.8}
# Joints closer than this (metres, as recorded) are in the same place.
SAME_PLACE = 1e-4
# A bone of the shared skeleton whose length is not the way its part runs, and the bone whose
# joint it runs to instead: a hand runs from the wrist to the knuckles.
KNUCKLES = {"wrist": "finger3-1"}
# A loop's end is looked for this far either side of where it was asked to end (a share of
# its length), where its pose comes back closest to its first.
LOOP_SEARCH = 0.3


def main(request: dict[str, Any], target: Path, facts: Path) -> int:
    rig = _skeleton()
    pairs = SKELETONS[request["skeleton"]]
    source, rate = _recording(Path(request["file"]))
    start = 1 + request["start"] * rate
    end = 1 + request["end"] * rate
    if request["loop"]:
        end = _loop_end(source, pairs, start, end)
    _fit(source, rig, pairs, start)
    fps = request["fps"]
    count = max(2, round((end - start) / rate * fps) + 1)
    action, travel = _bake(
        source, rig, pairs, request["name"], start, end, count, on_the_spot=request["loop"]
    )
    seconds = (end - start) / rate
    bpy.data.libraries.write(str(target), {action}, fake_user=True, compress=True)
    facts.write_text(json.dumps({
        "frames": count, "seconds": round(seconds, 3),
        "speed": round(travel.length / seconds, 3) if request["loop"] else 0.0,
    }))  # fmt: skip
    return 0


def _skeleton() -> Any:
    """The shared skeleton, alone (its body only shaped it)."""
    rig, _ = made(STANDARD)
    for obj in [o for o in bpy.data.objects if o.type == "MESH"]:
        bpy.data.objects.remove(obj)
    for bone in rig.pose.bones:
        for constraint in list(bone.constraints):
            bone.constraints.remove(constraint)
        bone.rotation_mode = "QUATERNION"
    return rig


def _recording(path: Path) -> tuple[Any, float]:
    """The recording, read as Blender reads BVH, and how many of its frames make a second."""
    rate = 1 / float(
        next(line for line in path.read_text().splitlines() if "Frame Time" in line).split()[-1]
    )
    bpy.ops.import_anim.bvh(
        filepath=str(path), frame_start=1, use_fps_scale=False, update_scene_fps=False,
        update_scene_duration=False, rotate_mode="NATIVE", axis_forward="-Z", axis_up="Y",
    )  # fmt: skip
    source = bpy.context.view_layer.objects.active
    bpy.context.scene.frame_end = max(
        bpy.context.scene.frame_end, int(source.animation_data.action.frame_range[1])
    )
    return source, rate


def _at(frame: float) -> None:
    bpy.context.scene.frame_set(int(frame), subframe=frame % 1)


def _head(rig: Any, name: str) -> Vector:
    return rig.matrix_world @ rig.pose.bones[name].head


def _fit(source: Any, rig: Any, pairs: dict[str, str], start: float) -> None:
    """The recording scaled to the skeleton's leg length, stood where the skeleton stands,
    and turned so the performer faces −Y as the stretch begins."""
    bpy.context.view_layer.update()
    rest = {bone.name: bone.head_local for bone in source.data.bones}
    leg = (rest[pairs["upperleg01.L"]] - rest[pairs["foot.L"]]).length
    bones = rig.data.bones
    ours = (bones["upperleg01.L"].head_local - bones["foot.L"].head_local).length
    source.scale = (ours / leg,) * 3
    _at(start)
    left = _head(source, pairs["upperleg01.L"]) - _head(source, pairs["upperleg01.R"])
    # Facing −Y, a person's left is +X: the turn that brings their left there.
    source.rotation_mode = "XYZ"
    source.rotation_euler.z -= math.atan2(left.y, left.x)
    _at(start)
    hips, ours_hips = _head(source, pairs["root"]), _head(rig, "root")
    source.location += Vector((ours_hips.x - hips.x, ours_hips.y - hips.y, 0.0))
    bpy.context.view_layer.update()


def _loop_end(source: Any, pairs: dict[str, str], start: float, end: float) -> float:
    """Where a loop comes back closest to its first pose, near `end` (in the recording's
    frames): the summed turn between each bone's pose then and at its start."""
    bones = [source.pose.bones[name] for name in pairs.values()]
    _at(start)
    first = [bone.matrix_basis.to_quaternion() for bone in bones]
    reach = (end - start) * LOOP_SEARCH
    best, best_end = math.inf, end
    for frame in range(int(end - reach), int(end + reach) + 1):
        _at(frame)
        apart = sum(
            bone.matrix_basis.to_quaternion().rotation_difference(q).angle
            for bone, q in zip(bones, first, strict=True)
        )
        if apart < best:
            best, best_end = apart, float(frame)
    return best_end


def _bake(
    source: Any,
    rig: Any,
    pairs: dict[str, str],
    name: str,
    start: float,
    end: float,
    count: int,
    *,
    on_the_spot: bool,
) -> tuple[Any, Vector]:
    """Each matched bone keyed, frame by frame, turning in the world as its match turns from
    where it stood at rest; the hips moving as the performer's do (`on_the_spot`: but for
    their travel over the ground, taken out evenly, as a loop walks on the spot). Returns the
    action and how far the hips travelled over the ground."""
    order = [b.name for b in rig.data.bones if b.name in pairs]  # parents first
    world = source.matrix_world.to_3x3()
    rest = {
        ours: world @ source.data.bones[theirs].matrix_local.to_3x3()
        for ours, theirs in pairs.items()
    }
    # The skeleton stood in the recording's rest pose, each bone along its match.
    _stand_as(rig, {ours: world @ _length(source, pairs[ours]) for ours in order})
    ours_rest = {
        ours: rig.matrix_world.to_3x3() @ rig.pose.bones[ours].matrix.to_3x3() for ours in order
    }
    action = bpy.data.actions.new(name)
    rig.animation_data_create().action = action
    root_rest = _head(rig, "root")
    _at(end)
    hips_end = _head(source, pairs["root"])
    _at(start)
    hips_start = _head(source, pairs["root"])
    travel = Vector((hips_end.x - hips_start.x, hips_end.y - hips_start.y, 0.0))
    for index in range(count):
        frame = start + (end - start) * index / (count - 1)
        _at(frame)
        turns = {
            ours: (world @ source.pose.bones[pairs[ours]].matrix.to_3x3())
            @ rest[ours].inverted()
            @ ours_rest[ours]
            for ours in order
        }
        hips = root_rest + (_head(source, pairs["root"]) - hips_start)
        if on_the_spot:
            hips -= travel * (index / (count - 1))
        _set_pose(rig, turns, root=hips)
        for ours in order:
            bone = rig.pose.bones[ours]
            bone.keyframe_insert("rotation_quaternion", frame=index + 1)
        rig.pose.bones["root"].keyframe_insert("location", frame=index + 1)
    return action, travel


def _length(source: Any, name: str) -> Vector:
    """Which way a recording's bone runs at rest, in its own space: from its joint to the next
    joint along that is somewhere else (a recording may put two joints in one place: CMU's hand
    and the base of its fingers)."""
    bone = source.data.bones[name]
    for joint in bone.children_recursive:
        if (joint.head_local - bone.head_local).length > SAME_PLACE:
            return joint.head_local - bone.head_local
    return bone.tail_local - bone.head_local


def _stand_as(rig: Any, ways: dict[str, Vector]) -> None:
    """Each bone turned (parents first) so its length runs the way given in the world, its
    roll kept: a hand's length is its wrist to its knuckles."""
    to_rig = rig.matrix_world.to_3x3().inverted()
    for name, way in ways.items():
        bone = rig.pose.bones[name]
        bpy.context.view_layer.update()
        towards = KNUCKLES.get(name.split(".")[0])
        side = name.split(".")[-1]
        current = (
            rig.pose.bones[f"{towards}.{side}"].head - bone.head
            if towards
            else bone.matrix.to_3x3().col[1]
        )
        turn = current.normalized().rotation_difference((to_rig @ way).normalized())
        head = bone.matrix.translation.copy()
        bone.matrix = Matrix.Translation(head) @ (turn.to_matrix() @ bone.matrix.to_3x3()).to_4x4()
    bpy.context.view_layer.update()


def _set_pose(rig: Any, turns: dict[str, Matrix], *, root: Vector) -> None:
    """Each bone turned to face as `turns` says in the world, parents first, the root also
    moved to `root`."""
    to_rig = rig.matrix_world.inverted()
    for name, turn in turns.items():
        bone = rig.pose.bones[name]
        bpy.context.view_layer.update()
        head = to_rig @ root if name == "root" else bone.matrix.translation.copy()
        rotation = to_rig.to_3x3() @ turn
        bone.matrix = Matrix.Translation(head) @ rotation.normalized().to_4x4()
    bpy.context.view_layer.update()


if __name__ == "__main__":
    arguments = sys.argv[sys.argv.index("--") + 1 :]
    request, target, facts = arguments
    sys.exit(main(json.loads(Path(request).read_text()), Path(target), Path(facts)))
