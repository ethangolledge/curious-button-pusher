"""`Stage`: everything a block may do. Blocks are written against this interface only, never
against Blender's own API, so they stay short, readable and safe to change; `stage.py`
implements it in Blender, and tests use a stand-in that records each call.

A verb is added here only when a new block needs it, with a test. That is the one routine
reason to touch the foundation."""

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from content.blender.maths import ORIGIN, Quat, Vec

# A funnel is an open cone, narrow at the top: a lamp shade, a hopper.
ShapeKind = Literal["box", "cylinder", "sphere", "cone", "funnel", "plane"]
LightKind = Literal["point", "spot", "sun", "area"]
# The surfaces a look knows how to draw; a block names what a thing is made of, the look
# decides how that looks.
Role = Literal[
    "wall", "floor", "ceiling", "ground", "road", "wood", "dark_wood", "metal", "glass",
    "paper", "card", "fabric", "leather", "plastic", "stone", "brick", "concrete", "money",
    "foliage", "rubber", "screen", "lamp_shade", "bulb", "paint", "skin", "hair",
]  # fmt: skip
Channel = Literal["power", "lens", "visible"]


class Thing(Protocol):
    """Something on the stage: a shape, a model, a light, the camera, or a group."""

    @property
    def name(self) -> str: ...


@dataclass(frozen=True, slots=True)
class Box:
    """A thing's extent in the world: its lowest and highest corners."""

    low: Vec
    high: Vec

    @property
    def centre(self) -> Vec:
        return self.low.lerp(self.high, 0.5)

    @property
    def size(self) -> Vec:
        return self.high - self.low

    @property
    def top(self) -> float:
        return self.high.z

    @property
    def radius(self) -> float:
        """Half the box's diagonal: a sphere that holds it."""
        return self.size.length() / 2

    def overlaps(self, other: "Box") -> bool:
        return all(
            getattr(self.low, axis) < getattr(other.high, axis)
            and getattr(other.low, axis) < getattr(self.high, axis)
            for axis in "xyz"
        )

    def encloses(self, other: "Box") -> bool:
        return all(
            getattr(self.low, axis) <= getattr(other.low, axis)
            and getattr(other.high, axis) <= getattr(self.high, axis)
            for axis in "xyz"
        )

    def union(self, other: "Box") -> "Box":
        low, high = self.low, self.high
        return Box(
            Vec(min(low.x, other.low.x), min(low.y, other.low.y), min(low.z, other.low.z)),
            Vec(max(high.x, other.high.x), max(high.y, other.high.y), max(high.z, other.high.z)),
        )


def standing_in(space: Box, extents: Sequence[Box]) -> list[Box]:
    """Of the extents of the separate things on a stage, those standing in a space: solids
    reaching into it, not the room around it, nor lights and empty places."""
    return [
        box for box in extents if box.radius > 0 and box.overlaps(space) and not box.encloses(space)
    ]


@dataclass(frozen=True, slots=True)
class Pose:
    frame: int
    at: Vec
    rotation: Quat


@dataclass(frozen=True, slots=True)
class Mark:
    """A named place a layout offers: where a prop stands, where the camera might be. `facing`
    is the way something placed there faces; `surface` is the top it sits on, if any."""

    name: str
    at: Vec
    facing: Vec
    surface: Box | None = None


class Stage(Protocol):
    @property
    def fps(self) -> int: ...

    @property
    def frames(self) -> int:
        """The shot's length in frames; frames are numbered from 1."""
        ...

    @property
    def aspect(self) -> float:
        """Width over height."""
        ...

    def random(self, purpose: str) -> random.Random:
        """Seeded randomness: the same job always makes the same shot."""
        ...

    # --- Building ------------------------------------------------------------------------

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
        """A simple solid: `size` is its full width, depth and height in metres; `at` is the
        centre of its base; `turn` is degrees about x, y and z."""
        ...

    def model(self, model_id: str, *, name: str, height: float | None = None) -> Thing:
        """A model from the library or a prop made in code, standing at the origin facing −Y,
        scaled to `height` metres if given."""
        ...

    def picture(self, model_id: str, *, name: str, width: float, lying: bool = False) -> Thing:
        """A picture from the library on a thin card `width` metres wide, at the origin:
        upright with its face towards −Y (a painting, a view through a window), or lying
        face up with its top towards +Y (a map on a table)."""
        ...

    def group(self, name: str, at: Vec = ORIGIN, parent: Thing | None = None) -> Thing:
        """An empty that other things hang from, so they move together."""
        ...

    def place(
        self, thing: Thing, at: Vec, *, facing: Vec | None = None, parent: Thing | None = None
    ) -> None:
        """Stand a thing at `at` (its base), turned to face `facing` on the ground."""
        ...

    def bounds(self, thing: Thing) -> Box: ...

    def parts(self, thing: Thing, prefix: str) -> list[Thing]:
        """A model's named parts, by the start of their name ("wheel")."""
        ...

    def occupied(self, space: Box) -> list[Box]:
        """The extents of the separate things standing in a space (a lamp on a desk-top),
        not counting what only encloses it (the room around it): where something placed
        there would pass into something else."""
        ...

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
        """A light; `power` in watts (sun: strength), `colour` as hex."""
        ...

    def camera(self) -> Thing:
        """The shot's camera."""
        ...

    # --- The layout's vocabulary -----------------------------------------------------------

    def mark(self, mark: Mark) -> None: ...

    def find_mark(self, name: str) -> Mark: ...

    def marks(self) -> list[Mark]: ...

    def path(self, name: str, points: Sequence[Vec]) -> None: ...

    def find_path(self, name: str) -> list[Vec]: ...

    def cast(self, actor_id: str, thing: Thing) -> None:
        """Name a thing as one of the shot's actors, so later blocks can refer to it."""
        ...

    def actor(self, actor_id: str) -> Thing: ...

    # --- Time ----------------------------------------------------------------------------

    def animate(self, thing: Thing, poses: Sequence[Pose]) -> None:
        """Where a thing is, and how it is turned, on each listed frame."""
        ...

    def animate_value(
        self, thing: Thing, channel: Channel, keys: Sequence[tuple[int, float]]
    ) -> None:
        """A light's power, the camera's lens (mm), or whether a thing is visible (0 or 1)."""
        ...

    def spin(self, thing: Thing, axis: Vec, degrees: Sequence[tuple[int, float]]) -> None:
        """Turn a part about its own axis (a wheel rolling, a fan), on top of its parent's
        motion."""
        ...

    def play(self, thing: Thing, motion: str, *, start_frame: int = 1, speed: float = 1.0) -> None:
        """A character plays one of its motions (by name, as its model lists them) from
        `start_frame`, repeating to the end of the shot; `speed` 2 plays it twice as fast."""
        ...

    def poses(self, thing: Thing) -> list[Pose]:
        """Every frame's pose of a thing animated so far, or its resting pose on every frame."""
        ...

    def simulate(
        self,
        bodies: Sequence[Thing],
        *,
        floors: Sequence[Box],
        start_frame: int,
        push: Mapping[str, Vec],
    ) -> None:
        """Let gravity take `bodies` from `start_frame`; those named in `push` are nudged that
        way (metres a second) as they are let go. They collide with each other and with
        `floors` (solid boxes). The result is baked into their animation."""
        ...
