# SPDX-License-Identifier: GPL-3.0-or-later
"""Checks on a built shot before it is rendered, for what a few stills miss: the camera inside
something or turning so fast it snaps, the subject hidden, or two things passing into each
other (a figure sunk into a table, a box half through a wall). A failing check stops the
render."""

import math
from typing import Any

import bpy  # type: ignore[import-not-found]
from mathutils import Vector  # type: ignore[import-not-found]
from mathutils.bvhtree import BVHTree  # type: ignore[import-not-found]

from content.blender.imports import skinned

# The camera may not turn faster than this, in degrees a frame (moves keep well under it).
CAMERA_TURN = 20.0
SAMPLES = 24
# Things may touch, but not pass into each other by more than this (metres); a character's
# motion may sink a foot a little further.
OVERLAP, POSED_OVERLAP = 0.01, 0.03


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
    for frame in sorted({1, (frames + 1) // 2, frames}):
        scene.frame_set(frame)
        issues += [f"frame {frame}: {a} and {b} pass into each other" for a, b in _overlaps()]
    scene.frame_set(1)
    return issues


def _overlaps() -> list[tuple[str, str]]:
    """The pairs of separate things (each top-level object with everything hanging from it)
    that pass into each other, as they stand this frame. Each solid is shrunk by `OVERLAP`
    before they are compared, so things that only touch (a phone on a desk, a chair on the
    floor) do not count."""
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    solids = [
        _shrunk(obj, depsgraph)
        for obj in bpy.context.scene.objects
        if obj.type == "MESH" and not obj.hide_render
    ]
    found: set[tuple[str, str]] = set()
    for index, (thing, low, high, tree) in enumerate(solids):
        for other, other_low, other_high, other_tree in solids[index + 1 :]:
            pair = (min(thing, other), max(thing, other))
            if thing == other or pair in found:
                continue
            apart = any(high[i] < other_low[i] or other_high[i] < low[i] for i in range(3))
            if not apart and tree.overlap(other_tree):
                found.add(pair)
    return sorted(found)


def _shrunk(obj: Any, depsgraph: Any) -> tuple[str, Vector, Vector, Any]:
    """Which thing a solid belongs to, its extent, and a tree of its faces drawn in towards
    its middle, so its outermost points (a foot's sole, a box's face) move in by the margin.
    The solid is its mesh as built, without the look's outlines or bevels, unless a skeleton
    poses it. (Shrinking along each point's normal would be truer for hollow shapes, but
    scans and generated models often have normals facing every way.)"""
    thing = obj
    while thing.parent is not None:
        thing = thing.parent
    posed = skinned(obj)
    evaluated = obj.evaluated_get(depsgraph) if posed else None
    mesh = evaluated.to_mesh() if evaluated else obj.data
    world = obj.matrix_world
    points = [world @ v.co for v in mesh.vertices]
    low = Vector([min(p[i] for p in points) for i in range(3)]) if points else world.translation
    high = Vector([max(p[i] for p in points) for i in range(3)]) if points else world.translation
    # Thin things (a card, a sheet of paper) shrink by a fraction of their thickness.
    depth = min(POSED_OVERLAP if posed else OVERLAP, 0.3 * min(high - low))
    middle, half = (low + high) / 2, (high - low) / 2
    keep = Vector([1 - depth / h if h > 0 else 0.0 for h in half])
    inward = [middle + (p - middle) * keep for p in points]
    tree = BVHTree.FromPolygons(inward, [tuple(face.vertices) for face in mesh.polygons])
    if evaluated:
        evaluated.to_mesh_clear()
    return thing.name, low, high, tree


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
