"""A four-door saloon car. Its wheels are parts named `wheel…`, so driving turns them."""

from content.blender.api import Stage, Thing
from content.blender.blocks.base import Prop
from content.blender.maths import Vec

LENGTH, WIDTH, WHEEL = 4.6, 1.8, 0.66


class Car(Prop):
    name = "car"
    names = ("saloon", "sedan", "automobile", "motor car", "vehicle")
    capabilities = frozenset({"vehicle"})

    def build(self, stage: Stage, name: str) -> Thing:
        car = stage.group(name)
        stage.shape(
            "box",
            Vec(WIDTH, LENGTH, 0.62),
            Vec(0, 0, 0.3),
            role="paint",
            name=f"{name}.body",
            parent=car,
            bevel=0.08,
        )
        stage.shape(
            "box",
            Vec(WIDTH * 0.86, LENGTH * 0.48, 0.5),
            Vec(0, 0.15, 0.88),
            role="paint",
            name=f"{name}.cabin",
            parent=car,
            bevel=0.1,
        )
        stage.shape(
            "box",
            Vec(WIDTH * 0.87, LENGTH * 0.4, 0.36),
            Vec(0, 0.15, 0.94),
            role="glass",
            name=f"{name}.windows",
            parent=car,
            bevel=0.06,
        )
        for index, (x, y) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
            hub = stage.group(
                f"{name}.wheel_{index}",
                Vec(x * (WIDTH / 2 - 0.12), y * LENGTH * 0.32, WHEEL / 2),
                parent=car,
            )
            stage.shape(
                "cylinder",
                Vec(WHEEL, WHEEL, 0.24),
                Vec(-0.12, 0, 0),
                role="rubber",
                name=f"{name}.tyre_{index}",
                parent=hub,
                turn=Vec(0, 90, 0),
            )
            stage.shape(
                "cylinder",
                Vec(WHEEL * 0.55, WHEEL * 0.55, 0.25),
                Vec(-0.125, 0, 0),
                role="metal",
                name=f"{name}.hubcap_{index}",
                parent=hub,
                turn=Vec(0, 90, 0),
            )
        for side in (-1, 1):
            stage.shape(
                "box",
                Vec(0.3, 0.04, 0.12),
                Vec(side * 0.6, -LENGTH / 2, 0.62),
                role="bulb",
                name=f"{name}.headlight_{side + 1}",
                parent=car,
            )
            stage.shape(
                "box",
                Vec(0.3, 0.04, 0.1),
                Vec(side * 0.6, LENGTH / 2, 0.64),
                role="paint",
                name=f"{name}.taillight_{side + 1}",
                parent=car,
            )
        return car
