"""What every camera move shares: how far to stand to frame something, and turning a path for
the camera and a path for what it looks at into a shot. Each move is a choice of those two
paths; nothing else differs between a push-in, an orbit, a pan or a fly-through."""

import math
from dataclasses import dataclass
from typing import Literal

from content.blender.api import Box, Mark, Pose, Stage
from content.blender.maths import Arc, Curve, Vec, look_rotation, progress, wobble

Framing = Literal["wide", "medium", "close", "detail"]
# The mark a move leaves for what it films, read by the check before rendering.
SUBJECT = "camera_subject"
# How much of the frame the subject fills at each framing.
FILL: dict[str, float] = {"wide": 0.3, "medium": 0.55, "close": 0.85, "detail": 1.4}
SENSOR_MM = 36.0  # Blender's default sensor, fitted to the frame's longer side


def field_of_view(lens_mm: float, aspect: float) -> tuple[float, float]:
    """The horizontal and vertical angles (radians) a lens sees."""
    wide = 2 * math.atan(SENSOR_MM / 2 / lens_mm)
    if aspect >= 1:
        return wide, 2 * math.atan(math.tan(wide / 2) / aspect)
    return 2 * math.atan(math.tan(wide / 2) * aspect), wide


def distance_to_frame(box: Box, lens_mm: float, aspect: float, framing: str) -> float:
    """How far from a subject's centre the camera stands to frame it so."""
    across, up = field_of_view(lens_mm, aspect)
    fill = FILL[framing]
    size = box.size
    # The framing sets how much of the frame's height the subject fills; across, it always
    # fits (bar a margin) unless the framing is closer than that.
    half_height = size.z / 2 / fill
    half_width = max(size.x, size.y) / 2 / max(fill, 0.9)
    return (
        max(half_height / math.tan(up / 2), half_width / math.tan(across / 2))
        + max(size.x, size.y) / 2
    )


@dataclass(frozen=True, slots=True)
class Shot:
    """A camera move: where the camera goes, what it looks at, and its lens."""

    position: Curve
    target: Curve
    lens_from: float = 35.0
    lens_to: float = 35.0
    # The lens follows the distance instead, so the subject stays one size while what is
    # behind it stretches or shrinks (the dolly zoom).
    hold_size: bool = False

    def lens(self, u: float) -> float:
        if not self.hold_size:
            return self.lens_from + (self.lens_to - self.lens_from) * u
        start = (self.target.at(0.0) - self.position.at(0.0)).length()
        now = (self.target.at(u) - self.position.at(u)).length()
        return max(8.0, min(300.0, self.lens_from * now / max(start, 1e-6)))


def film(
    stage: Stage,
    shot: Shot,
    *,
    ease: str = "in_out",
    start: float = 0.0,
    end: float = 1.0,
    drift: float = 0.0,
    roll_degrees: float = 0.0,
    watching: Box | None = None,
) -> None:
    """Animate the camera along a shot. `drift` adds a slow handheld sway, in metres.
    `watching` is what the shot is of; the check before rendering makes sure nothing blocks
    the view of it."""
    camera = stage.camera()
    if watching is not None:
        stage.mark(Mark(SUBJECT, watching.centre, Vec(0, -1, 0), watching))
    walls = inside(stage)
    amounts = progress(stage.frames, ease, start, end)
    sway = wobble(stage.random("drift").randrange(10**6), stage.frames, stage.fps, drift)
    poses = []
    for index, u in enumerate(amounts):
        # Whatever a move asks, the camera never leaves the set, nor enters what it films.
        at = keep_inside(walls, shot.position.at(u) + (sway[index] if drift else Vec()))
        if watching is not None:
            at = keep_away(watching, at)
        look = shot.target.at(u) - at
        poses.append(Pose(index + 1, at, look_rotation(look, roll_degrees)))
    stage.animate(camera, poses)
    stage.animate_value(camera, "lens", [(i + 1, shot.lens(u)) for i, u in enumerate(amounts)])


@dataclass(frozen=True, slots=True)
class Stand:
    """Where the camera stands to frame a subject: `degrees` round from −Y, `radius` across
    the ground from the subject's centre, `height` above it, and the lens that frames it from
    there."""

    position: Vec
    degrees: float
    radius: float
    height: float
    lens: float


# How close the camera may come to a wall, and the widest lens it may use to keep a framing.
MARGIN = 0.25
WIDEST = 20.0


def around(
    stage: Stage,
    box: Box,
    framing: str,
    lens_mm: float,
    degrees: float,
    elevation: float,
    *,
    sweep: float = 0.0,
) -> Stand:
    """Stand back far enough to frame `box`, `degrees` round from −Y and `elevation` degrees
    above it. Inside a set, the camera never stands beyond its walls, anywhere along an arc of
    `sweep` degrees: where it cannot step back far enough, the lens widens instead."""
    needed = distance_to_frame(box, lens_mm, stage.aspect, framing)
    distance = needed
    walls = inside(stage)
    if walls is not None:
        steps = max(1, int(abs(sweep) / 10))
        for step in range(steps + 1):
            angle = math.radians(degrees + sweep * step / steps)
            rise = math.radians(elevation)
            direction = Vec(
                math.sin(angle) * math.cos(rise), -math.cos(angle) * math.cos(rise), math.sin(rise)
            )
            distance = min(distance, reach(walls, box.centre, direction))
    lens = max(WIDEST, lens_mm * distance / needed)
    radius = distance * math.cos(math.radians(elevation))
    height = distance * math.sin(math.radians(elevation))
    position = Arc(box.centre, radius, degrees, 0.0, height, height).at(0.0)
    return Stand(position, degrees, radius, height, lens)


def inside(stage: Stage) -> Box | None:
    """The space the camera must stay in, if the layout is enclosed (its `interior` mark),
    kept a little away from the walls."""
    try:
        space = stage.find_mark("interior").surface
    except KeyError:
        return None
    if space is None:
        return None
    gap = Vec(MARGIN, MARGIN, MARGIN)
    return Box(space.low + gap, space.high - gap)


def reach(space: Box, start: Vec, direction: Vec) -> float:
    """How far from `start` along `direction` before leaving `space`."""
    farthest = math.inf
    for axis in ("x", "y", "z"):
        towards = getattr(direction, axis)
        if abs(towards) < 1e-9:
            continue
        wall = getattr(space.high if towards > 0 else space.low, axis)
        farthest = min(farthest, max(0.0, (wall - getattr(start, axis)) / towards))
    return farthest


# The nearest the camera comes to what it films, as a share of the subject's own radius.
NEAREST = 1.3


def keep_away(subject: Box, point: Vec) -> Vec:
    """A camera position pushed back out of a subject, along its line to the centre."""
    offset = point - subject.centre
    nearest = subject.radius * NEAREST
    if offset.length() >= nearest:
        return point
    return (
        subject.centre
        + (offset.normalised() if offset.length() > 1e-6 else Vec(0, -1, 0)) * nearest
    )


def keep_inside(space: Box | None, point: Vec) -> Vec:
    if space is None:
        return point
    return Vec(
        min(max(point.x, space.low.x), space.high.x),
        min(max(point.y, space.low.y), space.high.y),
        min(max(point.z, space.low.z), space.high.z),
    )
