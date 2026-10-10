"""Many of one model on a mark: a pile of banknote bundles, a column of boxes, a row of
files. The items are parts named `item…`, so an action can move them one by one (a stack
toppling)."""

from dataclasses import dataclass
from typing import Annotated, Literal

from content.blender.api import Stage
from content.blender.blocks.base import About, Actor, Range, Ref
from content.blender.maths import FRONT, Vec
from content.blender.sets import resting_on


@dataclass(frozen=True)
class Settings:
    at: Annotated[Ref, About("a mark in the layout")]
    count: Annotated[int, Range(1, 400, "how many")] = 12
    shape: Literal["column", "pile", "row", "tower"] = "column"
    gap: Annotated[float, Range(0, 0.5, "metres between items")] = 0.002


class Stack(Actor):
    name = "stack"
    settings = Settings
    example = Settings(at=Ref("centre"), count=3)

    def build(self, stage: Stage, p: Settings, actor_id: str, model: str) -> None:
        group = stage.group(actor_id, resting_on(stage.find_mark(p.at.name)))
        chance = stage.random(f"stack:{actor_id}")
        size: Vec | None = None
        for index in range(p.count):
            item = stage.model(model, name=f"{actor_id}.item_{index}")
            size = size or stage.bounds(item).size
            at, facing = _slot(p.shape, index, p.count, size, p.gap, chance.uniform(-1, 1))
            stage.place(item, at, facing=facing, parent=group)
        stage.cast(actor_id, group)


def _slot(
    shape: str, index: int, count: int, size: Vec, gap: float, jitter: float
) -> tuple[Vec, Vec]:
    """Where item `index` goes, relative to the mark, and which way it faces."""
    if shape == "row":
        return Vec((index - (count - 1) / 2) * (size.x + gap), 0, 0), FRONT
    if shape == "pile":
        # A loose heap: each layer smaller than the one under it.
        layer, within = 0, index
        while within >= max(1, (4 - layer)) ** 2:
            within -= max(1, (4 - layer)) ** 2
            layer += 1
        side = max(1, 4 - layer)
        x, y = within % side - (side - 1) / 2, within // side - (side - 1) / 2
        at = Vec(x * size.x * 1.02 + jitter * 0.01, y * size.y * 1.02, layer * (size.z + gap))
        return at, FRONT
    if shape == "tower":
        # Crossed layers of three side by side, like a stacking game: each layer's items lie
        # across the one below, spaced by their narrow side.
        layer, slot = divmod(index, 3)
        across = (slot - 1) * (size.y + gap)
        lift = Vec(0, 0, layer * (size.z + gap))
        if layer % 2 == 0:
            return Vec(across, 0, 0) + lift, Vec(1, 0, 0)
        return Vec(0, across, 0) + lift, FRONT
    return Vec(jitter * 0.004, 0, index * (size.z + gap)), FRONT
