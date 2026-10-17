# SPDX-License-Identifier: GPL-3.0-or-later
"""Bones, inside Blender: one way of posing a person's skeleton for everyone, from the rules in
`body.py`. A person is made with it (each pose measured, `person.py`) and placed with it (on a
shot's real furniture, `stage.py`), so every person is posed the same way.

Also looping motions written as keys (`loop`), which a lifted person moves by (`lift.py`)."""

import math
from collections.abc import Iterable, Sequence
from dataclasses import replace
from typing import Any

import bpy  # type: ignore[import-not-found]
from mathutils import Matrix, Quaternion, Vector  # type: ignore[import-not-found]

from content.blender import body
from content.blender.api import Box
from content.blender.body import GRIPS, Frame, Reach, knee
from content.blender.maths import Vec

AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
Motion = tuple[int, dict[str, tuple[str, float, int, float]]]
# Keys every so many frames (each motion is smooth between them).
EVERY = 4
# A seated body's legs are bent to the seat only when it is further than this from fitting.
FITS = 0.01
# A hand resting on a surface: its lowest point this far above it (metres); its thumb turned
# out from its fingers by this much (against their length).
RESTS, THUMB_OUT = 0.003, 0.7


def rig_of(thing: Any) -> Any | None:
    """The skeleton in a thing (a person), if it has one."""
    return next((obj for obj in [thing, *thing.children_recursive] if obj.type == "ARMATURE"), None)


def hips(rig: Any) -> Vec:
    """Where a person's hips are, in the world."""
    bpy.context.view_layer.update()
    return Vec(*(rig.matrix_world @ rig.pose.bones["root"].head))


def pose(rig: Any, ways: dict[str, Vec]) -> None:
    """Each named bone turned to point its way, parents first, so each child starts from
    where its parent now ends."""
    with _posing(rig):
        for name, way in ways.items():
            _aim(rig, name, way)


def sit(rig: Any, frame: Frame, seat: float) -> None:
    """A seated body fitted to a seat `seat` metres above the floor: each leg bent by inverse
    kinematics until the underside of the thighs is that high when the feet stand on the
    floor (thighs sloping down, as anyone's do on a high seat), then the body lowered (or
    raised) so the feet do."""
    meshes = skin(rig)
    low, _ = extent(meshes)
    drop = seat - (underside(meshes, frame.hips) - low.z)
    if abs(drop) > FITS:
        with _posing(rig):
            targets = {}
            for side in ("L", "R"):
                shin = rig.pose.bones[f"lowerleg02.{side}"]
                ankle = rig.matrix_world @ shin.tail
                pole = Vector(knee(frame, side).tuple())
                targets[f"lowerleg02.{side}"] = (ankle - Vector((0.0, 0.0, drop)), pole)
            _reach_by_ik(rig, targets)
    low, _ = extent(skin(rig))
    rig.matrix_world = Matrix.Translation((0.0, 0.0, frame.floor - low.z)) @ rig.matrix_world
    bpy.context.view_layer.update()


def perform(
    rig: Any, frame: Frame, pose_name: str, doing: str, *, seat: float, table: Box | None
) -> dict[str, Vec]:
    """A person posed as `body.py` says, from rest: their limbs set for the pose; seated on a
    seat `seat` metres high; their hands doing `doing` (on `table`, the table before them, if
    any). Returns where each thing they hold goes (its base), by name."""
    pose(rig, body.ways(pose_name, frame))
    if pose_name == "seated":
        sit(rig, frame, seat)
    frame = replace(frame, hips=hips(rig))
    near = body.table_before(table, frame) if table is not None else None
    reach(rig, body.reaches(pose_name, doing, frame, near))
    return body.holds(pose_name, doing, frame, near)


def reach(rig: Any, reaches: Sequence[Reach]) -> None:
    """Each hand put where it reaches, the arm bent by inverse kinematics (the elbow pointing
    its way); a hand lying on something laid along it; then the fingers closed. A hand lying
    on a surface is then lifted until its lowest point rests on it, never in it."""
    if not reaches:
        return
    with _posing(rig):
        _bend_arms(rig, {r.side: r for r in reaches})
        for r in reaches:
            _close(rig, r.side, r.grip, r.lying)
    lifted = {}
    for r in reaches:
        sunk = r.surface + RESTS - _lowest(rig, r.side) if r.lying is not None else 0.0
        if sunk > 0:
            lifted[r.side] = replace(r, at=r.at + Vec(0.0, 0.0, sunk))
    if lifted:
        with _posing(rig):
            _bend_arms(rig, lifted)


def _bend_arms(rig: Any, reaches: dict[str, Reach]) -> None:
    """Each arm bent until its wrist reaches; a hand lying on something laid along it (the
    wrist bent, not carrying on down the arm). In pose mode."""
    _reach_by_ik(
        rig,
        {
            f"lowerarm02.{side}": (Vector(r.at.tuple()), Vector(r.elbow.tuple()))
            for side, r in reaches.items()
        },
    )
    for side, r in reaches.items():
        if r.lying is not None:
            _palm_down(rig, side)
            _aim(rig, f"wrist.{side}", r.lying, towards=f"finger3-1.{side}")


def _lowest(rig: Any, side: str) -> float:
    """The lowest point of a hand (every point its wrist or fingers bend most), in the world."""
    hand = {f"wrist.{side}"} | {b.name for b in rig.pose.bones if b.name.endswith(f".{side}")
                                and b.name.startswith(("finger", "metacarpal"))}  # fmt: skip
    graph = bpy.context.evaluated_depsgraph_get()
    lowest = math.inf
    for obj in skin(rig):
        groups = {g.index for g in obj.vertex_groups if g.name in hand}
        if not groups:
            continue
        evaluated = obj.evaluated_get(graph)
        moved = evaluated.to_mesh().vertices
        for vertex in obj.data.vertices:
            weight = sum(g.weight for g in vertex.groups if g.group in groups)
            if weight > 0.5:
                lowest = min(lowest, (evaluated.matrix_world @ moved[vertex.index].co).z)
        evaluated.to_mesh_clear()
    return lowest


def rest(rig: Any) -> None:
    """The skeleton back as it was made: every bone at rest, the body where it stood."""
    for bone in rig.pose.bones:
        bone.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


def skin(rig: Any) -> list[Any]:
    """The surfaces a skeleton bends: the body, its clothes and hair."""
    return [obj for obj in rig.children_recursive if obj.type == "MESH"]


def underside(meshes: list[Any], at: Vec) -> float:
    """The underside of a seated body: its lowest point within a hand's breadth of the hips,
    front to back (what rests on the seat: trousers, or skirt, or skin)."""
    near = [p.z for p in points(meshes) if abs(p.y - at.y) < 0.12 and abs(p.x - at.x) < 0.2]
    return float(min(near, default=at.z))


def points(meshes: list[Any]) -> list[Vector]:
    """Every point of the meshes, as they stand (posed, masks applied), in the world."""
    graph = bpy.context.evaluated_depsgraph_get()
    out = []
    for obj in meshes:
        evaluated = obj.evaluated_get(graph)
        out += [evaluated.matrix_world @ v.co for v in evaluated.to_mesh().vertices]
        evaluated.to_mesh_clear()
    return out


def extent(meshes: list[Any]) -> tuple[Vector, Vector]:
    """Where the meshes reach, as they stand."""
    found = points(meshes)
    low = Vector([min(p[i] for p in found) for i in range(3)])
    high = Vector([max(p[i] for p in found) for i in range(3)])
    return low, high


class _posing:
    """The skeleton in pose mode while it is posed, every change kept as it is left."""

    def __init__(self, rig: Any) -> None:
        self._rig = rig

    def __enter__(self) -> None:
        bpy.context.view_layer.objects.active = self._rig
        bpy.ops.object.mode_set(mode="POSE")

    def __exit__(self, *_: object) -> None:
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.context.view_layer.update()


def _aim(rig: Any, name: str, way: Vec, *, towards: str = "") -> None:
    """A bone turned to point `way` (in the world), about its head; in pose mode. What points
    is the bone itself, or the line from its head to another bone's (`towards`: a wrist turned
    so the hand, wrist to knuckles, points the way)."""
    bone = rig.pose.bones[name]
    bpy.context.view_layer.update()
    # The bone's axis (its Y), or the line to `towards`, turned onto the wanted way, in the
    # rig's own space.
    current = (
        (rig.pose.bones[towards].head - bone.head).normalized()
        if towards
        else (bone.matrix.to_3x3() @ Vector((0, 1, 0))).normalized()
    )
    wanted = (rig.matrix_world.to_3x3().inverted() @ Vector(way.tuple()).normalized()).normalized()
    turn = current.rotation_difference(wanted).to_matrix().to_4x4()
    head = bone.matrix.translation.copy()
    bone.matrix = Matrix.Translation(head) @ turn @ bone.matrix.to_3x3().to_4x4()


def _palm_down(rig: Any, side: str) -> None:
    """A forearm turned about its own length (as a forearm turns, so the wrist does not twist)
    until the palm faces down: the way the fingers close (the middle finger's +Z) turned as
    near straight down as it can. In pose mode."""
    forearm = rig.pose.bones[f"lowerarm02.{side}"]
    finger = rig.pose.bones.get(f"finger3-1.{side}")
    if finger is None:
        return
    bpy.context.view_layer.update()
    to_rig = rig.matrix_world.to_3x3().inverted()
    axis = (forearm.matrix.to_3x3() @ Vector((0, 1, 0))).normalized()
    palm = finger.matrix.to_3x3() @ Vector((0, 0, 1))
    down = to_rig @ Vector((0.0, 0.0, -1.0))
    palm, down = (palm - axis * palm.dot(axis)), (down - axis * down.dot(axis))
    if palm.length < 1e-6 or down.length < 1e-6:
        return
    angle = palm.angle(down)
    if palm.cross(down).dot(axis) < 0:
        angle = -angle
    turn = Matrix.Rotation(angle, 3, axis)
    head = forearm.matrix.translation.copy()
    forearm.matrix = Matrix.Translation(head) @ (turn @ forearm.matrix.to_3x3()).to_4x4()


def _reach_by_ik(rig: Any, ends: dict[str, tuple[Vector, Vector]]) -> None:
    """Each named bone's chain (four bones up from it) bent until its end reaches its target,
    the middle joint pointing at its pole; the result kept as the pose. In pose mode."""
    made = []
    for name, (target_at, pole_at) in ends.items():
        target = bpy.data.objects.new(f"reach {name}", None)
        pole = bpy.data.objects.new(f"pole {name}", None)
        target.location, pole.location = target_at, pole_at
        for empty in (target, pole):
            bpy.context.scene.collection.objects.link(empty)
            made.append(empty)
        solver = rig.pose.bones[name].constraints.new("IK")
        solver.target, solver.pole_target, solver.chain_count = target, pole, 4
        solver.pole_angle = math.radians(-90)
    bpy.context.view_layer.update()
    bpy.ops.pose.select_all(action="SELECT")
    bpy.ops.pose.visual_transform_apply()
    for name in ends:
        bone = rig.pose.bones[name]
        for constraint in list(bone.constraints):
            bone.constraints.remove(constraint)
    for empty in made:
        bpy.data.objects.remove(empty)


def _close(rig: Any, side: str, grip: str, along: Vec | None = None) -> None:
    """A hand's fingers drawn together and closed for its grip: each finger turned towards the
    middle one's way (on a hand lying on something, every joint laid `along` it first, as a
    hand on a table lies), then each joint turned about its own crosswise axis (into the
    palm); pointing keeps the index finger straight. In pose mode."""
    thumb, fingers, together = GRIPS[grip]
    middle = rig.pose.bones.get(f"finger3-1.{side}")
    if middle is not None:
        to_world = rig.matrix_world.to_3x3()

        def pointing(bone: Any) -> Vector:
            bpy.context.view_layer.update()
            return (to_world @ bone.matrix.to_3x3() @ Vector((0, 1, 0))).normalized()

        way = Vector(along.tuple()).normalized() if along is not None else pointing(middle)
        index, little = (
            rig.pose.bones.get(f"finger2-1.{side}"),
            rig.pose.bones.get(f"finger5-1.{side}"),
        )
        if along is not None and index is not None and little is not None:
            # The thumb lies beside the fingers, turned out towards its own side of the hand.
            across = (to_world @ (index.head - little.head)).normalized()
            for joint in (1, 2, 3):
                bone = rig.pose.bones.get(f"finger1-{joint}.{side}")
                if bone is not None:
                    _aim(rig, bone.name, Vec(*(way + across * THUMB_OUT).normalized()))
        for finger in (2, 3, 4, 5):
            for joint in (1, 2, 3) if along is not None else (1,):
                bone = rig.pose.bones.get(f"finger{finger}-{joint}.{side}")
                if bone is not None and (along is not None or finger != 3):
                    share = together if joint == 1 else 1.0
                    _aim(rig, bone.name, Vec(*pointing(bone).lerp(way, share)))
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


def loop(rig: Any, name: str, motion: Motion, *, keep: Iterable[str] = ()) -> Any:
    """`motion` keyed on `rig` as an action called `name`, on top of its pose: a loop of so
    many frames and, for each bone, an axis of the world it turns about (for a body facing −Y:
    x nods forward, y leans to the side, z turns), by up to so many degrees, so many times a
    loop, starting so far round (a fraction of a turn). Bones in `keep` are keyed still, so
    the pose is part of the motion (an unkeyed bone falls back to the skeleton's rest wherever
    the model is used)."""
    frames, moves = motion
    moves = {bone: move for bone, move in moves.items() if bone in rig.pose.bones}
    action = bpy.data.actions.new(name)
    rig.animation_data_create().action = action
    # Each bone's pose as a quaternion (a rig may turn its bones by Euler angles).
    held = {
        bone: rig.pose.bones[bone].matrix_basis.to_quaternion()
        for bone in {*keep, *moves}
        if bone in rig.pose.bones
    }
    axes = {
        bone: (rig.pose.bones[bone].matrix.to_3x3().inverted() @ Vector(AXES[axis])).normalized()
        for bone, (axis, *_) in moves.items()
    }
    for frame in range(1, frames + 2, EVERY):
        u = (frame - 1) / frames
        for bone, start in held.items():
            posed = rig.pose.bones[bone]
            posed.rotation_mode = "QUATERNION"
            posed.rotation_quaternion = start
            if bone in moves:
                _, degrees, times, phase = moves[bone]
                angle = math.radians(degrees) * math.sin(math.tau * (u * times + phase))
                posed.rotation_quaternion = start @ Quaternion(axes[bone], angle)
            posed.keyframe_insert("rotation_quaternion", frame=frame)
    return action
