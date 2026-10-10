"""Shapes props are built from again and again: legs under a top, a drawer front, a handle.
Each prop file then reads as a short description of the thing, not of the geometry."""

from content.blender.api import Role, ShapeKind, Stage, Thing
from content.blender.maths import Vec


def legs(
    stage: Stage, parent: Thing, name: str, *, width: float, depth: float, height: float,
    thickness: float = 0.045, inset: float = 0.04, role: Role = "wood", round_legs: bool = False,
) -> None:  # fmt: skip
    """Four legs under a top `width` by `depth`, `height` tall."""
    x, y = width / 2 - inset - thickness / 2, depth / 2 - inset - thickness / 2
    kind: ShapeKind = "cylinder" if round_legs else "box"
    for index, (sx, sy) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
        stage.shape(
            kind, Vec(thickness, thickness, height), Vec(sx * x, sy * y, 0),
            role=role, name=f"{name}.leg_{index}", parent=parent,
        )  # fmt: skip


def slab(
    stage: Stage, parent: Thing, name: str, size: Vec, at: Vec, role: Role, bevel: float = 0.004
) -> Thing:
    """A board or block with softened edges, which catch the light as real ones do."""
    return stage.shape("box", size, at, role=role, name=name, parent=parent, bevel=bevel)


def drawers(
    stage: Stage, parent: Thing, name: str, *, at: Vec, width: float, height: float,
    count: int, facing_y: float, role: Role = "wood",
) -> None:  # fmt: skip
    """A column of drawer fronts with handles, on the face at `facing_y` (−1 front, 1 back)."""
    gap = 0.012
    each = (height - gap * (count + 1)) / count
    for index in range(count):
        bottom = at.z + gap + index * (each + gap)
        front = Vec(at.x, at.y + facing_y * 0.01, bottom)
        slab(stage, parent, f"{name}.drawer_{index}", Vec(width - 2 * gap, 0.02, each), front, role)
        stage.shape(
            "box", Vec(min(0.12, width / 3), 0.02, 0.015),
            Vec(at.x, at.y + facing_y * 0.03, bottom + each * 0.6),
            role="metal", name=f"{name}.handle_{index}", parent=parent,
        )  # fmt: skip
