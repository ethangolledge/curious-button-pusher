"""A stylised figurine made of simple solids, standing or seated: the shape every made-in-code
person shares. Simple on purpose: under the channel's look it reads as a drawn or carved
figure, never a failed attempt at a real one.

Seated, it fits the engine's chair (seat 0.45 m high) and rests its forearms just above a
table or desk (about 0.75 m), touching neither."""

from dataclasses import dataclass, replace
from typing import Literal

from content.blender.api import Role, ShapeKind, Stage, Thing
from content.blender.maths import Vec

# Seated: the thighs' centre line, just clear of a 0.45 m seat; forearms clear of a 0.76 m top.
SEATED_HIP, FOREARMS = 0.535, 0.82
STANDING_HIP = 0.92
# A cylinder turned like this lies forward (towards −Y) from where it is put.
FORWARD = (90.0, 0.0, 0.0)


@dataclass(frozen=True, slots=True)
class Piece:
    kind: ShapeKind
    size: tuple[float, float, float]
    at: tuple[float, float, float]  # the centre of its base; a limb's is on the left (−x)
    role: Role
    turn: tuple[float, float, float] = (0, 0, 0)
    bevel: float = 0.0


def _trunk(hip: float) -> dict[str, Piece]:
    """Hips, torso, neck and head: the same in every pose but for their height."""
    shoulder = hip + 0.62
    return {
        "hips": Piece("box", (0.36, 0.22, 0.16), (0, 0, hip - 0.04), "fabric", bevel=0.05),
        "torso": Piece("box", (0.42, 0.24, 0.56), (0, 0, hip + 0.1), "fabric", bevel=0.07),
        "neck": Piece("cylinder", (0.1, 0.1, 0.1), (0, 0, shoulder - 0.02), "skin"),
        "head": Piece("sphere", (0.2, 0.23, 0.25), (0, -0.01, shoulder + 0.06), "skin"),
        "hair": Piece("sphere", (0.21, 0.23, 0.13), (0, 0.015, shoulder + 0.2), "hair"),
    }


_STAND_SHOULDER = STANDING_HIP + 0.62
_SIT_SHOULDER = SEATED_HIP + 0.62
# Each pose's limbs, the left one of each pair: the right mirrors it.
LIMBS: dict[str, dict[str, Piece]] = {
    "standing": {
        "leg": Piece("cylinder", (0.14, 0.14, STANDING_HIP - 0.05), (-0.1, 0, 0.05), "fabric"),
        "shoe": Piece("box", (0.11, 0.26, 0.07), (-0.1, -0.05, 0), "leather", bevel=0.02),
        "arm": Piece(
            "cylinder", (0.1, 0.1, 0.62), (-0.26, 0, _STAND_SHOULDER - 0.62), "fabric", (0, -4, 0)
        ),
        "hand": Piece("sphere", (0.09, 0.07, 0.11), (-0.28, 0, _STAND_SHOULDER - 0.72), "skin"),
    },
    "seated": {
        # Thighs forward, shins down to the floor, forearms forward as if on a table.
        "thigh": Piece("cylinder", (0.15, 0.15, 0.45), (-0.1, 0, SEATED_HIP), "fabric", FORWARD),
        "shin": Piece("cylinder", (0.12, 0.12, SEATED_HIP - 0.05), (-0.1, -0.42, 0.05), "fabric"),
        "shoe": Piece("box", (0.11, 0.26, 0.07), (-0.1, -0.48, 0), "leather", bevel=0.02),
        "upper_arm": Piece(
            "cylinder", (0.1, 0.1, _SIT_SHOULDER - FOREARMS), (-0.25, 0, FOREARMS), "fabric"
        ),
        "forearm": Piece("cylinder", (0.09, 0.09, 0.32), (-0.22, 0, FOREARMS), "fabric", FORWARD),
        "hand": Piece("sphere", (0.09, 0.1, 0.07), (-0.22, -0.34, FOREARMS - 0.035), "skin"),
    },
}
TRUNKS = {"standing": _trunk(STANDING_HIP), "seated": _trunk(SEATED_HIP)}


def figurine(stage: Stage, name: str, pose: Literal["standing", "seated"]) -> Thing:
    body = stage.group(name)
    pieces = dict(TRUNKS[pose])
    for limb, left in LIMBS[pose].items():
        x, y, z = left.at
        a, b, c = left.turn
        # Numbered 0 (left) and 2 (right), as the props' parts are.
        pieces[f"{limb}_0"] = left
        pieces[f"{limb}_2"] = replace(left, at=(-x, y, z), turn=(a, -b, -c))
    for part, p in pieces.items():
        stage.shape(
            p.kind, Vec(*p.size), Vec(*p.at), role=p.role, name=f"{name}.{part}",
            turn=Vec(*p.turn), parent=body, bevel=p.bevel,
        )  # fmt: skip
    return body
