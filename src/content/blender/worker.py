# SPDX-License-Identifier: GPL-3.0-or-later
"""Runs inside Blender: reads a job, builds the shot, checks it, renders it.

    blender -b --factory-startup --python-exit-code 1 \
        -P src/content/blender/worker.py -- job.json out/

Writes `out/frames/NNNN.png`, `out/snapshot.json` (where everything is on a few frames, for
tests), `out/report.json`, and with `save_scene` the built scene as `out/scene.blend`."""

import json
import sys
import time
from pathlib import Path
from typing import Any

SOURCE = Path(__file__).resolve().parents[2]
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

import bpy  # type: ignore[import-not-found]  # noqa: E402
from mathutils import Vector  # type: ignore[import-not-found]  # noqa: E402

from content.blender.audit import audit  # noqa: E402
from content.blender.blocks.base import Look, read  # noqa: E402
from content.blender.camera import SUBJECT  # noqa: E402
from content.blender.direct import build  # noqa: E402
from content.blender.job import Grade, Job, Report  # noqa: E402
from content.blender.registry import KINDS, LOOKS, discover  # noqa: E402
from content.blender.stage import BlenderStage  # noqa: E402

# How far full warmth (or cold) moves the white balance from daylight.
WARMTH_KELVIN = 2500


def main(job_path: Path, out: Path, *, force: bool) -> int:
    job = Job.read(job_path)
    started = time.perf_counter()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
    registry = discover([Path(folder) for folder in job.channel_blocks], [*KINDS, *LOOKS])
    look_block = registry.get("looks", job.look.block)
    assert issubclass(look_block, Look)
    look = look_block(read(look_block, job.look.settings), job.palette)
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = job.width, job.height
    scene.render.fps = job.fps
    scene.frame_start, scene.frame_end = 1, job.frame_count
    scene.render.image_settings.file_format = "PNG"
    look.world(scene)
    look.render(scene, job.quality)
    _grade(scene, job.grade)
    stage = BlenderStage(
        frames=job.frame_count,
        fps=job.fps,
        aspect=job.width / job.height,
        seed=job.seed,
        look=look,
        props=registry.props(),
        model_files={m.model_id: (m.path, m.size) for m in job.models},
    )
    build(stage, job, registry)
    issues = audit(job.frame_count, _subject(stage))
    out.mkdir(parents=True, exist_ok=True)
    (out / "snapshot.json").write_text(json.dumps(_snapshot(job.frame_count), indent=1))
    blend = None
    if job.save_scene:
        blend = str(out / "scene.blend")
        bpy.ops.wm.save_as_mainfile(filepath=blend)
    built = time.perf_counter()
    frames: list[str] = []
    if not issues or force:
        frames = _render(job, out / "frames")
    report = Report(
        shot_id=job.shot_id,
        frames=frames,
        issues=issues,
        seconds_building=round(built - started, 2),
        seconds_rendering=round(time.perf_counter() - built, 2),
        blend=blend,
    )
    (out / "report.json").write_text(report.dumps())
    return 0 if frames else 2


def _grade(scene: Any, grade: Grade) -> None:
    """The scene's feeling on top of the look: exposure, and warmth through the white
    balance (a warmer scene is balanced for bluer light, so it renders warmer)."""
    scene.view_settings.exposure += grade.exposure
    if grade.warmth:
        scene.view_settings.use_white_balance = True
        scene.view_settings.white_balance_temperature = 6500 + WARMTH_KELVIN * grade.warmth


def _subject(stage: BlenderStage) -> tuple[Vector, float] | None:
    try:
        box = stage.find_mark(SUBJECT).surface
    except KeyError:
        return None
    return (Vector(box.centre.tuple()), box.radius) if box else None


def _render(job: Job, folder: Path) -> list[str]:
    scene = bpy.context.scene
    folder.mkdir(parents=True, exist_ok=True)
    wanted = job.frames or tuple(range(1, job.frame_count + 1))
    written = []
    for frame in wanted:
        scene.frame_set(frame)
        target = folder / f"{frame:04d}.png"
        scene.render.filepath = str(target)
        bpy.ops.render.render(write_still=True)
        written.append(str(target))
    return written


def _snapshot(frames: int) -> dict[str, dict[str, list[list[float]]]]:
    """Every top-level thing's place and turn on the first, middle and last frames."""
    scene = bpy.context.scene
    picked = sorted({1, (frames + 1) // 2, frames})
    out: dict[str, dict[str, list[list[float]]]] = {}
    for frame in picked:
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        for obj in scene.objects:
            if obj.parent is not None:
                continue
            location, rotation, _ = obj.matrix_world.decompose()
            out.setdefault(obj.name, {})[str(frame)] = [
                [round(v, 3) for v in location],
                [round(v, 3) for v in rotation],
            ]
    scene.frame_set(1)
    return out


if __name__ == "__main__":
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    sys.exit(main(Path(arguments[0]), Path(arguments[1]), force="--force" in arguments))
