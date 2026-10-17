# SPDX-License-Identifier: GPL-3.0-or-later
"""Runs inside Blender: a stretch of recorded motion read as poses, the joints of a body frame
by frame (`body.JOINTS`), as the pose library keeps them (`staging/poses.py`).

    PYTHONPATH=src blender -b --factory-startup --python-use-system-env \\
        --python-exit-code 1 -P src/content/blender/poses.py -- request.json out.json

The recording is a rigged, animated character (`.glb`) or a motion capture take (`.bvh`); its
skeleton's family says where each joint is (`skeletons.py`). No body is moved: each joint is
only read where its bone starts, so nothing can twist. The poses are then written as every pose
is: facing −Y as the stretch begins, standing on the floor under the middle of the hips, the
legs as long as a person of the standard height's. A loop (a walk) has its travel over the
ground taken out, so it walks on the spot, and its pace kept."""

import json
import math
import sys
from pathlib import Path
from typing import Any

import bpy  # type: ignore[import-not-found]

from content.blender import skeletons
from content.blender.body import ANKLE_HEIGHT, JOINTS, face
from content.blender.imports import import_model
from content.blender.maths import Vec, axis_angle

# A person of the standard height's legs, hip to ankle (metres).
LEG = 0.86


def main(request: dict[str, Any], out: Path) -> int:
    path = Path(request["file"])
    if path.suffix.lower() == ".bvh":
        bpy.ops.import_anim.bvh(
            filepath=str(path), frame_start=1, use_fps_scale=False, update_scene_fps=False,
            update_scene_duration=False, rotate_mode="NATIVE", axis_forward="-Z", axis_up="Y",
        )  # fmt: skip
        rate = 1 / float(
            next(line for line in path.read_text().splitlines() if "Frame Time" in line).split()[-1]
        )
    else:
        import_model(str(path))
        rate = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
    rig = next(obj for obj in bpy.data.objects if obj.type == "ARMATURE")
    found = skeletons.matched([bone.name for bone in rig.data.bones])
    if found is None:
        raise SystemExit(f"{path.name}: no known skeleton ({len(rig.data.bones)} bones)")
    family, bones = found
    action = rig.animation_data.action if rig.animation_data else None
    first, last = action.frame_range if action else (1.0, 1.0)
    start = first + request["start"] * rate
    end = min(last, first + request["end"] * rate) if request["end"] else last
    fps = request["fps"]
    count = max(1, round((end - start) / rate * fps) + 1)
    frames = [
        _read(rig, bones, start + (end - start) * i / max(1, count - 1)) for i in range(count)
    ]
    poses, speed = _written(frames, loop=request["loop"], seconds=(end - start) / rate)
    out.write_text(json.dumps({
        "family": family, "fps": fps, "seconds": round((end - start) / rate, 3),
        "speed": round(speed, 3), "loop": request["loop"],
        "frames": [[[round(c, 4) for c in pose[j].tuple()] for j in JOINTS] for pose in poses],
    }))  # fmt: skip
    return 0


def _read(rig: Any, bones: dict[str, str], frame: float) -> dict[str, Vec]:
    """Every joint, in the world, at a frame: where each bone starts; the face from the head."""
    bpy.context.scene.frame_set(int(frame), subframe=frame % 1)
    bpy.context.view_layer.update()

    def at(bone: str, end: bool = False) -> Vec:
        posed = rig.pose.bones[bone]
        return Vec(*(rig.matrix_world @ (posed.tail if end else posed.head)))

    joints = {name: at(bone) for name, bone in bones.items() if name not in ("head", "top")}
    head = at(bones["head"])
    top = at(bones["top"]) if "top" in bones else at(bones["head"], end=True)
    left = joints["shoulder.L"] - joints["shoulder.R"]
    forward = left.cross(Vec(0.0, 0.0, 1.0)).normalised()
    return {**joints, **face(head, top, forward)}


def _written(
    frames: list[dict[str, Vec]], *, loop: bool, seconds: float
) -> tuple[list[dict[str, Vec]], float]:
    """The frames as every pose is written: turned to face −Y and stood at the origin as the
    first begins, on the floor, scaled to the standard legs; a loop on the spot. Returns them
    and the pace a loop walks at (metres a second at the standard height)."""
    first = frames[0]
    hips = first["hip.L"].lerp(first["hip.R"], 0.5)
    across = first["hip.L"] - first["hip.R"]
    # Facing −Y, a person's left is +X: the turn that brings their left there.
    turn = axis_angle(Vec(0.0, 0.0, 1.0), -math.degrees(math.atan2(across.y, across.x)))
    legs = [
        (first[f"hip.{s}"] - first[f"knee.{s}"]).length()
        + (first[f"knee.{s}"] - first[f"ankle.{s}"]).length()
        for s in "LR"
    ]
    scale = LEG / (sum(legs) / 2)
    origin = Vec(hips.x, hips.y, 0.0)
    out = [{n: turn.rotate((p - origin) * scale) for n, p in f.items()} for f in frames]
    floor = min(min(f["ankle.L"].z, f["ankle.R"].z) for f in out) - ANKLE_HEIGHT
    out = [{n: p - Vec(0.0, 0.0, floor) for n, p in f.items()} for f in out]
    if not loop:
        return out, 0.0
    last = out[-1]
    travel = last["hip.L"].lerp(last["hip.R"], 0.5).flat()
    steps = max(1, len(out) - 1)
    spot = [{n: p - travel * (i / steps) for n, p in f.items()} for i, f in enumerate(out)]
    return spot, _pace(spot, seconds / steps)


def _pace(frames: list[dict[str, Vec]], step: float) -> float:
    """How fast a walk on the spot goes: the foot on the ground slides back under the body as
    fast as the body would go over it (the median over the loop, metres a second)."""
    slides = []
    for before, after in zip(frames, frames[1:], strict=False):
        planted = min(("L", "R"), key=lambda side: before[f"ankle.{side}"].z)
        moved = after[f"ankle.{planted}"] - before[f"ankle.{planted}"]
        slides.append(moved.flat().length() / step)
    slides.sort()
    return slides[len(slides) // 2] if slides else 0.0


if __name__ == "__main__":
    arguments = sys.argv[sys.argv.index("--") + 1 :]
    request, out = arguments
    sys.exit(main(json.loads(Path(request).read_text()), Path(out)))
