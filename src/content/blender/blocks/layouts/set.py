"""A set from the model library, built by hand (in Blender, or downloaded) rather than in
code: an office, a harbour, a bank vault. Its named parts become the layout's vocabulary:
empties `mark_<name>` are marks (facing the empty's −Y), meshes `surface_<name>` are marks
on their tops, empties `path_<name>_<n>` are paths (in order of n), objects `actor_<name>` are
actors, and a box `interior` is the space the camera stays in (it is not rendered). Its people
(`actor_person_…`, as a lifted picture has: `docs/picture-shots.md`) play `motion` all through
the shot, each starting at their own moment."""

import re
from dataclasses import dataclass
from typing import Annotated, Literal

from content.blender.api import Mark, Stage, Thing
from content.blender.blocks.base import Layout, ModelName
from content.blender.maths import FRONT, Vec
from content.blender.sets import surface_mark


@dataclass(frozen=True)
class Settings:
    model: Annotated[str, ModelName("a set from the model library, by id")] = ""
    motion: Literal["breathing", "talking", "still"] = "breathing"


class Set(Layout):
    name = "set"
    settings = Settings
    example = Settings(model="sample_set")

    def build(self, stage: Stage, p: Settings) -> None:
        if not p.model:
            raise ValueError("set: name a set from the model library (model)")
        scene = stage.model(p.model, name="set")
        for part in stage.parts(scene, "mark_"):
            pose = stage.poses(part)[0]
            stage.mark(Mark(_named(part, "mark_"), pose.at, pose.rotation.rotate(FRONT)))
        for part in stage.parts(scene, "surface_"):
            stage.mark(surface_mark(_named(part, "surface_"), stage.bounds(part)))
        chance = stage.random("set people")
        for part in stage.parts(scene, "actor_"):
            stage.cast(_named(part, "actor_"), part)
            if p.motion != "still" and _named(part, "actor_").startswith("person"):
                try:
                    begins = 1 + chance.randrange(max(stage.frames // 3, 1))
                    stage.play(part, p.motion, start_frame=begins)
                except (KeyError, ValueError):
                    pass  # a person whose pose was too unsure for a skeleton stays still
        routes: dict[str, list[tuple[int, Vec]]] = {}
        for part in stage.parts(scene, "path_"):
            found = re.fullmatch(r"(.+)_(\d+)", _named(part, "path_"))
            if found:
                routes.setdefault(found[1], []).append((int(found[2]), stage.poses(part)[0].at))
        for route, points in routes.items():
            stage.path(route, [at for _, at in sorted(points, key=lambda point: point[0])])
        for part in stage.parts(scene, "interior"):
            stage.mark(Mark("interior", Vec(), FRONT, stage.bounds(part)))
            stage.animate_value(part, "visible", [(1, 0.0)])


def _named(part: Thing, prefix: str) -> str:
    """A part's own name after its prefix, without Blender's numbering (`mark_door.001`)."""
    return re.sub(r"\.\d+$", "", part.name).split(".")[-1].removeprefix(prefix)
