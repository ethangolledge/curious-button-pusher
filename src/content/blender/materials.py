"""What each surface role looks like in the real world, and the role an imported model's own
surface is nearest to. A model made elsewhere arrives with its own colours; matching each of
its surfaces to a role (a pale one to paper, a tan one to leather, a shiny one to metal) lets
every look draw it its own way while it keeps its light and dark parts. A channel can always
say otherwise for a model (its library entry's `paint`)."""

import math
from typing import get_args

from content.blender.api import Role

# Each role's everyday colour (sRGB hex): the plain look's colours, and what an imported
# surface is compared with.
REFERENCE: dict[str, str] = {
    "wall": "#b9b2a6", "floor": "#6b5a48", "ceiling": "#d6d1c8", "ground": "#5d6150",
    "road": "#3b3c3e", "wood": "#8a6440", "dark_wood": "#4a3121", "metal": "#9a9c9f",
    "glass": "#c9d7dc", "paper": "#e8e2d3", "card": "#c7b796", "fabric": "#5b5f6b",
    "leather": "#5a3624", "plastic": "#2f3134", "stone": "#8d8a83", "brick": "#7d4a3a",
    "concrete": "#8f8d88", "money": "#a9b49a", "foliage": "#3f5a35", "rubber": "#1c1c1d",
    "screen": "#9fc4d9", "lamp_shade": "#d9c7a0", "bulb": "#fff2d6", "paint": "#7a7f86",
    "skin": "#c79a7e", "hair": "#2b2018",
}  # fmt: skip
ROLES: tuple[Role, ...] = get_args(Role)
# The roles a solid thing can be matched to by its colour. A set's surfaces (walls, floors),
# what glows, and what only a material's other properties say (metal, glass) are left out.
BY_COLOUR: tuple[Role, ...] = (
    "wood", "dark_wood", "paper", "card", "fabric", "leather", "plastic", "stone", "brick",
    "concrete", "foliage", "rubber", "paint", "skin", "hair",
)  # fmt: skip


def nearest_role(
    colour: tuple[float, float, float], *, metallic: float = 0.0, transmission: float = 0.0
) -> Role:
    """The role a surface is most like: glass if light passes through it, metal if it is
    metallic, otherwise the role whose everyday colour is nearest (`colour` in linear light,
    compared as the eye sees it)."""
    if transmission > 0.5:
        return "glass"
    if metallic > 0.5:
        return "metal"
    seen = _oklab(colour)
    return min(BY_COLOUR, key=lambda role: math.dist(seen, _oklab(linear(REFERENCE[role]))))


def linear(colour: str) -> tuple[float, float, float]:
    """A hex colour (sRGB, as a person picks it) in Blender's linear light."""
    value = colour.lstrip("#")
    r, g, b = (int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return decoded((r, g, b))


def decoded(colour: tuple[float, float, float]) -> tuple[float, float, float]:
    """An sRGB colour (each channel 0 to 1, as images store them) in linear light."""
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in colour)
    return r, g, b


def _oklab(colour: tuple[float, float, float]) -> tuple[float, float, float]:
    """A linear colour in Oklab, where distance follows how different colours look."""
    r, g, b = colour
    l_ = math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    m_ = math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    s_ = math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )
