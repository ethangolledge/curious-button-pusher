"""A plain studio: a wide floor and a distant backdrop around a low plinth, for showing one
object on its own, as a museum or a catalogue would. Marks: plinth_top (stand the object
here), centre."""

from dataclasses import dataclass
from typing import Annotated, Literal

from content.blender.api import Mark, Stage
from content.blender.blocks.base import Layout, Range
from content.blender.maths import FRONT, Vec
from content.blender.sets import surface_mark


@dataclass(frozen=True)
class Settings:
    plinth: Annotated[float, Range(0, 1.5, "metres high; 0 for none")] = 0.6
    backdrop: Literal["paint", "concrete", "fabric", "paper"] = "paint"


class Studio(Layout):
    name = "studio"
    settings = Settings
    example = Settings()

    def build(self, stage: Stage, p: Settings) -> None:
        stage.shape("plane", Vec(60, 60, 0), Vec(), role=p.backdrop, name="floor")
        # Far enough back that its line with the floor sits in the dark behind the object.
        stage.shape("box", Vec(60, 0.1, 25), Vec(0, 14, 0), role=p.backdrop, name="backdrop")
        stage.mark(Mark("centre", Vec(), FRONT))
        if p.plinth:
            plinth = stage.shape(
                "box", Vec(0.8, 0.8, p.plinth), Vec(), role="concrete", name="plinth", bevel=0.005
            )
            stage.mark(surface_mark("plinth_top", stage.bounds(plinth)))
        else:
            stage.mark(Mark("plinth_top", Vec(), FRONT))
