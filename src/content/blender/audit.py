# SPDX-License-Identifier: GPL-3.0-or-later
"""Checks on a built shot before it is rendered, for what a few stills miss: the camera inside
something, or turning so fast it snaps. A failing check stops the render."""

import math
from typing import Any

import bpy  # type: ignore[import-not-found]
from mathutils import Vector  # type: ignore[import-not-found]

# The camera may not turn faster than this, in degrees a frame (moves keep well under it).
CAMERA_TURN = 20.0
SAMPLES = 24


def audit(frames: int, subject: tuple[Vector, float] | None = None) -> list[str]:
    """`subject` is what the shot films (its centre and radius), if the move said."""
    scene = bpy.context.scene
    camera = scene.camera
    issues: list[str] = []
    meshes = [obj for obj in scene.objects if obj.type == "MESH" and not obj.hide_render]
    previous = None
    for frame in sorted({1, frames, *range(1, frames + 1, max(1, frames // SAMPLES))}):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        point = camera.matrix_world.translation.copy()
        inside = [obj.name for obj in meshes if _inside(obj, point)]
        if inside:
            issues.append(f"frame {frame}: the camera is inside {', '.join(sorted(inside))}")
        if subject is not None:
            blocker = _blocking(scene, point, *subject)
            if blocker:
                issues.append(f"frame {frame}: {blocker} blocks the view of the subject")
        rotation = camera.matrix_world.to_quaternion()
        if previous is not None:
            before_frame, before = previous
            # q and −q are the same turn; the shorter way round is the real one.
            angle = before.rotation_difference(rotation).angle
            turn = math.degrees(min(angle, math.tau - angle)) / (frame - before_frame)
            if turn > CAMERA_TURN:
                issues.append(f"frame {frame}: the camera turns {turn:.0f}° a frame")
        previous = (frame, rotation)
    scene.frame_set(1)
    return issues


def _inside(obj: Any, point: Vector) -> bool:
    """Inside a closed mesh: a ray from the point crosses its surface an odd number of times."""
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    if not all(
        min(c[i] for c in corners) < point[i] < max(c[i] for c in corners) for i in range(3)
    ):
        return False
    local = obj.matrix_world.inverted() @ point
    direction = Vector((0.0, 0.0, 1.0))
    crossings = 0
    origin = local
    for _ in range(64):
        hit, location, _, _ = obj.ray_cast(origin, direction)
        if not hit:
            break
        crossings += 1
        origin = location + direction * 1e-4
    return crossings % 2 == 1


def _blocking(scene: Any, eye: Vector, centre: Vector, radius: float) -> str | None:
    """The thing between the camera and the subject, if any (glass does not count)."""
    towards = centre - eye
    distance = towards.length - radius
    if distance <= 0:
        return None
    hit, _, _, _, obj, _ = scene.ray_cast(
        bpy.context.evaluated_depsgraph_get(), eye, towards.normalized(), distance=distance
    )
    if not hit or any(
        slot.material and slot.material.name.startswith("glass") for slot in obj.material_slots
    ):
        return None
    return str(obj.name)
