# SPDX-License-Identifier: GPL-3.0-or-later
"""The starter kit's look, and the template for a channel's own: the engine's plain look,
pulled towards the channel's palette. It changes only what differs (the colours, the world,
the tone); every setting is a knob for the feel. A channel copies this file, renames it and
changes what it draws: its materials and finishing can go as far as its style needs."""

from dataclasses import dataclass
from typing import Annotated, Literal

from content.blender.blocks.base import About, Range
from content.blender.blocks.looks.plain import ROLES, Plain
from content.blender.stage import linear

GLOWING = ("bulb", "screen")
Contrast = Literal[
    "None", "Very Low Contrast", "Low Contrast", "Medium Low Contrast", "Medium High Contrast",
    "High Contrast", "Very High Contrast",
]  # fmt: skip


@dataclass(frozen=True)
class Settings:
    exposure: Annotated[float, Range(-4, 4, "stops brighter or darker")] = 0.0
    contrast: Contrast = "None"
    saturation: Annotated[float, Range(0, 1.5, "0 grey, 1 as made, above 1 richer")] = 1.0
    shadow: Annotated[str, About("the palette colour the dark leans towards")] = "night"
    glow: Annotated[str, About("the palette colour lamps and screens glow in")] = "sun"


class Starter(Plain):
    name = "starter"
    settings = Settings
    example = Settings()

    def colour(self, role: str) -> tuple[float, float, float]:
        if role in GLOWING:
            return linear(self.palette.get(self.values.glow, ROLES[role][0]))
        r, g, b = super().colour(role)
        grey = 0.2126 * r + 0.7152 * g + 0.0722 * b
        mixed = [grey + (c - grey) * self.values.saturation for c in (r, g, b)]
        # The darker a surface, the more it leans towards the shadow colour (up to a fifth).
        shade = linear(self.palette.get(self.values.shadow, "#000000"))
        lean = 0.2 * (1 - min(grey * 3, 1))
        sr, sg, sb = (c + (s - c) * lean for c, s in zip(mixed, shade, strict=True))
        return sr, sg, sb

    def sky(self) -> tuple[tuple[float, float, float], float]:
        return linear(self.palette.get(self.values.shadow, "#202428")), 0.5

    def tone(self) -> tuple[str, float]:
        look = "None" if self.values.contrast == "None" else f"AgX - {self.values.contrast}"
        return look, self.values.exposure
