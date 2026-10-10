"""Outdoor light: the sun and the sky at a time of day, from day to a moonlit night."""

import math
from dataclasses import dataclass
from typing import Annotated, Literal

from content.blender.api import Stage
from content.blender.blocks.base import Light, Range
from content.blender.maths import Vec

TIMES = {
    "day": ("#fff3e0", 4.5, 50.0),
    "golden": ("#ffbf80", 3.0, 12.0),
    "dusk": ("#ff9a6a", 1.2, 3.0),
    "night": ("#9db4e0", 0.25, 35.0),
}


@dataclass(frozen=True)
class Settings:
    time: Literal["day", "golden", "dusk", "night"] = "day"
    from_degrees: Annotated[float, Range(-180, 180, "where the sun is, round from the front")] = (
        40.0
    )
    strength: Annotated[float, Range(0, 5, "times the usual")] = 1.0


class Sky(Light):
    name = "sky"
    settings = Settings
    example = Settings()

    def build(self, stage: Stage, p: Settings) -> None:
        colour, power, height = TIMES[p.time]
        turn, rise = math.radians(p.from_degrees), math.radians(height)
        towards = Vec(
            math.sin(turn) * math.cos(rise), -math.cos(turn) * math.cos(rise), math.sin(rise)
        )
        stage.light(
            "sun",
            name="sun",
            at=towards * 50,
            colour=colour,
            power=power * p.strength,
            aim=Vec(),
            size=0.01 if p.time != "night" else 0.03,
        )
