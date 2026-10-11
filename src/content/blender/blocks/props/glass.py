"""A drinking glass of any kind: a tumbler, a whisky glass, a wine or champagne glass on its
stem, a pint glass; with a drink in it or empty."""

from dataclasses import dataclass
from typing import Annotated, Literal

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop, Range
from content.blender.maths import Vec

# Each style: the bowl's height and width, the stem's height (0: none), and how full it is.
STYLES = {
    "tumbler": (0.1, 0.075, 0.0, 0.5),
    "whisky": (0.085, 0.085, 0.0, 0.3),
    "wine": (0.1, 0.085, 0.09, 0.4),
    "champagne": (0.11, 0.05, 0.1, 0.7),
    "pint": (0.15, 0.085, 0.0, 0.85),
}


@dataclass(frozen=True)
class Settings:
    style: Literal["tumbler", "whisky", "wine", "champagne", "pint"] = "tumbler"
    full: Annotated[float, Range(0, 1, "how full; 0 is empty")] = 0.5
    height: Annotated[float, Range(0, 0.4, "metres tall; 0 for the style's own")] = 0.0


class Glass(Prop):
    name = "glass"
    names = ("tumbler", "whisky glass", "wine glass", "champagne glass", "flute", "pint",
             "drink", "glass of water", "water glass", "shot glass")  # fmt: skip
    settings = Settings
    example = Settings()

    def build(self, stage: Stage, name: str) -> Thing:
        p: Settings = self.p
        bowl, wide, stem, _ = STYLES[p.style]
        scale = p.height / (bowl + stem) if p.height else 1.0
        bowl, wide, stem = bowl * scale, wide * scale, stem * scale
        glass = stage.group(name)
        if stem:
            stage.shape("cylinder", Vec(wide * 0.9, wide * 0.9, 0.004), Vec(), role="glass",
                        name=f"{name}.foot", parent=glass)  # fmt: skip
            stage.shape("cylinder", Vec(0.008, 0.008, stem), Vec(), role="glass",
                        name=f"{name}.stem", parent=glass)  # fmt: skip
        stage.shape("cylinder", Vec(wide, wide, bowl), Vec(0, 0, stem), role="glass",
                    name=f"{name}.bowl", parent=glass)  # fmt: skip
        if p.full:
            stage.shape("cylinder", Vec(wide * 0.88, wide * 0.88, bowl * p.full * 0.9),
                        Vec(0, 0, stem + bowl * 0.06), role="wood", name=f"{name}.drink",
                        parent=glass)  # fmt: skip
        return glass
