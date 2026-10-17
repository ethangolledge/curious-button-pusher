"""How a person is posed, as rules and joints: a person in a shot is a pose (the joints of
their body, from real recorded motion: `staging/poses.py`), placed where they stand, seated on
the shot's real seat, their hands reaching its real table. The image model draws the person
from these joints (drawn as a skeleton over the layout); no body is rendered.

Plain Python, so all of it is tested without Blender. A pose is written facing −Y, standing on
the floor under the middle of its hips, at `STANDARD_HEIGHT`; placed, it is in the world."""

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content.blender.api import Box, Figure
from content.blender.maths import FRONT, Quat, Vec
from content.blender.sets import SEAT_REACH

# A pose's measures are for someone this tall, and scale with their height.
STANDARD_HEIGHT = 1.8
# The poses a person can be placed in, each held as a stance from recorded motion.
POSES = ("standing", "seated", "walking")
# The joints of a pose: the OpenPose body set the image model reads a skeleton by.
JOINTS = (
    "nose", "neck", "shoulder.R", "elbow.R", "wrist.R", "shoulder.L", "elbow.L", "wrist.L",
    "hip.R", "knee.R", "ankle.R", "hip.L", "knee.L", "ankle.L", "eye.R", "eye.L", "ear.R",
    "ear.L",
)  # fmt: skip
# Figure clips are kept this many frames a second.
RECORDED_FPS = 30
# A person standing at ease, as a pose is written: what a rehearsal (a check without Blender)
# poses everyone as.
STANDING = {
    "nose": (0.0, -0.1, 1.66), "neck": (0.0, 0.0, 1.5),
    "shoulder.R": (-0.19, 0.0, 1.47), "elbow.R": (-0.22, 0.02, 1.18),
    "wrist.R": (-0.23, 0.0, 0.92), "shoulder.L": (0.19, 0.0, 1.47),
    "elbow.L": (0.22, 0.02, 1.18), "wrist.L": (0.23, 0.0, 0.92),
    "hip.R": (-0.1, 0.0, 0.94), "knee.R": (-0.1, -0.02, 0.51), "ankle.R": (-0.1, 0.0, 0.08),
    "hip.L": (0.1, 0.0, 0.94), "knee.L": (0.1, -0.02, 0.51), "ankle.L": (0.1, 0.0, 0.08),
    "eye.R": (-0.035, -0.08, 1.69), "eye.L": (0.035, -0.08, 1.69),
    "ear.R": (-0.075, 0.0, 1.67), "ear.L": (0.075, 0.0, 1.67),
}  # fmt: skip
# How far a seated person's hip joints are above the seat they sit on, and their ankles above
# the floor (metres, at the standard height).
HIP_ABOVE_SEAT, ANKLE_HEIGHT = 0.09, 0.08
# How far a seated person's ankle is in front of their knee (metres, at the standard height).
SHIN_LEAN = 0.06
# Room round a pose's joints taken by the body itself (metres): a person is wider than
# their bones.
FLESH = 0.12


def recording(path: Path) -> list[Figure]:
    """A pose clip's poses, frame by frame (`RECORDED_FPS` a second), as written: facing −Y,
    standing at the origin (`staging/poses.py` keeps them; `blender/poses.py` writes them)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        Figure(dict(zip(JOINTS, (Vec(*point) for point in frame), strict=True)))
        for frame in data["frames"]
    ]


def placed(pose: Figure, at: Vec, turn: Quat, scale: float) -> Figure:
    """A pose as written (facing −Y, standing at the origin, the standard height) stood at
    `at`, turned and scaled to a person's height."""
    return Figure({name: at + turn.rotate(point * scale) for name, point in pose.joints.items()})


def two_bone(root: Vec, middle: Vec, end: Vec, target: Vec, pole: Vec) -> tuple[Vec, Vec]:
    """A limb of two bones (a thigh and shin, an upper arm and forearm) bent so its end reaches
    `target` as nearly as its length allows, its middle joint bending towards `pole`: the new
    middle and end, each bone its own length still."""
    upper, lower = (middle - root).length(), (end - middle).length()
    aim = target - root
    reach = min(max(aim.length(), abs(upper - lower) + 1e-6), upper + lower - 1e-6)
    way = aim.normalised() if aim.length() > 1e-9 else (end - root).normalised()
    cos = (upper * upper + reach * reach - lower * lower) / (2 * upper * reach)
    sin = math.sqrt(max(0.0, 1.0 - cos * cos))
    bend = pole - root
    bend = (bend - way * bend.dot(way)).normalised()
    new_middle = root + way * (upper * cos) + bend * (upper * sin)
    return new_middle, root + way * reach


def seated(pose: Figure, seat: float, floor: float, turn: Quat, scale: float) -> Figure:
    """A placed sitting pose fitted to a seat `seat` metres above the floor: its hips on the
    seat, each shin brought upright under its knee (the foot a little ahead, clear of the
    chair's legs), the ankles above the floor; the thighs keep their way."""
    rise = floor + seat + HIP_ABOVE_SEAT * scale - pose.hips.z
    joints = {name: point + Vec(0.0, 0.0, rise) for name, point in pose.joints.items()}
    ahead = turn.rotate(FRONT) * (SHIN_LEAN * scale)
    for side in ("L", "R"):
        hip, knee = joints[f"hip.{side}"], joints[f"knee.{side}"]
        target = Vec(knee.x, knee.y, floor + ANKLE_HEIGHT * scale) + ahead
        pole = knee + turn.rotate(FRONT)
        joints[f"knee.{side}"], joints[f"ankle.{side}"] = two_bone(
            hip, knee, joints[f"ankle.{side}"], target, pole
        )
    return Figure(joints)


def reached(pose: Figure, side: str, target: Vec, elbow: Vec) -> Figure:
    """One arm of a pose reaching `target` with its wrist, the elbow bending towards `elbow`."""
    shoulder = pose.joints[f"shoulder.{side}"]
    new_elbow, wrist = two_bone(
        shoulder, pose.joints[f"elbow.{side}"], pose.joints[f"wrist.{side}"], target, elbow
    )
    return Figure({**pose.joints, f"elbow.{side}": new_elbow, f"wrist.{side}": wrist})


def local(pose: Figure, at: Vec, turn: Quat) -> Figure:
    """A placed pose in its own terms again: as seen from where it stands, facing −Y."""
    back = Quat(turn.w, -turn.x, -turn.y, -turn.z)
    return Figure({name: back.rotate(point - at) for name, point in pose.joints.items()})


def extent(pose: Figure) -> Box:
    """The room a posed person takes: round their joints, with their flesh."""
    points = list(pose.joints.values())
    low = Vec(*(min(getattr(p, a) for p in points) for a in "xyz"))
    high = Vec(*(max(getattr(p, a) for p in points) for a in "xyz"))
    flesh = Vec(FLESH, FLESH, 0.0)
    # From the soles of the feet (below the ankles) to the top of the head (above the eyes).
    soles = Vec(0.0, 0.0, min(ANKLE_HEIGHT, low.z))
    return Box(low - flesh - soles, high + flesh + Vec(0.0, 0.0, FLESH))


def face(head: Vec, top: Vec, forward: Vec) -> dict[str, Vec]:
    """The face's points (nose, eyes, ears) from the head's joint, the top of the head and
    the way the face looks: what tells the image model which way a head turns."""
    up = (top - head).normalised()
    size = (top - head).length()
    middle = head + up * (size * 0.45)
    look = (forward - up * forward.dot(up)).normalised()
    left = up.cross(look).normalised()
    return {
        "nose": middle + look * (size * 0.55) - up * (size * 0.1),
        "eye.L": middle + look * (size * 0.45) + left * (size * 0.18) + up * (size * 0.08),
        "eye.R": middle + look * (size * 0.45) - left * (size * 0.18) + up * (size * 0.08),
        "ear.L": middle + left * (size * 0.38),
        "ear.R": middle - left * (size * 0.38),
    }


# What a person does with their hands, by pose: where each wrist that moves goes, and where
# what they hold goes. A point is (right, back, up, measured from):
# from the hips (scaled with height); from a table (back from its near edge, up from its top:
# a wrist lying on it a few centimetres up, the hand on the top); or from the floor.
Point = tuple[float, float, float, str]
ACTIVITIES: dict[tuple[str, str], dict[str, Any]] = {
    ("seated", "resting"): {
        "hands": {"L": (0.17, -0.06, 0.05, "table"), "R": (-0.17, -0.06, 0.05, "table")},
    },
    ("seated", "drink"): {
        "hands": {"L": (0.17, -0.06, 0.05, "table"), "R": (-0.12, -0.09, 0.12, "table")},
        "holds": {"drink": (-0.15, -0.17, 0.0, "table")},
    },
    ("seated", "reading"): {
        "hands": {"L": (0.13, -0.08, 0.06, "table"), "R": (-0.13, -0.08, 0.06, "table")},
        "holds": {"document": (0.0, -0.14, 0.0, "table")},
    },
    ("seated", "writing"): {
        "hands": {"L": (0.15, -0.08, 0.05, "table"), "R": (-0.06, -0.11, 0.07, "table")},
        "holds": {"paper": (0.02, -0.16, 0.0, "table")},
    },
    ("seated", "pointing"): {
        "hands": {"L": (0.17, -0.06, 0.05, "table"), "R": (-0.14, -0.42, 0.26, "table")},
    },
    ("seated", "lap"): {
        "hands": {"L": (0.12, -0.24, 0.12, "hips"), "R": (-0.12, -0.24, 0.12, "hips")},
    },
    ("seated", "folded"): {
        "hands": {"L": (-0.13, -0.2, 0.3, "hips"), "R": (0.13, -0.22, 0.33, "hips")},
    },
    ("standing", "drink"): {
        "hands": {"R": (-0.17, -0.2, 0.12, "hips")},
        "holds": {"drink": (-0.17, -0.27, 0.06, "hips")},
    },
    ("standing", "phone"): {
        "hands": {"R": (-0.1, -0.02, 0.66, "hips")},
        "holds": {"phone": (-0.08, -0.06, 0.7, "hips")},
    },
    ("standing", "pockets"): {
        "hands": {"L": (0.19, -0.04, -0.02, "hips"), "R": (-0.19, -0.04, -0.02, "hips")},
    },
    ("standing", "folded"): {
        "hands": {"L": (-0.13, -0.2, 0.3, "hips"), "R": (0.13, -0.22, 0.33, "hips")},
    },
    ("standing", "pointing"): {
        "hands": {"R": (-0.22, -0.55, 0.45, "hips")},
    },
}
# Where an elbow points as an arm reaches (out to the side and back), from the hips.
ELBOW = Vec(0.55, 0.45, -0.1)
# The table a person's hands go to when none is before them (and as the room their pose takes
# is measured): this high, its near edge a seat's reach in front of a seated person's hips.
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
    """Where one hand goes (its wrist, in the world) and which way its elbow points."""

    side: str
    at: Vec
    elbow: Vec


def table_before(box: Box, frame: Frame) -> Table:
    """A table as a person sees it: how far its nearest edge is in front of their hips (the
    corner of its top nearest them, along the way they face), and its top."""
    facing = frame.world(FRONT)
    corners = [Vec(x, y, 0) for x in (box.low.x, box.high.x) for y in (box.low.y, box.high.y)]
    near = min((corner - frame.hips.flat()).dot(facing) for corner in corners)
    return Table(near, box.top)


def where(point: Point, frame: Frame, table: Table | None) -> Vec:
    """A point of an activity, in the world. A table point with no table in front of the
    person is taken from the usual table (`posed_for`)."""
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
    """The usual table: what a person's hands go to when no table is before them."""
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
        out.append(Reach(side, where(point, frame, table), elbow))
    return out


def holds(pose: str, doing: str, frame: Frame, table: Table | None) -> dict[str, Vec]:
    """Where what they hold goes (its base), by name ("drink", "document")."""
    chosen = activity(pose, doing).get("holds", {})
    return {name: where(point, frame, table) for name, point in chosen.items()}
