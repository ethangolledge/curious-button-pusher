"""A desktop computer monitor on a stand, with a keyboard in front."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec


class Monitor(Prop):
    name = "monitor"
    names = ("computer", "screen", "desktop computer", "computer screen", "display")
    capabilities = frozenset({"keyboard", "screen"})

    def build(self, stage: Stage, name: str) -> Thing:
        monitor = stage.group(name)
        stage.shape(
            "box",
            Vec(0.22, 0.16, 0.01),
            Vec(0, 0.08, 0),
            role="plastic",
            name=f"{name}.foot",
            parent=monitor,
        )
        stage.shape(
            "box",
            Vec(0.04, 0.03, 0.18),
            Vec(0, 0.1, 0.01),
            role="plastic",
            name=f"{name}.neck",
            parent=monitor,
        )
        stage.shape(
            "box",
            Vec(0.56, 0.03, 0.34),
            Vec(0, 0.08, 0.15),
            role="plastic",
            name=f"{name}.frame",
            parent=monitor,
            bevel=0.004,
        )
        stage.shape(
            "box",
            Vec(0.53, 0.002, 0.3),
            Vec(0, 0.064, 0.17),
            role="screen",
            name=f"{name}.screen",
            parent=monitor,
        )
        stage.shape(
            "box",
            Vec(0.44, 0.14, 0.02),
            Vec(0, -0.15, 0),
            role="plastic",
            name=f"{name}.keyboard",
            parent=monitor,
            bevel=0.003,
        )
        return monitor
