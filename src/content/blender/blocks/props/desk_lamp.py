"""An angle-poise desk lamp: a heavy base, two arms, a shade over a bulb. Its light is placed
at the part named `bulb`."""

import math

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec

ARM = 0.36


class DeskLamp(Prop):
    name = "desk_lamp"
    names = ("lamp", "anglepoise lamp", "reading lamp", "table lamp", "task lamp")
    capabilities = frozenset({"light"})

    def build(self, stage: Stage, name: str) -> Thing:
        lamp = stage.group(name)
        stage.shape(
            "cylinder",
            Vec(0.17, 0.17, 0.03),
            Vec(),
            role="metal",
            name=f"{name}.base",
            parent=lamp,
            bevel=0.004,
        )
        elbow = self._arm(stage, lamp, f"{name}.arm_low", Vec(0, 0, 0.03), lean=-18)
        head = self._arm(stage, lamp, f"{name}.arm_high", elbow, lean=62)
        stage.shape(
            "sphere",
            Vec(0.04, 0.04, 0.04),
            elbow - Vec(0, 0, 0.02),
            role="metal",
            name=f"{name}.joint",
            parent=lamp,
        )
        # The shade hangs from the arm's end, open side down and a little forward.
        stage.shape(
            "funnel",
            Vec(0.17, 0.17, 0.16),
            head - Vec(0, 0.02, 0.15),
            role="lamp_shade",
            name=f"{name}.shade",
            turn=Vec(20, 0, 0),
            parent=lamp,
        )
        stage.shape(
            "sphere",
            Vec(0.05, 0.05, 0.05),
            head - Vec(0, 0.05, 0.14),
            role="bulb",
            name=f"{name}.bulb",
            parent=lamp,
        )
        return lamp

    @staticmethod
    def _arm(stage: Stage, lamp: Thing, name: str, start: Vec, *, lean: float) -> Vec:
        """An arm from `start`, leaning `lean` degrees forward (towards −Y); returns its end."""
        stage.shape(
            "cylinder",
            Vec(0.018, 0.018, ARM),
            start,
            role="metal",
            name=name,
            turn=Vec(lean, 0, 0),
            parent=lamp,
        )
        angle = math.radians(lean)
        return start + Vec(0, -math.sin(angle) * ARM, math.cos(angle) * ARM)
