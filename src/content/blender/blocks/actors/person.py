"""A person placed where the shot's composer worked out they go (`staging/compose.py`), as a
pose: the joints of their body from real recorded motion (their model is a pose clip:
`staging/poses.py`), fitted to the
shot's own furniture (`body.py`): seated with their hips on the seat and their feet on the
floor, their hands reaching the table before them. No body is rendered: the joints are drawn
over the layout as a skeleton, and the image model draws the person from it. Everyone is
posed the same way. Where they hold things is left as a mark, `<actor>.<thing>`
(`<aide>.drink`), for what they hold to be put in their hand."""

from dataclasses import dataclass
from typing import Annotated, Literal

from content.blender.api import Box, Figure, Mark, Stage
from content.blender.blocks.base import About, Actor, Range
from content.blender.blocks.props.chair import SEAT_HEIGHT
from content.blender.body import (
    RECORDED_FPS,
    STANDARD_HEIGHT,
    Frame,
    Table,
    extent,
    holds,
    local,
    placed,
    reached,
    reaches,
    seated,
    table_before,
)
from content.blender.maths import FRONT, UP, Quat, Vec, axis_angle


@dataclass(frozen=True)
class Settings:
    x: Annotated[float, Range(-500, 500, "metres right of the centre")] = 0.0
    y: Annotated[float, Range(-500, 500, "metres back from the centre")] = 0.0
    z: Annotated[float, Range(-50, 200, "metres up: the floor they stand on")] = 0.0
    heading: Annotated[float, Range(-360, 360, "degrees turned from facing the front")] = 0.0
    height: Annotated[float, Range(0.5, 2.5, "metres tall, standing")] = STANDARD_HEIGHT
    pose: Literal["standing", "seated", "walking"] = "standing"
    at: Annotated[float, Range(0, 1, "how far through the clip they are posed")] = 0.0
    doing: Annotated[str, About("what their hands do: resting, drink, pointing…")] = ""
    seat: Annotated[float, Range(0.2, 1.2, "metres high, the seat they sit on")] = SEAT_HEIGHT
    table: Annotated[str, About("the table or desk before them (an actor), if any")] = ""


class Person(Actor):
    name = "person"
    settings = Settings
    example = Settings(pose="standing", doing="drink")
    example_model = "sample_pose"

    def build(self, stage: Stage, p: Settings, actor_id: str, model: str) -> None:
        at, turn = Vec(p.x, p.y, p.z), axis_angle(UP, p.heading)
        scale = p.height / STANDARD_HEIGHT
        clip = stage.recording(model)
        table = stage.bounds(stage.actor(p.table)) if p.table else None
        # Walking, the whole loop plays; otherwise one moment of it is held.
        figures = clip if p.pose == "walking" else [clip[round(p.at * (len(clip) - 1))]]
        posed = [self._fitted(f, p, at, turn, scale, table) for f in figures]
        first, frame = posed[0]
        for name, point in holds(p.pose, p.doing, frame, _near(table, frame)).items():
            stage.mark(Mark(f"{actor_id}.{name}", point, turn.rotate(FRONT)))
        own = [local(figure, at, turn) for figure, _ in posed]
        thing = stage.skeleton(
            actor_id, own, fps=RECORDED_FPS if len(own) > 1 else 0.0, room=extent(own[0])
        )
        stage.place(thing, at, facing=turn.rotate(FRONT))
        stage.cast(actor_id, thing)

    @staticmethod
    def _fitted(
        figure: Figure, p: Settings, at: Vec, turn: Quat, scale: float, table: Box | None
    ) -> tuple[Figure, Frame]:
        """One pose of the clip put where they stand and fitted to the furniture."""
        posed = placed(figure, at, turn, scale)
        if p.pose == "seated":
            posed = seated(posed, p.seat, p.z, turn, scale)
        frame = Frame(posed.hips, p.z, turn, scale)
        for hand in reaches(p.pose, p.doing, frame, _near(table, frame)):
            posed = reached(posed, hand.side, hand.at, hand.elbow)
        return posed, frame


def _near(table: Box | None, frame: Frame) -> Table | None:
    """The table before a person, as they see it."""
    return table_before(table, frame) if table is not None else None
