"""A boardroom: a long table down the middle of a room, chairs along both sides and one at
its head. Actors: table, chair_0…. Marks: table_top, head (the head chair), seat_0… (each
chair), and the room's marks."""

from dataclasses import dataclass
from typing import Annotated

from content.blender.api import Mark, Stage
from content.blender.blocks.base import Layout, Range
from content.blender.maths import Vec
from content.blender.sets import room, surface_mark

# Facing the table from the near side, and from the far side.
FRONT_ON, BACK_ON = Vec(0, 1, 0), Vec(0, -1, 0)


@dataclass(frozen=True)
class Settings:
    chairs: Annotated[int, Range(0, 8, "chairs along each side")] = 4
    blinds: bool = True


class Boardroom(Layout):
    name = "boardroom"
    settings = Settings
    example = Settings(chairs=1)

    def build(self, stage: Stage, p: Settings) -> None:
        room(stage, 8.0, 6.5, 3.0, window=True, blinds=p.blinds, door=True)
        table = stage.model("table", name="table", settings={"style": "conference"})
        stage.place(table, Vec(0, 0.3, 0))
        stage.cast("table", table)
        top = stage.bounds(table)
        stage.mark(surface_mark("table_top", top))
        # Chairs a metre apart, closer if that many would not fit along the table.
        spacing = min(1.0, (top.size.x - 0.4) / max(p.chairs, 1))
        seats: list[tuple[Vec, Vec]] = []
        for index in range(p.chairs):
            x = (index - (p.chairs - 1) / 2) * spacing
            seats += [
                (Vec(x, top.low.y - 0.3, 0), FRONT_ON),
                (Vec(x, top.high.y + 0.3, 0), BACK_ON),
            ]
        seats.append((Vec(top.low.x - 0.6, top.centre.y, 0), Vec(1, 0, 0)))
        for index, (at, facing) in enumerate(seats):
            chair = stage.model("chair", name=f"chair_{index}")
            # Whoever sits faces the table, so the chair does too.
            stage.place(chair, at, facing=facing)
            stage.cast(f"chair_{index}", chair)
            stage.mark(Mark(f"seat_{index}", at, facing))
        stage.mark(Mark("head", seats[-1][0], seats[-1][1]))
