# SPDX-License-Identifier: GPL-3.0-or-later
"""A lifted picture (`staging/lift.py`, one `.npz` file) built as a set: the background as a
mesh where the picture shows it (painted in behind its people, cut at its depth edges), a mesh
behind each edge's near side carrying the far side on (seen only as the camera moves past), and
each person a mesh of their own with a skeleton made from their pose, so they can breathe and
move a little. Every surface shows the picture's own colours, unlit, so the camera at
`mark_camera` sees the picture itself.

Its parts are the set's vocabulary (`blocks/layouts/set.py`): `mark_camera`, `mark_ahead`,
`actor_person_<n>` and `interior`."""

import json
from pathlib import Path
from typing import Any

import bpy  # type: ignore[import-not-found]
import numpy as np
from mathutils import Euler, Vector  # type: ignore[import-not-found]

from content.blender.rigging import Motion, loop

# Where neighbouring points' distances differ by more than this fraction a surface is cut
# rather than stretched: the background at every depth edge (sharpened to a clean step when
# lifted), so what is painted in behind shows through as the camera moves; a person only at a
# stray point well off them (an arm before the chest stays joined).
GROUND_JUMP = 0.1
PERSON_JUMP = 0.12
# The prefix every surface of a lifted picture is named with: no look recolours it.
PAINTED = "painted"
# The skeleton made for a lifted person, from their body points (COCO order, `vision.BODY`):
# each bone from one point to another; a point given as a pair is their middle.
BONES: dict[str, tuple[Any, Any, str | None]] = {
    "spine": ((11, 12), (5, 6), None),
    "neck": ((5, 6), 0, "spine"),
    "upper_arm.L": (5, 7, "spine"),
    "forearm.L": (7, 9, "upper_arm.L"),
    "upper_arm.R": (6, 8, "spine"),
    "forearm.R": (8, 10, "upper_arm.R"),
}
# How sure the pose must be of a point for a bone to be made from it.
SURE = 0.3
# How a lifted person moves (`rigging.loop`): small, for a figure seen from one side only.
# Seen from the front, a lean (y) and a nod (x) of the head and shoulders read as life; a turn
# would show the flatness.
MOTIONS: dict[str, Motion] = {
    "breathing": (120, {
        "spine": ("y", 0.5, 1, 0.0), "neck": ("y", 1.2, 1, 0.3), "upper_arm.L": ("x", 0.8, 1, 0.1),
        "upper_arm.R": ("x", 0.8, 1, 0.6),
    }),
    "talking": (60, {
        "neck": ("x", 3.0, 2, 0.0), "spine": ("y", 0.8, 1, 0.25), "forearm.L": ("y", 3.0, 2, 0.0),
        "forearm.R": ("y", 2.5, 1, 0.5),
    }),
}  # fmt: skip


def build(path: str) -> None:
    """Build the lifted picture in `path` into the current scene."""
    data = np.load(path)
    picture = data["picture"]
    stem = Path(path).stem
    parts = json.loads(str(data["parts"]))
    # Distances are measured from where the picture was taken.
    camera = np.array(next(p["at"] for p in parts if p["name"] == "mark_camera"), np.float32)
    background = _image(f"{stem} background", data["background"])
    _mesh(
        "background", data["ground"], data["ground_pixels"], picture.shape,
        unlit(background, edge="MIRROR"), jump=GROUND_JUMP, camera=camera,
    )  # fmt: skip
    # Behind the near side of each depth edge, the far side carried on: seen only past it.
    hidden = _image(f"{stem} hidden", data["hidden"])
    _mesh(
        "beyond", data["beyond"], data["ground_pixels"], picture.shape,
        unlit(hidden, edge="MIRROR"), inside=data["beyond_reach"],
    )  # fmt: skip
    for n, alpha in enumerate(data["people"]):
        image = _image(f"{stem} person {n}", np.dstack([picture, alpha]))
        actor = bpy.data.objects.new(f"actor_person_{n}", None)
        bpy.context.scene.collection.objects.link(actor)
        # Their surface reaches a little past their outline; their picture's own soft edge
        # (its alpha) draws the outline, sharp at every resolution.
        surface = _mesh(
            f"person_{n}", data["people_points"][n], data["points_pixels"], picture.shape,
            unlit(image, alpha=True), jump=PERSON_JUMP, camera=camera,
            inside=data["people_reach"][n],
        )  # fmt: skip
        surface.parent = actor
        _skeleton(actor, surface, data["joints"][n])
    for part in parts:
        if part["name"] == "interior":
            box = bpy.data.objects.new("interior", _box_mesh(Vector(part["size"])))
            box.location = Vector(part["at"])
            bpy.context.scene.collection.objects.link(box)
        elif part["name"].startswith("mark_"):
            mark = bpy.data.objects.new(part["name"], None)
            mark.location = Vector(part["at"])
            # A mark faces its empty's −Y.
            facing = Vector(part["facing"])
            mark.rotation_euler = Euler((0, 0, (-facing).to_2d().angle_signed(Vector((0, 1)))))
            bpy.context.scene.collection.objects.link(mark)


def unlit(image: Any, *, alpha: bool = False, edge: str = "EXTEND") -> Any:
    """A surface showing `image` exactly: its colour as light, nothing shading it; with
    `alpha`, see-through where the image is. Beyond the image's edges (a lifted background's
    margin) it is carried on as `edge` says: `MIRROR` reads as more of the scene, where
    `EXTEND` would streak its last pixels outwards."""
    material = bpy.data.materials.new(f"{PAINTED} {image.name}")
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = image
    texture.interpolation = "Cubic"
    texture.extension = edge
    glow = nodes.new("ShaderNodeEmission")
    links.new(texture.outputs["Color"], glow.inputs["Color"])
    out = nodes.new("ShaderNodeOutputMaterial")
    if alpha:
        clear = nodes.new("ShaderNodeBsdfTransparent")
        mix = nodes.new("ShaderNodeMixShader")
        links.new(texture.outputs["Alpha"], mix.inputs["Fac"])
        links.new(clear.outputs["BSDF"], mix.inputs[1])
        links.new(glow.outputs["Emission"], mix.inputs[2])
        links.new(mix.outputs["Shader"], out.inputs["Surface"])
        material.surface_render_method = "BLENDED"
    else:
        links.new(glow.outputs["Emission"], out.inputs["Surface"])
    return material


def _image(name: str, pixels: np.ndarray) -> Any:
    """A picture held in the scene from an array of rows, top first (uint8, RGB or RGBA)."""
    height, width = pixels.shape[:2]
    if pixels.shape[2] == 3:
        pixels = np.dstack([pixels, np.full((height, width), 255, np.uint8)])
    image = bpy.data.images.new(name, width, height, alpha=True)
    image.pixels.foreach_set((pixels[::-1].astype(np.float32) / 255).ravel())
    image.pack()
    return image


def _mesh(
    name: str,
    points: np.ndarray,
    pixels: np.ndarray,
    shape: tuple[int, ...],
    material: Any,
    *,
    jump: float = 0.0,
    camera: np.ndarray | None = None,
    inside: np.ndarray | None = None,
) -> Any:
    """A grid of `points` (rows, columns, 3) as a mesh, each vertex showing the picture at its
    pixel (`pixels`, x and y); `inside` keeps only the cells whose corners are all in it, and
    a `jump` drops cells across a change in distance (from `camera`) of more than that
    fraction."""
    rows, cols = points.shape[:2]
    index = np.arange(rows * cols).reshape(rows, cols)
    corners = np.stack(
        [index[:-1, :-1], index[1:, :-1], index[1:, 1:], index[:-1, 1:]], axis=-1
    ).reshape(-1, 4)
    keep = np.ones(len(corners), bool)
    flat = points.reshape(-1, 3)
    if inside is not None:
        keep &= inside.ravel()[corners].all(axis=1)
    if jump and camera is not None:
        far = np.linalg.norm(flat - camera, axis=1)[corners]
        keep &= far.max(axis=1) / np.maximum(far.min(axis=1), 1e-6) < 1 + jump
    corners = corners[keep]
    # Only the vertices some kept cell uses (a person is the cells inside their outline).
    used = np.unique(corners)
    renumbered = np.full(len(flat), -1)
    renumbered[used] = np.arange(len(used))
    corners, flat = renumbered[corners], flat[used]
    pixels = pixels.reshape(-1, 2)[used]
    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(len(flat))
    mesh.vertices.foreach_set("co", flat.ravel())
    mesh.loops.add(corners.size)
    mesh.loops.foreach_set("vertex_index", corners.ravel())
    mesh.polygons.add(len(corners))
    mesh.polygons.foreach_set("loop_start", np.arange(0, corners.size, 4))
    mesh.polygons.foreach_set("loop_total", np.full(len(corners), 4))
    height, width = shape[:2]
    uv = np.column_stack(
        [
            (pixels[:, 0] + 0.5) / width,
            1 - (pixels[:, 1] + 0.5) / height,
        ]
    )
    layer = mesh.uv_layers.new(name="UVMap")
    layer.data.foreach_set("uv", uv[corners.ravel()].astype(np.float32).ravel())
    mesh.update()
    mesh.validate()
    mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _skeleton(actor: Any, surface: Any, joints: np.ndarray) -> None:
    """Bones from a person's body points, weighted to their surface by Blender's automatic
    weights (bone heat), so a bone turned bends what is near it. Both hang from the actor."""

    def point(which: Any) -> Vector | None:
        group = which if isinstance(which, tuple) else (which,)
        if any(joints[i, 3] < SURE for i in group):
            return None
        return Vector(np.mean([joints[i, :3] for i in group], axis=0).tolist())

    # Named apart from the actor: a set casts every part named `actor_…`.
    own = actor.name.removeprefix("actor_")
    skeleton = bpy.data.armatures.new(f"{own} skeleton")
    rig = bpy.data.objects.new(f"{own} rig", skeleton)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    made: dict[str, Any] = {}
    for name, (start, end, parent) in BONES.items():
        head, tail = point(start), point(end)
        if head is None or tail is None or (tail - head).length < 0.02:
            continue
        bone = skeleton.edit_bones.new(name)
        bone.head, bone.tail = head, tail
        if parent in made:
            bone.parent = made[parent]
        made[name] = bone
    bpy.ops.object.mode_set(mode="OBJECT")
    if not made:
        bpy.data.objects.remove(rig)
        return
    bpy.ops.object.select_all(action="DESELECT")
    surface.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    rig.parent = actor
    # Its motions, kept on the rig for `Stage.play` to choose from.
    for name, motion in MOTIONS.items():
        action = loop(rig, name, motion)
        rig.animation_data.action = None
        track = rig.animation_data.nla_tracks.new()
        track.strips.new(name, 1, action)
        track.mute = True


def _box_mesh(size: Vector) -> Any:
    x, y, z = (v / 2 for v in size)
    corners = [(sx * x, sy * y, sz * z) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    mesh = bpy.data.meshes.new("interior")
    mesh.from_pydata(corners, [], faces)
    return mesh
