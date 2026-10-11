# SPDX-License-Identifier: GPL-3.0-or-later
"""`Canvas`, built as a Blender shader: one plane filling an orthographic camera, its colour
worked out per pixel by the transition's program, so a transition renders on the GPU in a
fraction of a second a frame. Its own coordinates are the centred ones transitions use."""

from dataclasses import dataclass
from typing import Any

import bmesh  # type: ignore[import-not-found]
import bpy  # type: ignore[import-not-found]

from content.blender.canvas_api import Edge, Operation, Picture
from content.blender.materials import linear
from content.blender.maths import progress

OPERATIONS: dict[str, str] = {
    "add": "ADD", "subtract": "SUBTRACT", "multiply": "MULTIPLY", "divide": "DIVIDE",
    "power": "POWER", "logarithm": "LOGARITHM", "sqrt": "SQRT", "absolute": "ABSOLUTE",
    "minimum": "MINIMUM", "maximum": "MAXIMUM", "less_than": "LESS_THAN",
    "greater_than": "GREATER_THAN", "sine": "SINE", "cosine": "COSINE", "arctan2": "ARCTAN2",
    "fraction": "FRACT", "floor": "FLOOR", "modulo": "FLOORED_MODULO",
    "smooth_minimum": "SMOOTH_MIN", "exponent": "EXPONENT",
}  # fmt: skip


@dataclass(frozen=True)
class Node:
    """A value in the shader: a node's output."""

    output: Any


class BlenderCanvas:
    def __init__(
        self,
        *,
        frames: int,
        fps: int,
        aspect: float,
        pictures: dict[str, str],
        moving: dict[str, tuple[str, int]] | None = None,
    ) -> None:
        """`pictures` are stills; `moving` gives a side as a folder of numbered frames and
        the frame to start on, played on through the transition."""
        self._frames, self._fps, self._aspect = frames, fps, aspect
        scene = bpy.context.scene
        mesh = bpy.data.meshes.new("canvas")
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
        bmesh.ops.scale(bm, vec=(aspect, 1.0, 1.0), verts=bm.verts)
        bm.to_mesh(mesh)
        bm.free()
        plane = bpy.data.objects.new("canvas", mesh)
        scene.collection.objects.link(plane)
        self._material = bpy.data.materials.new("canvas")
        plane.data.materials.append(self._material)
        self._tree = self._material.node_tree
        self._tree.nodes.clear()
        camera = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
        camera.data.type = "ORTHO"
        camera.data.ortho_scale = max(aspect, 1.0)
        camera.location = (0.0, 0.0, 2.0)
        scene.collection.objects.link(camera)
        scene.camera = camera
        self._coords = self._tree.nodes.new("ShaderNodeTexCoord").outputs["Object"]
        self._images = {which: bpy.data.images.load(path) for which, path in pictures.items()}
        self._moving: dict[str, int] = {}
        for which, (folder, start) in (moving or {}).items():
            image = bpy.data.images.load(f"{folder}/0001.png")
            image.source = "SEQUENCE"
            self._images[which] = image
            self._moving[which] = start

    @property
    def aspect(self) -> float:
        return self._aspect

    @property
    def seconds(self) -> float:
        return self._frames / self._fps

    def _new(self, kind: str) -> Any:
        return self._tree.nodes.new(kind)

    def _feed(self, socket: Any, value: Any) -> None:
        if isinstance(value, Node):
            self._tree.links.new(value.output, socket)
        else:
            socket.default_value = float(value)

    def progress(self, ease: str = "in_out") -> Node:
        node = self._new("ShaderNodeValue")
        for frame, amount in enumerate(progress(self._frames, ease), start=1):
            node.outputs[0].default_value = amount
            node.outputs[0].keyframe_insert("default_value", frame=frame)
        return Node(node.outputs[0])

    def coords(self) -> Node:
        return Node(self._coords)

    def picture(self, which: Picture, at: Any, edge: Edge = "extend") -> Node:
        x, y = self.parts(at)
        uv = self.point(
            self.math("add", self.math("divide", x, self._aspect), 0.5), self.math("add", y, 0.5)
        )
        texture = self._new("ShaderNodeTexImage")
        texture.image = self._images[which]
        if which in self._moving:
            texture.image_user.frame_start = 1
            texture.image_user.frame_offset = self._moving[which] - 1
            texture.image_user.frame_duration = self._frames
            texture.image_user.use_auto_refresh = True
        texture.extension = edge.upper()
        texture.interpolation = "Cubic"
        self._feed(texture.inputs["Vector"], uv)
        return Node(texture.outputs["Color"])

    def math(self, operation: Operation, a: Any, b: Any = 0.0) -> Node:
        node = self._new("ShaderNodeMath")
        node.operation = OPERATIONS[operation]
        self._feed(node.inputs[0], a)
        self._feed(node.inputs[1], b)
        if operation == "logarithm" and not isinstance(b, Node) and b == 0.0:
            node.inputs[1].default_value = 2.718281828
        return Node(node.outputs[0])

    def point(self, x: Any, y: Any) -> Node:
        node = self._new("ShaderNodeCombineXYZ")
        self._feed(node.inputs["X"], x)
        self._feed(node.inputs["Y"], y)
        return Node(node.outputs[0])

    def parts(self, point: Any) -> tuple[Node, Node]:
        node = self._new("ShaderNodeSeparateXYZ")
        self._feed(node.inputs[0], point)
        return Node(node.outputs["X"]), Node(node.outputs["Y"])

    def noise(self, at: Any, scale: Any, detail: float = 2.0) -> Node:
        node = self._new("ShaderNodeTexNoise")
        self._feed(node.inputs["Vector"], at)
        self._feed(node.inputs["Scale"], scale)
        node.inputs["Detail"].default_value = detail
        return Node(node.outputs["Fac"])

    def mix(self, first: Any, second: Any, amount: Any) -> Node:
        node = self._new("ShaderNodeMix")
        node.data_type = "RGBA"
        sockets = {socket.identifier: socket for socket in node.inputs}
        self._feed(sockets["Factor_Float"], amount)
        self._feed(sockets["A_Color"], first)
        self._feed(sockets["B_Color"], second)
        outputs = {socket.identifier: socket for socket in node.outputs}
        return Node(outputs["Result_Color"])

    def colour(self, hex_colour: str) -> Node:
        node = self._new("ShaderNodeRGB")
        node.outputs[0].default_value = (*linear(hex_colour), 1.0)
        return Node(node.outputs[0])

    def output(self, colour: Any) -> None:
        emission = self._new("ShaderNodeEmission")
        self._feed(emission.inputs["Color"], colour)
        result = self._new("ShaderNodeOutputMaterial")
        self._tree.links.new(emission.outputs[0], result.inputs["Surface"])
