"""Light through the layout's window: daylight, dusk, or moonlight, falling into the room at
an angle, with a soft fill from the sky."""

from dataclasses import dataclass
from typing import Annotated, Literal

from content.blender.api import Stage
from content.blender.blocks.base import About, Light, Range, Ref
from content.blender.maths import Vec

TIMES = {
    "day": ("#fff1dc", 4.0, "#bcd3ea", 60.0, 45.0),
    "dusk": ("#ffb070", 2.5, "#7088b8", 30.0, 12.0),
    "night": ("#9fb4d8", 0.35, "#1c2a44", 8.0, 30.0),
}


@dataclass(frozen=True)
class Settings:
    at: Annotated[Ref, About("the window's mark")] = Ref("window")
    time: Literal["day", "dusk", "night"] = "day"
    strength: Annotated[float, Range(0, 5, "times the usual")] = 1.0
    from_side: Annotated[float, Range(-80, 80, "degrees the light comes from the right")] = 30.0


class Window(Light):
    name = "window"
    settings = Settings
    example = Settings(at=Ref("centre"))

    def build(self, stage: Stage, p: Settings) -> None:
        mark = stage.find_mark(p.at.name)
        sun_colour, sun, sky_colour, sky, elevation = TIMES[p.time]
        # The sun shines in through the window, from outside (behind the mark) and above.
        inward = mark.facing.normalised()
        side = Vec(-inward.y, inward.x, 0) * (p.from_side / 45)
        direction = (inward + side + Vec(0, 0, -elevation / 45)).normalised()
        stage.light(
            "sun",
            name=f"{p.at.name}_sun",
            at=mark.at - direction * 5,
            colour=sun_colour,
            power=sun * p.strength,
            aim=mark.at,
            size=0.02,
        )
        stage.light(
            "area",
            name=f"{p.at.name}_sky",
            at=mark.at + inward * 0.2 + Vec(0, 0, 0.7),
            colour=sky_colour,
            power=sky * p.strength,
            aim=mark.at + inward * 3,
            size=1.6,
        )
