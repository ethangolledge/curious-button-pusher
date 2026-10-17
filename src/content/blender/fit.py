# SPDX-License-Identifier: GPL-3.0-or-later
"""Runs inside Blender: a person's body fitted to their design, by its outline.

    PYTHONPATH=src blender -b --factory-startup --python-use-system-env \\
        --python-exit-code 1 -P src/content/blender/fit.py -- request.json out/ result.json

The design shows the person whole, facing the viewer, arms a little away from the body
(`visual.design_views`), alone on plain grey; its outline is found on this computer
(`staging/designs.outline`). The person is made from their recipe (`person.py`), stood the same
way, and their outline drawn from straight in front. Both outlines are brought to one height,
centred, and compared by how much of them overlaps (IoU: the shared area over the area either
covers). Then each of the body's dials (`person.DIALS`: weight, muscle, head, shoulders, hips,
belly…) is turned a step either way, and kept where the outlines overlap more, in smaller
steps each round. Free: every try is the same few seconds of Blender on this computer.

Writes the best dials and how well they fit to `result.json`, and to `out/` the person's
outlines and, for each view, both outlines over each other (the design's red, the person's
green, shared yellow). A front view shows breadth (shoulders, hips, a big head); a side view
shows depth (a paunch, a stoop)."""

import json
import math
import sys
from pathlib import Path
from typing import Any

import bpy  # type: ignore[import-not-found]
import numpy as np

from content.blender import person, rigging

# The range each dial is turned through (weight and muscle are MakeHuman's own, 0 to 1).
RANGES = {"weight": (0.0, 1.0), "muscle": (0.0, 1.0)}
TURN = (-1.0, 1.0)
# Each round turns every dial this far either way, from the best so far.
STEPS = (0.4, 0.2, 0.1)
# How far the arms are held out from the body, as a design shows them (degrees from upright).
ARMS_OUT = 15.0
# Outlines are compared this many pixels high, centred in this width.
HEIGHT, WIDTH = 256, 160


def main(request: dict[str, Any], out: Path, result: Path) -> int:
    # Each view of the design: its outline, and how far round from the front it was drawn.
    views = [(_normalised(_read_alpha(Path(v["mask"]))), v["turn"]) for v in request["views"]]
    recipe = request["recipe"]
    start = person.BUILD[recipe["build"]]
    body = {"weight": start[0], "muscle": start[1], **request.get("start", {})}
    tried = []

    def score(dials: dict[str, float]) -> float:
        outlines = _outlines({**recipe, "body": sorted(dials.items())}, views, out / "try")
        fit = sum(_overlap(o, design) for o, (design, _) in zip(outlines, views, strict=True))
        fit /= len(views)
        tried.append({"body": dials, "fit": round(fit, 4)})
        return fit

    best = score(body)
    for step in STEPS:
        for dial in request["dials"]:
            low, high = RANGES.get(dial, TURN)
            for way in (1.0, -1.0):
                value = round(min(high, max(low, body.get(dial, 0.0) + way * step)), 3)
                if value == body.get(dial, 0.0):
                    continue
                trial = {**body, dial: value}
                fit = score(trial)
                if fit > best:
                    best, body = fit, trial
    outlines = _outlines({**recipe, "body": sorted(body.items())}, views, out / "outline")
    for index, (outline, (design, _)) in enumerate(zip(outlines, views, strict=True)):
        _save_overlay(design, outline, out / f"overlay-{index}.png")
    result.write_text(json.dumps({"body": body, "fit": round(best, 4), "tried": tried}))
    return 0


def _overlap(outline: np.ndarray, design: np.ndarray) -> float:
    """How much two outlines overlap: their shared area over the area either covers."""
    either = float(np.logical_or(outline, design).sum())
    return float(np.logical_and(outline, design).sum()) / either if either else 0.0


def _outlines(
    recipe: dict[str, Any], views: list[tuple[np.ndarray, float]], path: Path
) -> list[np.ndarray]:
    """The person made to `recipe`, stood as a design stands them, their outline drawn from
    each view's side (degrees round from the front) and brought to the compared size."""
    rig, _ = person.made(recipe)
    rigging.arms_out(rig, ARMS_OUT)
    low, high = rigging.extent(rigging.skin(rig))
    middle = (low + high) / 2
    scene = bpy.context.scene
    camera = bpy.data.objects.new("view", bpy.data.cameras.new("view"))
    scene.collection.objects.link(camera)
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = (high.z - low.z) * 1.2
    scene.camera = camera
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.film_transparent = True
    scene.render.resolution_x, scene.render.resolution_y = 384, 512
    outlines = []
    for index, (_, turn) in enumerate(views):
        # From the front (−Y) round towards the person's left: at 90 they face right in the
        # picture, at −90 left.
        angle = math.radians(turn)
        camera.location = (middle.x + 5.0 * math.sin(angle), middle.y - 5.0 * math.cos(angle),
                           middle.z)  # fmt: skip
        camera.rotation_euler = (math.radians(90), 0.0, angle)
        scene.render.filepath = str(path.with_name(f"{path.name}-{index}.png"))
        bpy.ops.render.render(write_still=True)
        outlines.append(_normalised(_read_alpha(Path(scene.render.filepath))))
    return outlines


def _read_alpha(path: Path) -> np.ndarray:
    """Where a picture is covered: its alpha, or (with none) where it is bright."""
    image = bpy.data.images.load(str(path))
    width, height = image.size
    pixels = np.empty(width * height * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    bpy.data.images.remove(image)
    rgba = pixels.reshape(height, width, 4)[::-1]
    covered = rgba[..., 3] if rgba[..., 3].min() < 0.99 else rgba[..., :3].mean(axis=2)
    return covered > 0.5


def _normalised(mask: np.ndarray) -> np.ndarray:
    """An outline cropped to itself, scaled to `HEIGHT` (keeping its shape) and centred in
    `WIDTH`: outlines of any size and place compared alike."""
    rows, columns = np.nonzero(mask)
    if not len(rows):
        return np.zeros((HEIGHT, WIDTH), dtype=bool)
    top, bottom, left, right = rows.min(), rows.max() + 1, columns.min(), columns.max() + 1
    scale = (bottom - top) / HEIGHT
    width = min(WIDTH, max(1, round((right - left) / scale)))
    ys = (top + np.arange(HEIGHT) * scale).astype(int)
    xs = (left + np.arange(width) * scale).astype(int).clip(max=mask.shape[1] - 1)
    out = np.zeros((HEIGHT, WIDTH), dtype=bool)
    start = (WIDTH - width) // 2
    out[:, start : start + width] = mask[np.ix_(ys, xs)]
    return out


def _save_overlay(design: np.ndarray, outline: np.ndarray, path: Path) -> None:
    """Both outlines over each other: the design's red, the person's green, shared yellow."""
    rgba = np.zeros((HEIGHT, WIDTH, 4), dtype=np.float32)
    rgba[..., 0] = design
    rgba[..., 1] = outline
    rgba[..., 3] = 1.0
    image = bpy.data.images.new("overlay", WIDTH, HEIGHT, alpha=True)
    image.pixels.foreach_set(rgba[::-1].ravel())
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()


if __name__ == "__main__":
    arguments = sys.argv[sys.argv.index("--") + 1 :]
    request, out, result = arguments
    sys.exit(main(json.loads(Path(request).read_text()), Path(out), Path(result)))
