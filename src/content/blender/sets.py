"""The parts sets are built from, shared by every layout: a room's shell, a window, a floor to
the horizon. A layout chooses and dresses them; it never repeats them.

A room is centred on the origin. Its back wall is at +Y (where a window usually is), the
camera usually stands towards −Y, and the floor is at z = 0."""

from dataclasses import dataclass

from content.blender.api import Box, Mark, Role, Stage, Thing
from content.blender.maths import FRONT, UP, Vec, axis_angle

WALL = 0.12  # wall thickness
# How far a seat's middle stands from the edge of the table or desk it faces: room for whoever
# sits there, their hips over the seat and their lap and hands clear of the edge.
SEAT_REACH = 0.36


@dataclass(frozen=True, slots=True)
class Room:
    width: float
    depth: float
    height: float

    @property
    def back(self) -> float:
        return self.depth / 2


def room(
    stage: Stage,
    width: float,
    depth: float,
    height: float,
    *,
    window: bool = True,
    blinds: bool = False,
    door: bool = False,
    ceiling: bool = True,
    wall: Role = "wall",
    floor: Role = "floor",
) -> Room:
    shell = stage.group("room")
    stage.shape(
        "box",
        Vec(width + 2 * WALL, depth + 2 * WALL, WALL),
        Vec(0, 0, -WALL),
        role=floor,
        name="floor",
        parent=shell,
    )
    if ceiling:
        stage.shape(
            "box",
            Vec(width + 2 * WALL, depth + 2 * WALL, WALL),
            Vec(0, 0, height),
            role="ceiling",
            name="ceiling",
            parent=shell,
        )
    half_w, half_d = width / 2, depth / 2
    # Side and front walls are plain; the back wall may hold a window.
    stage.shape(
        "box",
        Vec(WALL, depth, height),
        Vec(-half_w - WALL / 2, 0, 0),
        role=wall,
        name="wall_left",
        parent=shell,
    )
    if door:
        _wall_with_hole(
            stage,
            shell,
            "wall_right",
            Vec(half_w + WALL / 2, 0, 0),
            depth,
            height,
            hole_width=1.0,
            hole_bottom=0.0,
            hole_top=2.1,
            along_y=True,
            role=wall,
        )
        stage.mark(Mark("door", Vec(half_w, 0, 0), Vec(-1, 0, 0)))
    else:
        stage.shape(
            "box",
            Vec(WALL, depth, height),
            Vec(half_w + WALL / 2, 0, 0),
            role=wall,
            name="wall_right",
            parent=shell,
        )
    stage.shape(
        "box",
        Vec(width, WALL, height),
        Vec(0, -half_d - WALL / 2, 0),
        role=wall,
        name="wall_front",
        parent=shell,
    )
    if window:
        sill, top = 0.9, min(height - 0.35, 2.4)
        window_width = min(width * 0.45, 2.0)
        _wall_with_hole(
            stage,
            shell,
            "wall_back",
            Vec(0, half_d + WALL / 2, 0),
            width,
            height,
            hole_width=window_width,
            hole_bottom=sill,
            hole_top=top,
            along_y=False,
            role=wall,
        )
        stage.shape(
            "box",
            Vec(window_width, 0.01, top - sill),
            Vec(0, half_d + WALL / 2, sill),
            role="glass",
            name="window_glass",
            parent=shell,
        )
        stage.shape(
            "box",
            Vec(window_width + 0.1, 0.25, 0.04),
            Vec(0, half_d - 0.08, sill - 0.04),
            role="paint",
            name="window_sill",
            parent=shell,
        )
        if blinds:
            slats = int((top - sill) / 0.06)
            for index in range(slats):
                stage.shape(
                    "box",
                    Vec(window_width, 0.045, 0.004),
                    Vec(0, half_d - 0.04, top - 0.03 - index * 0.06),
                    role="plastic",
                    name=f"blind_{index}",
                    turn=Vec(35, 0, 0),
                    parent=shell,
                )
        stage.mark(Mark("window", Vec(0, half_d, sill), FRONT))
    else:
        stage.shape(
            "box",
            Vec(width, WALL, height),
            Vec(0, half_d + WALL / 2, 0),
            role=wall,
            name="wall_back",
            parent=shell,
        )
    stage.mark(Mark("centre", Vec(), FRONT))
    # The space inside the walls: the camera stays in it.
    stage.mark(
        Mark("interior", Vec(), FRONT, Box(Vec(-half_w, -half_d, 0), Vec(half_w, half_d, height)))
    )
    stage.mark(Mark("back_wall", Vec(0, half_d - 0.3, 0), FRONT))
    stage.mark(Mark("ceiling_centre", Vec(0, 0, height), FRONT))
    stage.path("across", [Vec(-half_w + 0.6, -0.4, 0), Vec(0, 0.2, 0), Vec(half_w - 0.6, -0.4, 0)])
    return Room(width, depth, height)


def _wall_with_hole(
    stage: Stage, parent: Thing, name: str, centre: Vec, length: float, height: float, *,
    hole_width: float, hole_bottom: float, hole_top: float, along_y: bool, role: Role,
) -> None:  # fmt: skip
    """A wall in four pieces around a rectangular opening at its middle."""
    side = (length - hole_width) / 2

    def piece(part: str, offset: float, size_along: float, bottom: float, top: float) -> None:
        size = (
            Vec(WALL, size_along, top - bottom) if along_y else Vec(size_along, WALL, top - bottom)
        )
        shift = Vec(0, offset, bottom) if along_y else Vec(offset, 0, bottom)
        stage.shape("box", size, centre + shift, role=role, name=f"{name}_{part}", parent=parent)

    piece("left", -(hole_width + side) / 2, side, 0, height)
    piece("right", (hole_width + side) / 2, side, 0, height)
    if hole_bottom > 0:
        piece("below", 0, hole_width, 0, hole_bottom)
    piece("above", 0, hole_width, hole_top, height)


def ground(stage: Stage, size: float = 400.0, role: Role = "ground") -> None:
    """A floor running to the horizon."""
    stage.shape("plane", Vec(size, size, 0), Vec(), role=role, name="ground")


def resting_on(mark: Mark) -> Vec:
    """Where something stands on a mark: on its surface if it has one, else on the mark."""
    return Vec(mark.at.x, mark.at.y, mark.surface.top if mark.surface else mark.at.z)


def stand(stage: Stage, thing: Thing, mark: Mark, *, facing: Vec | None = None) -> None:
    """Put a thing on a mark, facing the mark's way unless told otherwise."""
    stage.place(thing, resting_on(mark), facing=facing or mark.facing)


def moved(mark: Mark, *, turn: float = 0.0, across: float = 0.0, along: float = 0.0) -> Mark:
    """A mark turned `turn` degrees and moved `across` metres to its right and `along` metres
    behind it (as it faces): where an actor stands when it is told to stand beside a mark."""
    facing = axis_angle(UP, turn).rotate(mark.facing).normalised()
    right = Vec(facing.y, -facing.x, 0)
    return Mark(mark.name, mark.at + right * across - facing * along, facing, mark.surface)


def surface_mark(name: str, box: Box, facing: Vec = FRONT) -> Mark:
    """A mark on top of something, in the middle, that props can be stood on."""
    return Mark(name, Vec(box.centre.x, box.centre.y, box.top), facing, box)
