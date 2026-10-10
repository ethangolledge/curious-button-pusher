"""What lights share: where a light sits on the thing that gives it (a lamp's bulb, a car's
headlight), and the way any light can flicker."""

from content.blender.api import Stage, Thing
from content.blender.maths import Vec


def source(stage: Stage, name: str, part: str = "bulb") -> Vec:
    """The centre of an actor's named part (its bulb), else its top, else a mark lifted to
    head height."""
    try:
        actor = stage.actor(name)
    except KeyError:
        return stage.find_mark(name).at + Vec(0, 0, 1.8)
    parts = stage.parts(actor, part)
    if parts:
        return stage.bounds(parts[0]).centre
    box = stage.bounds(actor)
    return Vec(box.centre.x, box.centre.y, box.top)


def flicker(stage: Stage, light: Thing, power: float, amount: float) -> None:
    """Dips and stutters in a light's power; none at 0, a failing bulb at 1."""
    if amount <= 0:
        return
    chance = stage.random(f"flicker:{light.name}")
    keys, frame = [], 1
    while frame <= stage.frames:
        keys.append((frame, power))
        if chance.random() < 0.08 * amount:
            dips = chance.randint(1, 3)
            for step in range(dips):
                keys.append(
                    (frame + 1 + step * 2, power * (1 - amount * chance.uniform(0.4, 0.95)))
                )
                keys.append((frame + 2 + step * 2, power))
            frame += 2 + dips * 2
        else:
            frame += chance.randint(4, 12)
    stage.animate_value(light, "power", [(f, v) for f, v in keys if f <= stage.frames])
