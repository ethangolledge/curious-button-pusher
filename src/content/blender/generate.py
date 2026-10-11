# SPDX-License-Identifier: GPL-3.0-or-later
"""Runs with Infinigen's own Python (Blender 4.2 as `bpy`, `.cache/infinigen/.venv`): one of
Infinigen's procedural generators makes one object, saved as glTF.

    .cache/infinigen/.venv/bin/python src/content/blender/generate.py \\
        infinigen.assets.objects.seating.SofaFactory 3 out.glb

The same generator and seed make the same object; another seed, another of its kind."""

import sys
from pathlib import Path

import bpy  # type: ignore[import-not-found]
from infinigen.core.util.test_utils import import_item  # type: ignore[import-not-found]


def main(generator: str, seed: int, target: Path) -> int:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    factory = import_item(generator)(seed)
    made = factory.spawn_asset(seed)
    factory.finalize_assets(made)
    for obj in bpy.data.objects:
        obj.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=str(target), export_format="GLB", use_selection=True, export_apply=True
    )
    return 0


if __name__ == "__main__":
    generator, seed, target = sys.argv[1:4]
    sys.exit(main(generator, int(seed), Path(target)))
