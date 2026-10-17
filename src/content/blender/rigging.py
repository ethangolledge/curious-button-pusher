# SPDX-License-Identifier: GPL-3.0-or-later
"""Looping motions on a skeleton, written as keys: what a lifted person (a cut-out of a
picture, `lift.py`) breathes and talks by."""

import math
from collections.abc import Iterable
from typing import Any

import bpy  # type: ignore[import-not-found]
from mathutils import Quaternion, Vector  # type: ignore[import-not-found]

AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
Motion = tuple[int, dict[str, tuple[str, float, int, float]]]
# Keys every so many frames (each motion is smooth between them).
EVERY = 4


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
