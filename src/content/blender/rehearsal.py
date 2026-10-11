"""A stage without Blender: it keeps track of where everything is and records every verb.
Used to check a shot before it is rendered (does every name it refers to exist?) and to test
every block's example in milliseconds. Rotation is ignored in extents: a rehearsal checks
names and rough places, not pixels."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from content.blender.api import (
    Box,
    Channel,
    LightKind,
    Mark,
    Pose,
    Role,
    ShapeKind,
    Thing,
    standing_in,
)
from content.blender.blocks.base import Prop
from content.blender.bookkeeping import Bookkeeping
from content.blender.maths import ORIGIN, Quat, Vec, axis_angle, heading_rotation


@dataclass(eq=False)
class Piece:
    name: str
    at: Vec
    size: Vec
    parent: "Piece | None" = None
    turn: Quat = field(default_factory=Quat)
    children: list["Piece"] = field(default_factory=list)

    def world(self) -> Vec:
        return self.at + (self.parent.world() if self.parent else Vec())

    def extent(self) -> Box:
        base = self.world()
        corners = [
            self.turn.rotate(Vec(x * self.size.x / 2, y * self.size.y / 2, z * self.size.z))
            for x in (-1, 1) for y in (-1, 1) for z in (0, 1)
        ]  # fmt: skip
        box = Box(
            base + Vec(*(min(getattr(c, a) for c in corners) for a in "xyz")),
            base + Vec(*(max(getattr(c, a) for c in corners) for a in "xyz")),
        )
        for child in self.children:
            box = box.union(child.extent())
        return box


class RehearsalStage(Bookkeeping):
    def __init__(
        self,
        *,
        frames: int,
        fps: int = 30,
        aspect: float = 9 / 16,
        seed: int = 1,
        props: Mapping[str, type[Prop]] | None = None,
        model_sizes: Mapping[str, tuple[float, float, float]] | None = None,
        model_parts: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    ) -> None:
        super().__init__(frames=frames, fps=fps, aspect=aspect, seed=seed)
        self._props = dict(props or {})
        self._model_sizes = dict(model_sizes or {})
        self._model_parts = dict(model_parts or {})
        self._poses: dict[str, list[Pose]] = {}
        self._pieces: dict[str, Piece] = {}
        self._camera = Piece("camera", Vec(), Vec())
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _new(self, name: str, at: Vec, size: Vec, parent: Thing | None) -> Piece:
        if name in self._pieces:
            raise ValueError(f"two things are called '{name}'")
        owner = self._piece(parent) if parent is not None else None
        piece = Piece(name, at, size, owner)
        self._pieces[name] = piece
        if owner is not None:
            owner.children.append(piece)
        return piece

    @staticmethod
    def _piece(thing: Thing) -> Piece:
        assert isinstance(thing, Piece)
        return thing

    def _record(self, verb: str, **details: Any) -> None:
        self.calls.append((verb, details))

    def shape(
        self,
        kind: ShapeKind,
        size: Vec,
        at: Vec,
        *,
        role: Role,
        name: str,
        turn: Vec = ORIGIN,
        parent: Thing | None = None,
        bevel: float = 0.0,
    ) -> Thing:
        self._record("shape", kind=kind, name=name, size=size, at=at, role=role)
        piece = self._new(name, at, size, parent)
        piece.turn = (
            axis_angle(Vec(0, 0, 1), turn.z)
            * axis_angle(Vec(0, 1, 0), turn.y)
            * axis_angle(Vec(1, 0, 0), turn.x)
        )
        return piece

    def model(self, model_id: str, *, name: str, height: float | None = None) -> Thing:
        self._record("model", model=model_id, name=name, height=height)
        if model_id in self._props:
            group = self._new(name, Vec(), Vec(), None)
            built = self._props[model_id]().build(self, f"{name}.body")
            self.place(built, Vec(), parent=group)
            return group
        if model_id not in self._model_sizes:
            raise KeyError(f"no model or prop called '{model_id}'")
        w, d, h = self._model_sizes[model_id]
        scale = height / h if height else 1.0
        model = self._new(name, Vec(), Vec(w, d, h) * scale, None)
        for part in self._model_parts.get(model_id, ()):
            at, size = Vec(*part["at"]) * scale, Vec(*part["size"]) * scale
            # A part's extent is measured from its base, as every piece's is.
            piece = self._new(f"{name}.{part['name']}", at - Vec(0, 0, size.z / 2), size, model)
            piece.turn = heading_rotation(Vec(*part["facing"]))
        return model

    def picture(self, model_id: str, *, name: str, width: float, lying: bool = False) -> Thing:
        self._record("picture", model=model_id, name=name, width=width, lying=lying)
        if model_id not in self._model_sizes:
            raise KeyError(f"no picture called '{model_id}'")
        w, _, h = self._model_sizes[model_id]
        tall = width * h / w
        size = Vec(width, tall, 0.002) if lying else Vec(width, 0.002, tall)
        return self._new(name, Vec(), size, None)

    def group(self, name: str, at: Vec = ORIGIN, parent: Thing | None = None) -> Thing:
        self._record("group", name=name, at=at)
        return self._new(name, at, Vec(), parent)

    def place(
        self, thing: Thing, at: Vec, *, facing: Vec | None = None, parent: Thing | None = None
    ) -> None:
        piece = self._piece(thing)
        self._record("place", name=piece.name, at=at, facing=facing)
        if parent is not None:
            if piece.parent is not None:
                piece.parent.children.remove(piece)
            piece.parent = self._piece(parent)
            piece.parent.children.append(piece)
        piece.at = at
        if facing is not None:
            piece.turn = heading_rotation(facing)

    def bounds(self, thing: Thing) -> Box:
        return self._piece(thing).extent()

    def occupied(self, space: Box) -> list[Box]:
        self._record("occupied", space=space)
        tops = [piece for piece in self._pieces.values() if piece.parent is None]
        return standing_in(space, [piece.extent() for piece in tops])

    def parts(self, thing: Thing, prefix: str) -> list[Thing]:
        found: list[Thing] = []
        stack = list(self._piece(thing).children)
        while stack:
            child = stack.pop(0)
            if child.name.split(".")[-1].startswith(prefix):
                found.append(child)
            stack.extend(child.children)
        return found

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
        parent: Thing | None = None,
    ) -> Thing:
        self._record("light", kind=kind, name=name, at=at, colour=colour, power=power)
        return self._new(name, at, Vec(), parent)

    def camera(self) -> Thing:
        return self._camera

    def mark(self, mark: Mark) -> None:
        self._record("mark", name=mark.name, at=mark.at)
        super().mark(mark)

    def path(self, name: str, points: Sequence[Vec]) -> None:
        self._record("path", name=name, points=list(points))
        super().path(name, points)

    def cast(self, actor_id: str, thing: Thing) -> None:
        super().cast(actor_id, self._piece(thing))

    def animate(self, thing: Thing, poses: Sequence[Pose]) -> None:
        piece = self._piece(thing)
        self._record("animate", name=piece.name, first=poses[0], last=poses[-1], count=len(poses))
        self._poses[piece.name] = list(poses)

    def animate_value(
        self, thing: Thing, channel: Channel, keys: Sequence[tuple[int, float]]
    ) -> None:
        self._record(
            "animate_value", name=thing.name, channel=channel, first=keys[0], last=keys[-1]
        )

    def spin(self, thing: Thing, axis: Vec, degrees: Sequence[tuple[int, float]]) -> None:
        self._record("spin", name=thing.name, axis=axis, last=degrees[-1])

    def play(self, thing: Thing, motion: str, *, start_frame: int = 1, speed: float = 1.0) -> None:
        self._record("play", name=thing.name, motion=motion, start=start_frame, speed=speed)

    def poses(self, thing: Thing) -> list[Pose]:
        piece = self._piece(thing)
        if piece.name in self._poses:
            return self._poses[piece.name]
        return [Pose(frame, piece.world(), piece.turn) for frame in range(1, self._frames + 1)]

    def simulate(
        self,
        bodies: Sequence[Thing],
        *,
        floors: Sequence[Box],
        start_frame: int,
        push: Mapping[str, Vec],
    ) -> None:
        self._record(
            "simulate", bodies=[b.name for b in bodies], start=start_frame, push=dict(push)
        )


@dataclass(frozen=True)
class Recorded:
    """A value in a recorded transition program: the number of the step that made it."""

    step: int


class RecordingCanvas:
    """A canvas without Blender: it writes down the transition's program, step by step, so a
    transition can be checked and tested without rendering."""

    def __init__(self, *, aspect: float = 9 / 16, seconds: float = 4.0) -> None:
        self._aspect, self._seconds = aspect, seconds
        self.steps: list[tuple[str, tuple[Any, ...]]] = []
        self.shown: Recorded | None = None

    @property
    def aspect(self) -> float:
        return self._aspect

    @property
    def seconds(self) -> float:
        return self._seconds

    def _step(self, verb: str, *inputs: Any) -> Recorded:
        self.steps.append((verb, tuple(i.step if isinstance(i, Recorded) else i for i in inputs)))
        return Recorded(len(self.steps) - 1)

    def progress(self, ease: str = "in_out") -> Recorded:
        return self._step("progress", ease)

    def coords(self) -> Recorded:
        return self._step("coords")

    def picture(self, which: str, at: Any, edge: str = "extend") -> Recorded:
        return self._step("picture", which, at, edge)

    def math(self, operation: str, a: Any, b: Any = 0.0) -> Recorded:
        return self._step("math", operation, a, b)

    def point(self, x: Any, y: Any) -> Recorded:
        return self._step("point", x, y)

    def parts(self, point: Any) -> tuple[Recorded, Recorded]:
        return self._step("x", point), self._step("y", point)

    def noise(self, at: Any, scale: Any, detail: float = 2.0) -> Recorded:
        return self._step("noise", at, scale, detail)

    def mix(self, first: Any, second: Any, amount: Any) -> Recorded:
        return self._step("mix", first, second, amount)

    def colour(self, hex_colour: str) -> Recorded:
        return self._step("colour", hex_colour)

    def output(self, colour: Any) -> None:
        self.shown = colour
