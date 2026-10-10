"""What moving things share: finding what a name refers to, and travelling along a path,
facing the way of travel and leaning into bends. Driving, flying, sliding and walking are
all travel with something added."""

from collections.abc import Sequence

from content.blender.api import Box, Pose, Stage
from content.blender.maths import (
    FRONT,
    Curve,
    Quat,
    Spline,
    Vec,
    degrees_round,
    direction_at,
    even,
    heading_rotation,
    limit_turn,
    progress,
)

# The fastest anything turns, in degrees a frame, unless a block says otherwise; faster reads
# as a snap.
MAX_TURN = 12.0


def where(stage: Stage, name: str) -> Box:
    """The extent of an actor, or a small box around a layout's mark."""
    try:
        return stage.bounds(stage.actor(name))
    except KeyError:
        mark = stage.find_mark(name)
        half = Vec(0.15, 0.15, 0.15)
        return Box(mark.at - half, mark.at + half)


def front(stage: Stage, name: str) -> float:
    """Which way an actor or mark faces, as degrees round from −Y (`maths.Arc`'s convention):
    camera angles are measured from a subject's front, whichever way it is turned."""
    try:
        facing = stage.poses(stage.actor(name))[0].rotation.rotate(FRONT)
    except KeyError:
        facing = stage.find_mark(name).facing
    return degrees_round(facing)


def route(stage: Stage, name: str) -> Curve:
    """A layout's named path, as a smooth curve walked at constant speed."""
    return even(Spline(tuple(stage.find_path(name))))


def travel(
    curve: Curve,
    frames: int,
    *,
    ease: str = "in_out",
    start: float = 0.0,
    end: float = 1.0,
    bank: float = 0.0,
    upright: bool = True,
    max_turn: float = MAX_TURN,
) -> list[Pose]:
    """A pose per frame along `curve`, facing the way of travel. `bank` (0 to 1) leans into
    bends, as a car body rolls or a plane banks; `upright` keeps the nose level, otherwise it
    pitches with the path (a plane climbing)."""
    amounts = progress(frames, ease, start, end)
    points = [curve.at(u) for u in amounts]
    headings = [direction_at(curve, u) for u in amounts]
    rotations: list[Quat] = []
    for index, heading in enumerate(headings):
        lean = bank * _bend(headings, index) * 35.0
        rotations.append(heading_rotation(heading, lean, level=upright))
    limited = limit_turn(rotations, max_turn)
    return [
        Pose(index + 1, at, rotation)
        for index, (at, rotation) in enumerate(zip(points, limited, strict=True))
    ]


def _bend(headings: Sequence[Vec], index: int) -> float:
    """How sharply the path turns here, from −1 (hard left) to 1 (hard right)."""
    before = headings[max(index - 2, 0)].flat().normalised()
    after = headings[min(index + 2, len(headings) - 1)].flat().normalised()
    turn = before.cross(after).z  # positive: turning left
    return max(-1.0, min(1.0, -turn * 8.0))


def distances(poses: Sequence[Pose]) -> list[float]:
    """How far a thing has travelled by each frame."""
    out = [0.0]
    for a, b in zip(poses, poses[1:], strict=False):
        out.append(out[-1] + (b.at - a.at).length())
    return out
