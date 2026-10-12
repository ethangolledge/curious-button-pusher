"""Lifting a keyframe into depth for a picture shot (docs/picture-shots.md): the picture's own
camera and lens, its people standing in front of what is painted in behind them, and the
shot that glides from where the picture was taken, in the picture's own look. The vision
models are stood in for by a scene of known shape: a wall 3 m away and a person 2 m away."""

from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from content.config import load_config
from content.providers import vision
from content.staging import lift as lifting
from content.staging.catalogue import check, load_catalogue
from content.staging.library import Library
from content.staging.plan import PAINTED, picture_job, themed

WIDTH, HEIGHT = 120, 200
FOCAL = (1.2, 0.72)  # fractions of width and height: square pixels (1.2 × 120 = 0.72 × 200)
WALL, PERSON = 3.0, 2.0
BOX = (40.0, 60.0, 80.0, 180.0)  # the person, in pixels


def _scene(monkeypatch: pytest.MonkeyPatch, picture: Path) -> list[str]:
    """A picture whose geometry the stand-in vision models report: a wall, and a person in
    front of it. Returns what was asked of them, in order."""
    Image.fromarray(np.full((HEIGHT, WIDTH, 3), 90, np.uint8)).save(picture)
    left, top, right, bottom = (int(v) for v in BOX)
    inside = np.zeros((HEIGHT, WIDTH), bool)
    inside[top:bottom, left:right] = True
    depth = np.where(inside, PERSON, WALL).astype(np.float32)
    u = ((np.arange(WIDTH) + 0.5) / WIDTH - 0.5)[None, :] / FOCAL[0] * depth
    v = ((np.arange(HEIGHT) + 0.5) / HEIGHT - 0.5)[:, None] / FOCAL[1] * depth
    asked: list[str] = []

    def record(name: str, value: Any) -> Any:
        asked.append(name)
        return value

    joints = np.zeros((1, 17, 3), np.float32)
    joints[0, :, 0], joints[0, :, 1], joints[0, :, 2] = 60, np.linspace(70, 170, 17), 0.9
    monkeypatch.setattr(vision, "ready", lambda: True)
    monkeypatch.setattr(vision, "geometry", lambda image: record(
        "geometry", vision.Geometry(np.stack([u, v, depth], axis=-1), FOCAL)))  # fmt: skip
    monkeypatch.setattr(vision, "find", lambda image, phrases, threshold: record(
        "find", [vision.Found(BOX, 0.9, "a person")]))  # fmt: skip
    monkeypatch.setattr(vision, "outline", lambda image, boxes: record("outline", inside[None]))
    monkeypatch.setattr(vision, "poses", lambda image, boxes: record("poses", joints))
    monkeypatch.setattr(vision, "fill", lambda pixels, hole: record("fill", pixels))
    return asked


def test_a_picture_is_lifted_with_its_own_camera_and_its_people_in_front(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _scene(monkeypatch, tmp_path / "scene.png")

    arrays, parts, _, people = lifting.lift(tmp_path / "scene.png")

    named = {part["name"]: part for part in parts}
    assert people == 1 and set(named) == {
        "mark_camera", "mark_ahead", "actor_person_0", "interior",
    }  # fmt: skip
    # The picture's own lens, its sensor across the longer side (here the height).
    assert named["mark_camera"]["lens"] == pytest.approx(lifting.SENSOR_MM * FOCAL[1], abs=0.01)
    camera = np.array(named["mark_camera"]["at"])
    ahead = arrays["ground"][..., 1] - camera[1]
    # Everything is in front of the camera; behind the person, the wall stays at its distance
    # (never brought forward to them), and the camera may move round inside the interior.
    assert ahead.min() > 0
    assert np.allclose(ahead, WALL, atol=0.01)
    room = named["interior"]
    assert all(abs(camera[i] - room["at"][i]) < room["size"][i] / 2 for i in range(3))


def test_a_persons_surface_reaches_past_their_outline_on_them_not_the_wall(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _scene(monkeypatch, tmp_path / "scene.png")

    arrays, parts, _, _ = lifting.lift(tmp_path / "scene.png")

    camera = np.array(next(p for p in parts if p["name"] == "mark_camera")["at"])
    reach, surface = arrays["people_reach"][0], arrays["people_points"][0]
    pixels = arrays["points_pixels"]
    left, top, right, bottom = BOX
    outside = (pixels[..., 0] < left) | (pixels[..., 0] >= right) | (pixels[..., 1] < top)
    assert (reach & outside).any()  # past the outline
    assert np.allclose(surface[reach][..., 1] - camera[1], PERSON, atol=0.01)  # all on them


def test_the_wall_behind_a_person_is_never_nearer_than_they_are(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Depth carried in from something in front of a person (a desk) must not stand in
    front of them: behind them is at least a little further than they are."""
    _scene(monkeypatch, tmp_path / "scene.png")
    monkeypatch.setattr(lifting, "_carried", lambda depth, hole: np.where(hole, 0.5, depth))

    arrays, parts, _, _ = lifting.lift(tmp_path / "scene.png")

    camera = np.array(next(p for p in parts if p["name"] == "mark_camera")["at"])
    behind = arrays["ground"][..., 1] - camera[1]
    assert behind.min() >= PERSON * (1 + lifting.BEHIND) - 0.01


def test_a_picture_is_lifted_once_and_kept_in_the_library(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    asked = _scene(monkeypatch, tmp_path / "scene.png")
    library = Library(folder=tmp_path / "library")

    first = lifting.lifted(library, tmp_path / "scene.png", make=True)
    again = lifting.lifted(library, tmp_path / "scene.png", make=True)

    assert first is not None and again is first
    assert asked.count("geometry") == 1
    assert first.file.endswith(".npz") and "lifted" in first.capabilities
    assert first.motions == ("breathing", "talking")


def test_without_the_vision_models_nothing_is_lifted(tmp_path: Path) -> None:
    Image.new("RGB", (8, 8)).save(tmp_path / "scene.png")
    library = Library(folder=tmp_path / "library")

    assert lifting.lifted(library, tmp_path / "scene.png", make=True) is None


def test_a_picture_shot_glides_from_the_pictures_camera_in_its_own_look(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, project_root: Path
) -> None:
    _scene(monkeypatch, tmp_path / "scene.png")
    config = load_config(project_root / "config/config.fake-video.json")
    engine = load_catalogue(None)
    library = Library(folder=tmp_path / "library", props=engine.library.props)
    catalogue = replace(engine, library=library)
    moves = config.theme.spec.staging.moves
    orbit = next((name for name, preset in moves.items() if preset.block == "orbit"), None)

    job = picture_job(
        "S1", tmp_path / "scene.png", orbit or "anything", config.theme, catalogue,
        seconds=4.0, quality="draft",
    )  # fmt: skip

    assert job.layout.block == "set" and job.look.block == PAINTED
    assert job.camera.block == "glide"
    assert float(job.camera.settings["lens"]) == pytest.approx(
        lifting.SENSOR_MM * FOCAL[1], abs=0.01
    )
    assert job.camera.settings["subject"] == "person_0"
    assert job.camera.settings["direction"] == ("round_left" if orbit else "right")
    assert check(job, catalogue) == []
    # Drawn the channel's way, it keeps the picture's own look.
    assert themed(job, config.theme).look.block == PAINTED


def test_past_any_depth_edge_the_far_side_is_carried_on_behind_the_near_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Something nearer that is not a person (a box before the wall): its blurred edge is
    snapped to a clean step, and behind its rim the wall carries on, at the wall's depth."""
    _scene(monkeypatch, tmp_path / "scene.png")
    monkeypatch.setattr(vision, "find", lambda image, phrases, threshold: [])
    shape = vision.geometry(tmp_path / "scene.png")
    blurred = shape.points.copy()
    ramp = np.linspace(PERSON, WALL, 5)
    left = int(BOX[0])
    blurred[int(BOX[1]) : int(BOX[3]), left - 2 : left + 3, 2] = ramp[::-1]
    monkeypatch.setattr(vision, "geometry", lambda image: vision.Geometry(blurred, FOCAL))

    arrays, parts, _, people = lifting.lift(tmp_path / "scene.png")

    camera = np.array(next(p for p in parts if p["name"] == "mark_camera")["at"])
    ground = arrays["ground"][..., 1] - camera[1]
    beyond = arrays["beyond"][..., 1] - camera[1]
    reach = arrays["beyond_reach"]
    assert people == 0
    assert set(np.round(np.unique(ground), 2)) <= {PERSON, WALL}  # no ramp left: a clean step
    assert reach.any() and np.allclose(beyond[reach], WALL, atol=0.01)
