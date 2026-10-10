# SPDX-License-Identifier: GPL-3.0-or-later
"""`Stage`, implemented with Blender's own API: the foundation every block stands on. Nothing
else that builds a shot touches `bpy` (looks aside, which shape materials).

It also enforces what no block should have to remember: every thing gets the look's material
for its role, every animation is keyed per frame and linear between, names are unique, and
simulated bodies are recorded as ordinary animation."""

import math
import random
from collections.abc import Mapping, Sequence
from typing import Any

import bmesh  # type: ignore[import-not-found]
import bpy  # type: ignore[import-not-found]
from mathutils import Matrix, Vector  # type: ignore[import-not-found]

from content.blender.api import Box, Channel, LightKind, Mark, Pose, Role, ShapeKind
from content.blender.blocks.base import Look, Prop
from content.blender.maths import ORIGIN, Quat, Vec, heading_rotation, look_rotation

BlenderObject = Any


def linear(colour: str) -> tuple[float, float, float]:
    """A hex colour (sRGB, as a person picks it) in Blender's linear light."""
    value = colour.lstrip("#")
    channels = [int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(  # type: ignore[return-value]
        c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    )


class BlenderStage:
    def __init__(
        self,
        *,
        frames: int,
        fps: int,
        aspect: float,
        seed: int,
        look: Look,
        props: Mapping[str, type[Prop]],
        model_files: Mapping[str, tuple[str, tuple[float, float, float]]],
    ) -> None:
        self._frames, self._fps, self._aspect, self._seed = frames, fps, aspect, seed
        self._look = look
        self._props = props
        self._model_files = model_files
        self._scene = bpy.context.scene
        self._marks: dict[str, Mark] = {}
        self._paths: dict[str, list[Vec]] = {}
        self._actors: dict[str, BlenderObject] = {}
        self._poses: dict[str, list[Pose]] = {}
        self._camera = self._make_camera()

    @property
    def fps(self) -> int:
        return self._fps

    @property
    def frames(self) -> int:
        return self._frames

    @property
    def aspect(self) -> float:
        return self._aspect

    def random(self, purpose: str) -> random.Random:
        return random.Random(f"{self._seed}:{purpose}")

    # --- Building ------------------------------------------------------------------------

    @staticmethod
    def _unused(name: str) -> str:
        # Blender would quietly rename a second "lamp" to "lamp.001"; blocks refer to things
        # by name, so a clash is a mistake to report.
        if name in bpy.data.objects:
            raise ValueError(f"two things are called '{name}'")
        return name

    def _link(self, obj: BlenderObject, at: Vec, parent: BlenderObject | None) -> BlenderObject:
        self._scene.collection.objects.link(obj)
        obj.location = at.tuple()
        if parent is not None:
            obj.parent = parent
        return obj

    def shape(
        self,
        kind: ShapeKind,
        size: Vec,
        at: Vec,
        *,
        role: Role,
        name: str,
        turn: Vec = ORIGIN,
        parent: BlenderObject | None = None,
        bevel: float = 0.0,
    ) -> BlenderObject:
        mesh = bpy.data.meshes.new(self._unused(name))
        bm = bmesh.new()
        if kind == "box":
            bmesh.ops.create_cube(bm, size=1.0)
        elif kind in ("cylinder", "cone", "funnel"):
            top = {"cylinder": 0.5, "cone": 0.0, "funnel": 0.18}[kind]
            bmesh.ops.create_cone(
                bm, cap_ends=kind != "funnel", segments=40, radius1=0.5, radius2=top, depth=1.0
            )
        elif kind == "sphere":
            bmesh.ops.create_uvsphere(bm, u_segments=40, v_segments=20, radius=0.5)
        else:
            bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
        lift = 0.0 if kind == "plane" else 0.5
        bmesh.ops.transform(
            bm,
            matrix=Matrix.Diagonal((size.x, size.y, size.z, 1.0))
            @ Matrix.Translation((0, 0, lift)),
            verts=bm.verts,
        )
        if kind in ("cylinder", "cone", "funnel", "sphere"):
            for face in bm.faces:
                face.smooth = kind == "sphere" or abs(face.normal.z) < 0.99
        bm.to_mesh(mesh)
        bm.free()
        obj = bpy.data.objects.new(name, mesh)
        obj.data.materials.append(self._look.material(role))
        obj.rotation_euler = tuple(math.radians(a) for a in turn.tuple())
        if role == "bulb":
            # A bulb surrounds its light; it must not shadow it.
            obj.visible_shadow = False
        if bevel > 0:
            modifier = obj.modifiers.new("bevel", "BEVEL")
            modifier.width = bevel
            modifier.segments = 3
            modifier.limit_method = "ANGLE"
        self._look.dress(obj)
        return self._link(obj, at, parent)

    def model(self, model_id: str, *, name: str, height: float | None = None) -> BlenderObject:
        group = self.group(name)
        if model_id in self._props:
            body: BlenderObject = self._props[model_id]().build(self, f"{name}.body")
            body.parent = group
        elif model_id in self._model_files:
            path, _ = self._model_files[model_id]
            before = set(bpy.data.objects)
            bpy.ops.import_scene.gltf(filepath=path)
            imported = [obj for obj in bpy.data.objects if obj not in before]
            for obj in imported:
                if obj.parent is None:
                    obj.parent = group
                self._look.restyle(obj)
                if obj.type == "MESH":
                    self._look.dress(obj)
        else:
            raise KeyError(f"no model or prop called '{model_id}'")
        if height:
            box = self.bounds(group)
            if box.size.z > 0:
                group.scale = (height / box.size.z,) * 3
        return group

    def picture(
        self, model_id: str, *, name: str, width: float, lying: bool = False
    ) -> BlenderObject:
        if model_id not in self._model_files:
            raise KeyError(f"no picture called '{model_id}'")
        path, (w, _, h) = self._model_files[model_id]
        tall = width * h / w
        size = Vec(width, tall, 0.002) if lying else Vec(width, 0.002, tall)
        card = self.shape("box", size, Vec(), role="paper", name=name)
        card.data.materials.clear()
        card.data.materials.append(self._look.picture(path))
        # The image is laid across the card, its top at the far edge (lying) or the top.
        layer = card.data.uv_layers.new(name="UVMap")
        for polygon in card.data.polygons:
            for index in polygon.loop_indices:
                corner = card.data.vertices[card.data.loops[index].vertex_index].co
                up = (corner.y / tall + 0.5) if lying else corner.z / tall
                layer.data[index].uv = (corner.x / width + 0.5, up)
        return card

    def group(
        self, name: str, at: Vec = ORIGIN, parent: BlenderObject | None = None
    ) -> BlenderObject:
        empty = bpy.data.objects.new(self._unused(name), None)
        empty.empty_display_size = 0.2
        return self._link(empty, at, parent)

    def place(
        self,
        thing: BlenderObject,
        at: Vec,
        *,
        facing: Vec | None = None,
        parent: BlenderObject | None = None,
    ) -> None:
        if parent is not None:
            thing.parent = parent
        thing.location = at.tuple()
        if facing is not None:
            thing.rotation_mode = "QUATERNION"
            thing.rotation_quaternion = heading_rotation(facing).tuple()

    def bounds(self, thing: BlenderObject) -> Box:
        bpy.context.view_layer.update()
        corners: list[Vector] = []
        stack = [thing]
        while stack:
            obj = stack.pop()
            if obj.type == "MESH":
                corners += [obj.matrix_world @ Vector(c) for c in obj.bound_box]
            stack.extend(obj.children)
        if not corners:
            at = thing.matrix_world.translation
            return Box(Vec(*at), Vec(*at))
        low = Vec(*(min(c[i] for c in corners) for i in range(3)))
        high = Vec(*(max(c[i] for c in corners) for i in range(3)))
        return Box(low, high)

    def parts(self, thing: BlenderObject, prefix: str) -> list[BlenderObject]:
        return [
            obj
            for obj in thing.children_recursive
            if obj.name.split(".")[-1].lower().startswith(prefix)
            or obj.name.lower().startswith(prefix)
        ]

    def light(
        self,
        kind: LightKind,
        *,
        name: str,
        at: Vec,
        colour: str,
        power: float,
        aim: Vec | None = None,
        size: float = 0.1,
        cone_degrees: float = 45.0,
        parent: BlenderObject | None = None,
    ) -> BlenderObject:
        data = bpy.data.lights.new(self._unused(name), kind.upper())
        data.color = linear(colour)
        data.energy = power
        if kind == "spot":
            data.spot_size = math.radians(cone_degrees)
            data.spot_blend = 0.25
        if kind == "area":
            data.size = size
        else:
            data.shadow_soft_size = size
        obj = bpy.data.objects.new(name, data)
        self._link(obj, at, parent)
        if aim is not None:
            obj.rotation_mode = "QUATERNION"
            obj.rotation_quaternion = look_rotation(aim - at).tuple()
        return obj

    def _make_camera(self) -> BlenderObject:
        data = bpy.data.cameras.new("camera")
        data.lens = 35
        data.sensor_fit = "AUTO"
        data.clip_start = 0.02
        data.clip_end = 1000
        obj = bpy.data.objects.new("camera", data)
        self._scene.collection.objects.link(obj)
        self._scene.camera = obj
        return obj

    def camera(self) -> BlenderObject:
        return self._camera

    # --- The layout's vocabulary -----------------------------------------------------------

    def mark(self, mark: Mark) -> None:
        self._marks[mark.name] = mark

    def find_mark(self, name: str) -> Mark:
        if name not in self._marks:
            raise KeyError(f"the layout has no mark '{name}' (marks: {', '.join(self._marks)})")
        return self._marks[name]

    def marks(self) -> list[Mark]:
        return list(self._marks.values())

    def path(self, name: str, points: Sequence[Vec]) -> None:
        self._paths[name] = list(points)

    def find_path(self, name: str) -> list[Vec]:
        if name not in self._paths:
            raise KeyError(f"the layout has no path '{name}' (paths: {', '.join(self._paths)})")
        return self._paths[name]

    def cast(self, actor_id: str, thing: BlenderObject) -> None:
        if actor_id in self._actors:
            raise ValueError(f"two actors are called '{actor_id}'")
        self._actors[actor_id] = thing

    def actor(self, actor_id: str) -> BlenderObject:
        if actor_id not in self._actors:
            raise KeyError(f"no actor '{actor_id}' (actors: {', '.join(self._actors)})")
        return self._actors[actor_id]

    # --- Time ----------------------------------------------------------------------------

    def animate(self, thing: BlenderObject, poses: Sequence[Pose]) -> None:
        thing.rotation_mode = "QUATERNION"
        for pose in poses:
            thing.location = pose.at.tuple()
            thing.rotation_quaternion = pose.rotation.tuple()
            thing.keyframe_insert("location", frame=pose.frame)
            thing.keyframe_insert("rotation_quaternion", frame=pose.frame)
        self._poses[thing.name] = list(poses)
        # Keying leaves the thing at its last pose until the frame is read again; blocks built
        # after this one measure the shot as it stands now.
        now = self._scene.frame_current
        current = next((pose for pose in poses if pose.frame == now), poses[0])
        thing.location = current.at.tuple()
        thing.rotation_quaternion = current.rotation.tuple()

    def animate_value(
        self, thing: BlenderObject, channel: Channel, keys: Sequence[tuple[int, float]]
    ) -> None:
        for frame, value in keys:
            if channel == "visible":
                thing.hide_render = thing.hide_viewport = value < 0.5
                thing.keyframe_insert("hide_render", frame=frame)
                thing.keyframe_insert("hide_viewport", frame=frame)
            else:
                prop = "energy" if channel == "power" else "lens"
                setattr(thing.data, prop, value)
                thing.data.keyframe_insert(prop, frame=frame)

    def spin(self, thing: BlenderObject, axis: Vec, degrees: Sequence[tuple[int, float]]) -> None:
        thing.rotation_mode = "XYZ"
        rest = Vector(thing.rotation_euler)
        for frame, angle in degrees:
            turn = Vector(axis.tuple()) * math.radians(angle)
            thing.rotation_euler = tuple(rest + turn)
            thing.keyframe_insert("rotation_euler", frame=frame)

    def play(
        self, thing: BlenderObject, motion: str, *, start_frame: int = 1, speed: float = 1.0
    ) -> None:
        rigs = [obj for obj in [thing, *thing.children_recursive] if obj.type == "ARMATURE"]
        if not rigs:
            raise ValueError(f"{thing.name} has no skeleton to play '{motion}' with")
        rig = rigs[0]
        data = rig.animation_data or rig.animation_data_create()
        # Its own copy of the motion: importing a model twice numbers the second "idle.001".
        held = [data.action, *(strip.action for track in data.nla_tracks for strip in track.strips)]
        found = next((a for a in held if a and a.name.split(".")[0] == motion), None)
        found = found or bpy.data.actions.get(motion)
        if found is None:
            raise KeyError(f"{thing.name} has no motion '{motion}'")
        data.action = None
        for track in list(data.nla_tracks):
            data.nla_tracks.remove(track)
        strip = data.nla_tracks.new().strips.new(motion, start_frame, found)
        strip.scale = 1 / speed
        length = (strip.frame_end - strip.frame_start) or 1
        strip.repeat = max(1.0, (self._frames - start_frame + 1) / length)

    def poses(self, thing: BlenderObject) -> list[Pose]:
        if thing.name in self._poses:
            return self._poses[thing.name]
        bpy.context.view_layer.update()
        location, rotation, _ = thing.matrix_world.decompose()
        resting = Pose(1, Vec(*location), Quat(*rotation))
        return [Pose(f, resting.at, resting.rotation) for f in range(1, self._frames + 1)]

    def simulate(
        self,
        bodies: Sequence[BlenderObject],
        *,
        floors: Sequence[Box],
        start_frame: int,
        push: Mapping[str, Vec],
    ) -> None:
        """Each body is stood in for by a box of its size, held still until `start_frame`,
        then moved by its `push` for two frames as it is let go (a body handed on from animation
        keeps its speed). The boxes fall; their motion is recorded onto the bodies as ordinary
        animation, and the stand-ins are removed."""
        scene = self._scene
        with bpy.context.temp_override(scene=scene):
            bpy.ops.rigidbody.world_add()
        world = scene.rigidbody_world
        world.point_cache.frame_start = 1
        world.point_cache.frame_end = self._frames
        world.substeps_per_frame = 20
        world.solver_iterations = 20
        stand_ins = {
            body.name: self._stand_in(self.bounds(body), body.name, True) for body in bodies
        }
        fixed = [self._stand_in(box, f"floor_{i}", False) for i, box in enumerate(floors)]
        bpy.context.view_layer.update()
        offsets = {
            b.name: stand_ins[b.name].matrix_world.inverted() @ b.matrix_world for b in bodies
        }
        let_go = max(start_frame, 3)
        for body_name, stand_in in stand_ins.items():
            step = Vector(push.get(body_name, Vec()).tuple()) / self._fps
            rest = stand_in.location.copy()
            stand_in.rigid_body.kinematic = True
            for frame, moved in ((let_go - 2, 0), (let_go - 1, 1), (let_go, 2)):
                stand_in.location = rest + step * moved
                stand_in.keyframe_insert("location", frame=frame)
            stand_in.rigid_body.keyframe_insert("kinematic", frame=let_go)
            stand_in.rigid_body.kinematic = False
            stand_in.rigid_body.keyframe_insert("kinematic", frame=let_go + 1)
        recorded: dict[str, list[Pose]] = {body.name: [] for body in bodies}
        for frame in range(1, self._frames + 1):
            scene.frame_set(frame)
            for body in bodies:
                matrix = stand_ins[body.name].matrix_world @ offsets[body.name]
                location, rotation, _ = matrix.decompose()
                recorded[body.name].append(Pose(frame, Vec(*location), Quat(*rotation)))
        for stand_in in [*stand_ins.values(), *fixed]:
            bpy.data.objects.remove(stand_in, do_unlink=True)
        with bpy.context.temp_override(scene=scene):
            bpy.ops.rigidbody.world_remove()
        scene.frame_set(1)
        for body in bodies:
            self.animate(body, recorded[body.name])

    def _stand_in(self, box: Box, name: str, moving: bool) -> BlenderObject:
        size = Vec(max(box.size.x, 0.005), max(box.size.y, 0.005), max(box.size.z, 0.005))
        stand_in = self.shape(
            "box",
            size,
            Vec(box.centre.x, box.centre.y, box.low.z),
            role="paint",
            name=f"{name}.stand_in",
        )
        stand_in.hide_render = True
        with bpy.context.temp_override(
            object=stand_in, active_object=stand_in, selected_objects=[stand_in]
        ):
            bpy.ops.rigidbody.object_add(type="ACTIVE" if moving else "PASSIVE")
        body = stand_in.rigid_body
        body.collision_shape = "BOX"
        body.friction = 0.7
        body.restitution = 0.05
        body.collision_margin = 0.001
        if moving:
            body.mass = max(size.x * size.y * size.z * 500, 0.02)
            body.angular_damping = 0.3
        return stand_in
