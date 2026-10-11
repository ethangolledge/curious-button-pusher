"""The geometry every block shares: vectors, rotations, easing, curves, and turning a curve into
one position per frame. Plain Python, so blocks can be tested without Blender.

Conventions, everywhere: metres and seconds; +Z is up; an object's front faces −Y (Blender's
and glTF's convention after import); a camera or spot light looks down its own −Z."""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True, slots=True)
class Vec:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __add__(self, other: "Vec") -> "Vec":
        return Vec(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vec") -> "Vec":
        return Vec(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scale: float) -> "Vec":
        return Vec(self.x * scale, self.y * scale, self.z * scale)

    def __neg__(self) -> "Vec":
        return Vec(-self.x, -self.y, -self.z)

    def dot(self, other: "Vec") -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: "Vec") -> "Vec":
        return Vec(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def length(self) -> float:
        return math.sqrt(self.dot(self))

    def normalised(self) -> "Vec":
        size = self.length()
        return self * (1 / size) if size > 1e-12 else Vec()

    def lerp(self, other: "Vec", t: float) -> "Vec":
        return self + (other - self) * t

    def flat(self) -> "Vec":
        """The same direction on the ground plane."""
        return Vec(self.x, self.y, 0.0)

    def tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


ORIGIN = Vec()
UP = Vec(0, 0, 1)
FRONT = Vec(0, -1, 0)  # where an object's front faces


@dataclass(frozen=True, slots=True)
class Quat:
    """A rotation, as Blender stores it (w, x, y, z)."""

    w: float = 1.0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __mul__(self, other: "Quat") -> "Quat":
        return Quat(
            self.w * other.w - self.x * other.x - self.y * other.y - self.z * other.z,
            self.w * other.x + self.x * other.w + self.y * other.z - self.z * other.y,
            self.w * other.y - self.x * other.z + self.y * other.w + self.z * other.x,
            self.w * other.z + self.x * other.y - self.y * other.x + self.z * other.w,
        )

    def dot(self, other: "Quat") -> float:
        return self.w * other.w + self.x * other.x + self.y * other.y + self.z * other.z

    def rotate(self, v: Vec) -> Vec:
        turned = self * Quat(0.0, v.x, v.y, v.z) * Quat(self.w, -self.x, -self.y, -self.z)
        return Vec(turned.x, turned.y, turned.z)

    def tuple(self) -> tuple[float, float, float, float]:
        return (self.w, self.x, self.y, self.z)


def axis_angle(axis: Vec, degrees: float) -> Quat:
    half = math.radians(degrees) / 2
    a = axis.normalised() * math.sin(half)
    return Quat(math.cos(half), a.x, a.y, a.z)


def from_basis(x: Vec, y: Vec, z: Vec) -> Quat:
    """The rotation whose local axes point along x, y and z (orthonormal)."""
    trace = x.x + y.y + z.z
    if trace > 0:
        s = 0.5 / math.sqrt(trace + 1.0)
        return Quat(0.25 / s, (y.z - z.y) * s, (z.x - x.z) * s, (x.y - y.x) * s)
    if x.x > y.y and x.x > z.z:
        s = 2.0 * math.sqrt(1.0 + x.x - y.y - z.z)
        return Quat((y.z - z.y) / s, 0.25 * s, (y.x + x.y) / s, (z.x + x.z) / s)
    if y.y > z.z:
        s = 2.0 * math.sqrt(1.0 + y.y - x.x - z.z)
        return Quat((z.x - x.z) / s, (y.x + x.y) / s, 0.25 * s, (z.y + y.z) / s)
    s = 2.0 * math.sqrt(1.0 + z.z - x.x - y.y)
    return Quat((x.y - y.x) / s, (z.x + x.z) / s, (z.y + y.z) / s, 0.25 * s)


def _side(forward: Vec) -> Vec:
    side = forward.cross(UP)
    # Looking straight up or down: any side will do, but always the same one.
    return side.normalised() if side.length() > 1e-6 else Vec(1, 0, 0)


def look_rotation(direction: Vec, roll_degrees: float = 0.0) -> Quat:
    """Turn a camera or spot light (which looks down its −Z, +Y up) to look along `direction`,
    keeping the horizon level unless rolled."""
    forward = direction.normalised()
    right = _side(forward)
    up = right.cross(forward)
    level = from_basis(right, up, -forward)
    return level * axis_angle(Vec(0, 0, 1), roll_degrees) if roll_degrees else level


def heading_rotation(direction: Vec, bank_degrees: float = 0.0, *, level: bool = True) -> Quat:
    """Turn an object (front along −Y, +Z up) to face `direction`, leaning `bank_degrees` into
    a bend (positive leans right). `level` keeps its nose on the ground plane; otherwise it
    pitches up and down with `direction`, as a plane climbs."""
    forward = (direction.flat() if level else direction).normalised()
    if forward.length() == 0:
        forward = FRONT
    # The object's local axes: +Y points behind it (its front is −Y), +X and +Z complete them.
    behind = -forward
    across = _side(behind)
    facing = from_basis(across, behind, across.cross(behind))
    return facing * axis_angle(Vec(0, 1, 0), -bank_degrees) if bank_degrees else facing


def fit_scale(
    size: tuple[float, float, float], fit: tuple[float, float, float]
) -> tuple[float, float, float]:
    """The scale that stretches a thing of `size` to `fit` (width, depth, height in metres):
    each axis given is that size; an axis given 0 keeps the proportions (of the height if it
    is given, else of the first given)."""
    ratios = [
        want / have if want and have > 0 else 0.0 for want, have in zip(fit, size, strict=True)
    ]
    uniform = ratios[2] or next((r for r in ratios if r), 1.0)
    x, y, z = (r or uniform for r in ratios)
    return x, y, z


def degrees_round(direction: Vec) -> float:
    """A ground direction as degrees round from −Y, anticlockwise from above: the convention
    of `Arc`, and of every camera angle measured from a subject's front."""
    return math.degrees(math.atan2(direction.x, -direction.y))


def angle_between(a: Quat, b: Quat) -> float:
    """Degrees of turn from one rotation to the other."""
    return math.degrees(2 * math.acos(min(1.0, abs(a.dot(b)))))


def slerp(a: Quat, b: Quat, t: float) -> Quat:
    dot = a.dot(b)
    if dot < 0:
        b, dot = Quat(-b.w, -b.x, -b.y, -b.z), -dot
    if dot > 0.9995:
        mixed = Quat(*(p + (q - p) * t for p, q in zip(a.tuple(), b.tuple(), strict=True)))
    else:
        theta = math.acos(dot)
        sa, sb = math.sin((1 - t) * theta), math.sin(t * theta)
        mixed = Quat(
            *(
                (p * sa + q * sb) / math.sin(theta)
                for p, q in zip(a.tuple(), b.tuple(), strict=True)
            )
        )
    size = math.sqrt(mixed.dot(mixed))
    return Quat(mixed.w / size, mixed.x / size, mixed.y / size, mixed.z / size)


def limit_turn(rotations: Sequence[Quat], max_degrees: float) -> list[Quat]:
    """No rotation turns more than `max_degrees` a frame: a turn that would snap is spread over
    the frames that follow."""
    if not rotations:
        return []
    limited = [rotations[0]]
    for wanted in rotations[1:]:
        turn = angle_between(limited[-1], wanted)
        limited.append(
            wanted if turn <= max_degrees else slerp(limited[-1], wanted, max_degrees / turn)
        )
    return limited


# --- Easing -------------------------------------------------------------------------------

Ease = Literal["linear", "in", "out", "in_out"]

EASES: dict[str, Callable[[float], float]] = {
    "linear": lambda t: t,
    "in": lambda t: t * t * t,
    "out": lambda t: 1 - (1 - t) ** 3,
    # Smootherstep: no jolt at either end, the camera operator's ease.
    "in_out": lambda t: t * t * t * (t * (t * 6 - 15) + 10),
}


def progress(frames: int, ease: str, start: float = 0.0, end: float = 1.0) -> list[float]:
    """For each frame of a shot, how far along (0 to 1) a motion is that starts and ends at
    those fractions of the shot."""
    curve = EASES[ease]
    out = []
    for index in range(frames):
        t = index / (frames - 1) if frames > 1 else 1.0
        local = 0.0 if t <= start else 1.0 if t >= end else (t - start) / (end - start)
        out.append(curve(local))
    return out


# --- Curves -------------------------------------------------------------------------------


class Curve(Protocol):
    def at(self, u: float) -> Vec: ...


@dataclass(frozen=True, slots=True)
class Still:
    point: Vec

    def at(self, u: float) -> Vec:
        return self.point


@dataclass(frozen=True, slots=True)
class Line:
    start: Vec
    end: Vec

    def at(self, u: float) -> Vec:
        return self.start.lerp(self.end, u)


@dataclass(frozen=True, slots=True)
class Arc:
    """A circle's arc around `centre`, measured in degrees from the centre's front (−Y),
    anticlockwise seen from above, rising from one height to another, and closing in or
    opening out if its radius changes."""

    centre: Vec
    radius: float
    start_degrees: float
    sweep_degrees: float
    height_from: float
    height_to: float
    # The radius at the end, if it changes: closing in makes a spiral.
    radius_to: float | None = None

    def at(self, u: float) -> Vec:
        angle = math.radians(self.start_degrees + self.sweep_degrees * u)
        end = self.radius if self.radius_to is None else self.radius_to
        radius = self.radius + (end - self.radius) * u
        return Vec(
            self.centre.x + radius * math.sin(angle),
            self.centre.y - radius * math.cos(angle),
            self.centre.z + self.height_from + (self.height_to - self.height_from) * u,
        )


@dataclass(frozen=True, slots=True)
class Spline:
    """A smooth path through every point (centripetal Catmull-Rom: no loops or overshoot)."""

    points: tuple[Vec, ...]

    def at(self, u: float) -> Vec:
        count = len(self.points)
        if count == 1:
            return self.points[0]
        scaled = min(max(u, 0.0), 1.0) * (count - 1)
        index = min(int(scaled), count - 2)
        t = scaled - index
        p0 = self.points[max(index - 1, 0)]
        p1, p2 = self.points[index], self.points[index + 1]
        p3 = self.points[min(index + 2, count - 1)]
        return _catmull_rom(p0, p1, p2, p3, t)


def _catmull_rom(p0: Vec, p1: Vec, p2: Vec, p3: Vec, t: float) -> Vec:
    def knot(a: Vec, b: Vec) -> float:
        return max(math.sqrt((b - a).length()), 1e-6)

    t1 = knot(p0, p1)
    t2 = t1 + knot(p1, p2)
    t3 = t2 + knot(p2, p3)
    x = t1 + (t2 - t1) * t

    def mix(a: Vec, b: Vec, ta: float, tb: float) -> Vec:
        return a * ((tb - x) / (tb - ta)) + b * ((x - ta) / (tb - ta))

    a1, a2, a3 = mix(p0, p1, 0, t1), mix(p1, p2, t1, t2), mix(p2, p3, t2, t3)
    b1, b2 = mix(a1, a2, 0, t2), mix(a2, a3, t1, t3)
    return mix(b1, b2, t1, t2)


@dataclass(frozen=True, slots=True)
class Offset:
    """Another curve, moved by a fixed amount: a camera keeping its distance from a path."""

    curve: Curve
    by: Vec

    def at(self, u: float) -> Vec:
        return self.curve.at(u) + self.by


@dataclass(frozen=True, slots=True)
class Stretch:
    """Part of another curve, from `start` to `end` (fractions of it), read from 0 to 1."""

    curve: Curve
    start: float
    end: float

    def at(self, u: float) -> Vec:
        return self.curve.at(min(1.0, max(0.0, self.start + (self.end - self.start) * u)))


@dataclass(frozen=True, slots=True)
class Samples:
    """A curve through positions already known per frame (another object's motion)."""

    points: tuple[Vec, ...]

    def at(self, u: float) -> Vec:
        scaled = min(max(u, 0.0), 1.0) * (len(self.points) - 1)
        index = min(int(scaled), len(self.points) - 2) if len(self.points) > 1 else 0
        if len(self.points) == 1:
            return self.points[0]
        return self.points[index].lerp(self.points[index + 1], scaled - index)


@dataclass(frozen=True, slots=True)
class Even:
    """A curve walked at constant speed: equal steps of `u` cover equal distances."""

    curve: Curve
    table: tuple[float, ...]  # cumulative distance at evenly spaced raw u
    total: float

    def at(self, u: float) -> Vec:
        wanted = min(max(u, 0.0), 1.0) * self.total
        steps = len(self.table) - 1
        low, high = 0, steps
        while low < high:
            middle = (low + high) // 2
            if self.table[middle] < wanted:
                low = middle + 1
            else:
                high = middle
        if low == 0:
            return self.curve.at(0.0)
        before, after = self.table[low - 1], self.table[low]
        within = (wanted - before) / (after - before) if after > before else 0.0
        return self.curve.at((low - 1 + within) / steps)


def even(curve: Curve, steps: int = 512) -> Even:
    points = [curve.at(i / steps) for i in range(steps + 1)]
    table = [0.0]
    for a, b in zip(points, points[1:], strict=False):
        table.append(table[-1] + (b - a).length())
    return Even(curve, tuple(table), table[-1])


def length(curve: Curve, steps: int = 512) -> float:
    return even(curve, steps).total


def sample(curve: Curve, amounts: Sequence[float]) -> list[Vec]:
    return [curve.at(u) for u in amounts]


def direction_at(curve: Curve, u: float, step: float = 1e-3) -> Vec:
    """The way a curve is heading at `u`."""
    a, b = curve.at(max(u - step, 0.0)), curve.at(min(u + step, 1.0))
    return (b - a).normalised()


def wobble(seed: int, frames: int, fps: int, amplitude: float, hertz: float = 0.25) -> list[Vec]:
    """A slow, smooth, repeatable drift (the sum of a few sines with seeded phases): a hand
    holding the camera, or air moving a hanging lamp."""
    phases = [((seed * 7919 + k * 104729) % 1000) / 1000 * math.tau for k in range(9)]
    out = []
    for frame in range(frames):
        t = frame / fps
        axes = []
        for axis in range(3):
            total = 0.0
            for k, ratio in enumerate((1.0, 1.7, 2.9)):
                total += math.sin(math.tau * hertz * ratio * t + phases[axis * 3 + k]) / ratio
            axes.append(total * amplitude / 1.9)
        out.append(Vec(*axes))
    return out
