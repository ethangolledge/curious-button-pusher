"""A person placed where the shot's composer worked out they go (`staging/compose.py`), and
posed there on the shot's own furniture: standing, seated on a seat (their legs bent so their
feet stand on the floor) or mid-stride; their hands resting on the table before them, holding
a drink, pointing (`body.py`). Every person, made from words or from a design, is posed this
same way, on the same skeleton. Where they hold things is left as a mark, `<actor>.<thing>`
(`<aide>.drink`), for what they hold to be put in their hand."""

from dataclasses import dataclass
from typing import Annotated, Literal

from content.blender.api import Mark, Stage
from content.blender.blocks.base import About, Actor, Range
from content.blender.blocks.props.chair import SEAT_HEIGHT
from content.blender.maths import FRONT, UP, Vec, axis_angle


@dataclass(frozen=True)
class Settings:
    x: Annotated[float, Range(-500, 500, "metres right of the centre")] = 0.0
    y: Annotated[float, Range(-500, 500, "metres back from the centre")] = 0.0
    z: Annotated[float, Range(-50, 200, "metres up: the floor they stand on")] = 0.0
    heading: Annotated[float, Range(-360, 360, "degrees turned from facing the front")] = 0.0
    pose: Literal["standing", "seated", "walking"] = "standing"
    doing: Annotated[str, About("what their hands do: resting, drink, pointing…")] = ""
    seat: Annotated[float, Range(0.2, 1.2, "metres high, the seat they sit on")] = SEAT_HEIGHT
    table: Annotated[str, About("the table or desk before them (an actor), if any")] = ""


class Person(Actor):
    name = "person"
    settings = Settings
    example = Settings(pose="standing", doing="drink")
    example_model = "sample_person"

    def build(self, stage: Stage, p: Settings, actor_id: str, model: str) -> None:
        thing = stage.model(model, name=actor_id)
        facing = axis_angle(UP, p.heading).rotate(FRONT)
        stage.place(thing, Vec(p.x, p.y, p.z), facing=facing)
        table = stage.actor(p.table) if p.table else None
        held = stage.perform(thing, p.pose, p.doing, seat=p.seat, table=table)
        for name, at in held.items():
            stage.mark(Mark(f"{actor_id}.{name}", at, facing))
        stage.cast(actor_id, thing)
