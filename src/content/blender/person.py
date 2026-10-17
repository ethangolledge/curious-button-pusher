# SPDX-License-Identifier: GPL-3.0-or-later
"""Runs inside Blender: makes a person to a recipe, once, as a library model.

    PYTHONPATH=src blender -b --factory-startup --python-use-system-env \\
        --python-exit-code 1 -P src/content/blender/person.py -- recipe.json out.glb facts.json

One parametric body (MakeHuman, through the MPFB extension; its assets are CC0) shaped by
sex, age and build, made the height asked, dressed (suit, casual, work), with hair, on the
one skeleton every person shares, and kept standing at rest: a shot poses them where it puts
them, on its own furniture (`rigging.py`). Each surface is named for its role (skin, hair,
fabric, leather), so every look draws it its own way.

So a shot can be composed without Blender, every pose is tried here and measured (standing as
its stance stands, posed as `body.py` says, at the engine's chair and table: the recipe names
each pose's stance, a motion in the library): the room it takes, how high a seat it fits
and where what it holds goes. Writes them, with the person's size, to `facts.json`."""

import json
import sys
from pathlib import Path
from typing import Any

import addon_utils  # type: ignore[import-not-found]
import bpy  # type: ignore[import-not-found]
from mathutils import Vector  # type: ignore[import-not-found]

from content.blender import body, rigging
from content.blender.blocks.props.chair import SEAT_HEIGHT
from content.blender.maths import Quat, Vec

EXTENSION = "bl_ext.user_default.mpfb"
# The MakeHuman sliders (0 to 1) each word sets.
SEX = {"man": 1.0, "woman": 0.0}
AGE = {"young": 0.4, "middle": 0.6, "old": 0.88}
BUILD = {"slim": (0.3, 0.4), "average": (0.5, 0.5), "heavy": (0.85, 0.45)}  # weight, muscle
# What each person wears, by dress and sex; then shoes and hair (by sex, and for the old).
DRESS = {
    ("suit", "man"): "toigo_male_suit_3", ("suit", "woman"): "toigo_female_suit",
    ("casual", "man"): "male_casualsuit02", ("casual", "woman"): "female_casualsuit01",
    ("work", "man"): "male_worksuit01", ("work", "woman"): "female_casualsuit02",
    ("uniform", "man"): "male_worksuit01", ("uniform", "woman"): "female_sportsuit01",
}  # fmt: skip
SHOES = {"man": "shoes01", "woman": "shoes03"}
HAIR = {("man", False): "short02", ("man", True): "short04", ("woman", False): "bob02",
        ("woman", True): "short03"}  # fmt: skip
# How a body's shape can be turned from the usual, each by a value from −1 to 1 (`body` in a
# recipe): weight and muscle (0 to 1, in place of its build), and the MakeHuman targets that
# make each part bigger or smaller (`{axis}` each of its axes in `AXES`).
DIALS = {
    "head": ("head-scale-{axis}-incr", "head-scale-{axis}-decr"),
    "shoulders": ("torso-scale-horiz-incr", "torso-scale-horiz-decr"),
    "hips": ("hip-scale-horiz-incr", "hip-scale-horiz-decr"),
    "belly": ("stomach-pregnant-incr", "stomach-pregnant-decr"),
    "neck": ("neck-scale-vert-incr", "neck-scale-vert-decr"),
}
AXES = {"head": ("vert", "horiz", "depth")}


def main(recipe: dict[str, Any], target: Path, facts: Path) -> int:
    rig, roles = made(recipe)
    _name_roles(roles)
    meshes = rigging.skin(rig)
    low, high = rigging.extent(meshes)
    # Standing on the origin, under the hips.
    at = rigging.hips(rig)
    rig.location -= Vector((at.x, at.y, low.z))
    bpy.context.view_layer.update()
    postures = {
        f"{pose}:{doing}": _measured(rig, pose, doing, recipe)
        for pose in body.POSES
        for doing in ("", *(d for p, d in body.ACTIVITIES if p == pose))
    }
    rigging.rest(rig)
    bpy.ops.export_scene.gltf(
        filepath=str(target), export_format="GLB", export_apply=True, export_skins=True,
        export_animations=False,
    )  # fmt: skip
    size = high - low
    facts.write_text(json.dumps({
        "width": round(size.x, 3), "depth": round(size.y, 3), "height": round(size.z, 3),
        "faces": sum(len(obj.data.polygons) for obj in meshes),
        "postures": postures,
    }))  # fmt: skip
    return 0


def made(recipe: dict[str, Any]) -> tuple[Any, dict[str, str]]:
    """The body, dressed, at its height, on the shared skeleton; and each surface's role."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    addon_utils.enable(EXTENSION, default_set=True)
    from bl_ext.user_default.mpfb.services.humanservice import (  # type: ignore[import-not-found]
        HumanService,
    )
    from bl_ext.user_default.mpfb.services.locationservice import (  # type: ignore[import-not-found]
        LocationService,
    )
    from bl_ext.user_default.mpfb.services.targetservice import (  # type: ignore[import-not-found]
        TargetService,
    )

    sex, old = recipe["sex"], recipe["age"] == "old"
    weight, muscle = BUILD[recipe["build"]]
    dials = dict(recipe.get("body", ()))
    macro = TargetService.get_default_macro_info_dict()
    macro.update({
        "gender": SEX[sex], "age": AGE[recipe["age"]],
        "weight": dials.pop("weight", weight), "muscle": dials.pop("muscle", muscle),
    })  # fmt: skip
    human = HumanService.create_human(macro_detail_dict=macro, scale=0.1)
    # The body's own shape (a big head, a paunch), before it is rigged and dressed to it.
    TargetService.bulk_load_targets(human, [
        {"target": DIALS[dial][0 if value > 0 else 1].format(axis=axis), "value": abs(value)}
        for dial, value in dials.items() if value
        for axis in AXES.get(dial, ("",))
    ])  # fmt: skip
    rig = HumanService.add_builtin_rig(human, "default", import_weights=True)
    data = Path(LocationService.get_user_data())
    roles = {human.name: "skin"}
    for folder, kind, role in (
        (f"clothes/{DRESS[(recipe['dress'], sex)]}", "Clothes", "fabric"),
        (f"clothes/{SHOES[sex]}", "Clothes", "leather"),
        (f"hair/{HAIR[(sex, old)]}", "Hair", "hair"),
        ("eyebrows/eyebrow001", "Eyebrows", "hair"),
    ):
        asset = next((data / folder).glob("*.mhclo"))
        worn = HumanService.add_mhclo_asset(str(asset), human, asset_type=kind, subdiv_levels=0)
        roles[worn.name] = role
    bpy.context.view_layer.update()
    low, high = rigging.extent(rigging.skin(rig))
    rig.scale = (recipe["height"] / (high.z - low.z),) * 3
    bpy.context.view_layer.update()
    # Its size as made is its real size: the scale is kept in the bones it exports.
    bpy.context.view_layer.objects.active = rig
    for obj in [rig, *rigging.skin(rig)]:
        obj.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return rig, roles


def _measured(rig: Any, pose: str, doing: str, recipe: dict[str, Any]) -> dict[str, Any]:
    """A pose tried on the person, at the engine's chair and table, and measured: the room it
    takes (its size, and where its middle is from where they stand), how high the seat it
    fits is, and where each thing they hold goes."""
    rigging.rest(rig)
    standing = rig.location.copy()
    frame = body.Frame(rigging.hips(rig), 0.0, Quat(), recipe["height"] / body.STANDARD_HEIGHT)
    path, name, at = recipe["stances"][pose]
    stance = (rigging.motion(path, name), at)
    held = rigging.perform(rig, frame, pose, doing, stance=stance, seat=SEAT_HEIGHT, table=None)
    hips = rigging.hips(rig)
    meshes = rigging.skin(rig)
    low, high = rigging.extent(meshes)
    at = Vec(hips.x, hips.y, 0.0)
    size = high - low
    measured = {
        "size": [round(size.x, 3), round(size.y, 3), round(size.z, 3)],
        "middle": [round((low.x + high.x) / 2 - at.x, 3), round((low.y + high.y) / 2 - at.y, 3)],
        "seat": round(rigging.underside(meshes, hips), 3) if pose == "seated" else 0.0,
        "holds": {
            name: [round(p.x - at.x, 3), round(p.y - at.y, 3), round(p.z, 3)]
            for name, p in held.items()
        },
    }
    rig.location = standing
    return measured


def _name_roles(roles: dict[str, str]) -> None:
    """Each surface's material named for its role, the skeleton kept."""
    for obj in [o for o in bpy.data.objects if o.type == "MESH"]:
        obj.data.materials.clear()
        obj.data.materials.append(bpy.data.materials.new(roles.get(obj.name, "fabric")))


if __name__ == "__main__":
    arguments = sys.argv[sys.argv.index("--") + 1 :]
    recipe, target, facts = arguments
    sys.exit(main(json.loads(Path(recipe).read_text()), Path(target), Path(facts)))
