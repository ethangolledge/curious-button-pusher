"""How a person's body is posed, as rules: where each limb points in each pose, where the
hands go for what they are doing, and how the fingers close. The same rules pose everyone,
made or placed: `rigging.py` turns them into bones inside Blender, when a person is made
(to measure the room each pose takes) and when a shot places them (on its real furniture).

Plain Python, so the arithmetic is tested without Blender. Directions and points are in the
world: a person facing −Y is posed as written; one turned is posed turned (`Frame.turn`)."""

from dataclasses import dataclass
from typing import Any

from content.blender.api import Box
from content.blender.maths import FRONT, Quat, Vec
from content.blender.sets import SEAT_REACH

# A person's measures below are for someone this tall, and scale with their height.
STANDARD_HEIGHT = 1.8
# Where each limb points in each pose (x right, y back, z up, for a person facing −Y), from
# the hips out; each pair is the left side's, mirrored for the right.
POSES: dict[str, dict[str, tuple[float, float, float]]] = {
    "standing": {
        "upperarm01": (0.18, 0.0, -1.0), "upperarm02": (0.12, 0.02, -1.0),
        "lowerarm01": (0.05, -0.12, -1.0), "lowerarm02": (0.04, -0.15, -1.0),
    },
    "seated": {
        "upperleg01": (0.08, -1.0, -0.1), "upperleg02": (0.06, -1.0, 0.0),
        "lowerleg01": (0.0, -0.08, -1.0), "lowerleg02": (0.0, -0.05, -1.0),
        "upperarm01": (0.15, -0.35, -1.0), "upperarm02": (0.1, -0.4, -1.0),
        "lowerarm01": (-0.15, -1.0, -0.05), "lowerarm02": (-0.15, -1.0, -0.05),
    },
    "walking": {
        "upperleg01": (0.05, -0.35, -1.0), "upperleg02": (0.04, -0.35, -1.0),
        "lowerleg01": (0.0, 0.05, -1.0), "lowerleg02": (0.0, 0.05, -1.0),
        "upperarm01": (0.15, 0.3, -1.0), "upperarm02": (0.1, 0.3, -1.0),
        "lowerarm01": (0.05, 0.05, -1.0), "lowerarm02": (0.05, 0.0, -1.0),
    },
}  # fmt: skip
# Mid-stride the right side does the opposite.
OPPOSED = {"walking"}
# What a person does with their hands, by pose: where each wrist that moves goes, how its
# fingers close, and where what they hold goes. A point is (right, back, up, measured from):
# from the hips (scaled with height); from a table (back from its near edge, up from its top:
# a wrist lying on it about 5 cm up, the hand then lifted until it rests on the top, never in
# it); or from the floor.
Point = tuple[float, float, float, str]
ACTIVITIES: dict[tuple[str, str], dict[str, Any]] = {
    ("seated", "resting"): {
        "hands": {"L": (0.17, -0.06, 0.05, "table"), "R": (-0.17, -0.06, 0.05, "table")},
        "fingers": {"L": "flat", "R": "flat"},
    },
    ("seated", "drink"): {
        "hands": {"L": (0.17, -0.06, 0.05, "table"), "R": (-0.12, -0.09, 0.12, "table")},
        "fingers": {"L": "flat", "R": "hold"},
        "holds": {"drink": (-0.15, -0.17, 0.0, "table")},
    },
    ("seated", "reading"): {
        "hands": {"L": (0.13, -0.08, 0.06, "table"), "R": (-0.13, -0.08, 0.06, "table")},
        "fingers": {"L": "hold", "R": "hold"},
        "holds": {"document": (0.0, -0.14, 0.0, "table")},
    },
    ("seated", "writing"): {
        "hands": {"L": (0.15, -0.08, 0.05, "table"), "R": (-0.06, -0.11, 0.07, "table")},
        "fingers": {"L": "flat", "R": "hold"},
        "holds": {"paper": (0.02, -0.16, 0.0, "table")},
    },
    ("seated", "pointing"): {
        "hands": {"L": (0.17, -0.06, 0.05, "table"), "R": (-0.14, -0.42, 0.26, "table")},
        "fingers": {"L": "flat", "R": "point"},
    },
    ("seated", "lap"): {
        "hands": {"L": (0.12, -0.24, 0.12, "hips"), "R": (-0.12, -0.24, 0.12, "hips")},
        "fingers": {"L": "rest", "R": "rest"},
    },
    ("seated", "folded"): {
        "hands": {"L": (-0.13, -0.2, 0.3, "hips"), "R": (0.13, -0.22, 0.33, "hips")},
        "fingers": {"L": "rest", "R": "rest"},
    },
    ("standing", "drink"): {
        "hands": {"R": (-0.17, -0.2, 0.12, "hips")},
        "fingers": {"R": "hold"},
        "holds": {"drink": (-0.17, -0.27, 0.06, "hips")},
    },
    ("standing", "phone"): {
        "hands": {"R": (-0.1, -0.02, 0.66, "hips")},
        "fingers": {"R": "hold"},
        "holds": {"phone": (-0.08, -0.06, 0.7, "hips")},
    },
    ("standing", "pockets"): {
        "hands": {"L": (0.19, -0.04, -0.02, "hips"), "R": (-0.19, -0.04, -0.02, "hips")},
        "fingers": {"L": "rest", "R": "rest"},
    },
    ("standing", "folded"): {
        "hands": {"L": (-0.13, -0.2, 0.3, "hips"), "R": (0.13, -0.22, 0.33, "hips")},
        "fingers": {"L": "rest", "R": "rest"},
    },
    ("standing", "pointing"): {
        "hands": {"R": (-0.22, -0.55, 0.45, "hips")},
        "fingers": {"R": "point"},
    },
}
# Which way a hand lying on a table points: forward, tipped a little down to the fingertips.
RESTING_HAND = Vec(0.0, -1.0, -0.15)
# Each grip: how far each finger joint closes (degrees: the thumb, then the four fingers), and
# how far the fingers are drawn together from the made hand's spread (0 to 1). A hand lying
# on something is relaxed (fingers together, a little curled), never splayed flat.
GRIPS = {
    "flat": (5.0, 8.0, 0.8), "rest": (15.0, 35.0, 0.7), "hold": (30.0, 70.0, 0.9),
    "point": (40.0, 80.0, 0.5),
}  # fmt: skip
# Where an elbow points as an arm reaches (out to the side and back), and a knee as a leg
# bends (forward, a little out), from the hips.
ELBOW = Vec(0.55, 0.45, -0.1)
KNEE = Vec(0.1, -0.8, 0.0)
# The table a person is posed for when made (to measure the room each pose takes): this high,
# its near edge a seat's reach in front of a seated person's hips (`sets.SEAT_REACH`).
TABLE_HEIGHT = 0.75


@dataclass(frozen=True, slots=True)
class Frame:
    """Where a person is: their hips, the floor under them, which way they are turned (from
    facing −Y), and how tall they are against `STANDARD_HEIGHT`."""

    hips: Vec
    floor: float
    turn: Quat
    scale: float = 1.0

    def world(self, way: Vec) -> Vec:
        """A direction in the person's own terms, in the world."""
        return self.turn.rotate(way)


@dataclass(frozen=True, slots=True)
class Table:
    """The table a person's hands are on: how far its near edge is in front of their hips,
    and how high its top is."""

    near: float
    top: float


@dataclass(frozen=True, slots=True)
class Reach:
    """Where one hand goes (its wrist, in the world), which way its elbow points, how its
    fingers close, and, for a hand lying on a surface, the way it lies along it and how high
    the surface's top is (the hand rests on it, never in it)."""

    side: str
    at: Vec
    elbow: Vec
    grip: str
    lying: Vec | None = None
    surface: float = 0.0


def ways(pose: str, frame: Frame) -> dict[str, Vec]:
    """Each bone the pose sets (`upperarm01.L`), and the way it points in the world."""
    out = {}
    for limb, (x, y, z) in POSES[pose].items():
        for side, sign in (("L", 1), ("R", -1)):
            back = -y if pose in OPPOSED and side == "R" else y
            out[f"{limb}.{side}"] = frame.world(Vec(x * sign, back, z))
    return out


def knee(frame: Frame, side: str) -> Vec:
    """Where a bending leg's knee points at, in the world."""
    sign = 1 if side == "L" else -1
    return frame.hips + frame.world(Vec(KNEE.x * sign, KNEE.y, KNEE.z)) * frame.scale


def table_before(box: Box, frame: Frame) -> Table:
    """A table as a person sees it: how far its nearest edge is in front of their hips (the
    corner of its top nearest them, along the way they face), and its top."""
    facing = frame.world(FRONT)
    corners = [Vec(x, y, 0) for x in (box.low.x, box.high.x) for y in (box.low.y, box.high.y)]
    near = min((corner - frame.hips.flat()).dot(facing) for corner in corners)
    return Table(near, box.top)


def where(point: Point, frame: Frame, table: Table | None) -> Vec:
    """A point of an activity, in the world. A table point with no table in front of the
    person is taken from the table they are posed for when made."""
    x, y, z, ref = point
    s = frame.scale
    if ref == "table":
        table = table or posed_for(frame)
        local, up = Vec(x * s, y - table.near, 0.0), table.top + z
    elif ref == "hips":
        local, up = Vec(x * s, y * s, 0.0), frame.hips.z + z * s
    else:
        local, up = Vec(x * s, y * s, 0.0), frame.floor + z
    flat = frame.world(local)
    return Vec(frame.hips.x + flat.x, frame.hips.y + flat.y, up)


def posed_for(frame: Frame) -> Table:
    """The table a person is posed for when made, or when no table is before them."""
    return Table(SEAT_REACH, frame.floor + TABLE_HEIGHT)


def activity(pose: str, doing: str) -> dict[str, Any]:
    """What a person in this pose does with their hands: nothing, if it does not suit it."""
    return ACTIVITIES.get((pose, doing), {})


def reaches(pose: str, doing: str, frame: Frame, table: Table | None) -> list[Reach]:
    """Where each hand that moves goes, for what they are doing."""
    chosen = activity(pose, doing)
    out = []
    for side, point in chosen.get("hands", {}).items():
        sign = 1 if side == "L" else -1
        elbow = frame.hips + frame.world(Vec(ELBOW.x * sign, ELBOW.y, ELBOW.z)) * frame.scale
        at = where(point, frame, table)
        grip = chosen["fingers"][side]
        if point[3] == "table":
            top = (table or posed_for(frame)).top
            out.append(Reach(side, at, elbow, grip, frame.world(RESTING_HAND), top))
        else:
            out.append(Reach(side, at, elbow, grip))
    return out


def holds(pose: str, doing: str, frame: Frame, table: Table | None) -> dict[str, Vec]:
    """Where what they hold goes (its base), by name ("drink", "document")."""
    chosen = activity(pose, doing).get("holds", {})
    return {name: where(point, frame, table) for name, point in chosen.items()}
