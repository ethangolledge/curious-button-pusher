"""The SAM 3D cloud job's request: what the engine sends is what the container accepts, and
nothing in a request can reach outside its job's `in/` folder."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from content.providers import sam3d
from content.storage import LocalStore


def _container_request() -> ModuleType:
    path = Path(__file__).parents[1] / "cloud/sam3d/sam3d/request.py"
    spec = importlib.util.spec_from_file_location("sam3d_request", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up while being made
    spec.loader.exec_module(module)
    return module


request = _container_request()


def _job(tmp_path: Path, payload: object, files: tuple[str, ...] = ("a.png",)) -> Path:
    folder = tmp_path / "jobs" / "objects-1"
    (folder / "in").mkdir(parents=True)
    for name in files:
        (folder / "in" / name).write_bytes(b"\x89PNG")
    (folder / "request.json").write_text(json.dumps(payload), encoding="utf-8")
    return folder


def test_what_the_engine_sends_is_what_the_container_runs(tmp_path: Path) -> None:
    for name in ("room.png", "chair.png", "lamp.png", "people.jpg"):
        (tmp_path / name).write_bytes(b"\x89PNG")
    bucket = LocalStore(tmp_path / "bucket")
    seen: list[Any] = []

    def container(place: sam3d.Place, job_id: str) -> None:
        job = request.read(request.job_folder(bucket.root, job_id))
        seen.append(job)
        (job.outputs / "room").mkdir(parents=True)
        (job.outputs / "room" / "0.glb").write_bytes(b"glTF")
        (job.outputs / "result.json").write_text('{"model": "objects"}', encoding="utf-8")

    pictures = [
        sam3d.Picture(
            "room", tmp_path / "room.png", masks=(tmp_path / "chair.png", tmp_path / "lamp.png")
        )
    ]
    out = tmp_path / "out"
    result = sam3d.make(
        "objects", pictures, out, bucket=bucket, place=sam3d.Place("p", "r"), run=container
    )

    [job] = seen
    assert job.model == "objects"
    assert [mask.name for mask in job.items[0].masks] == ["room-mask-0.png", "room-mask-1.png"]
    assert (out / "room" / "0.glb").read_bytes() == b"glTF"
    assert result["model"] == "objects" and result["job"].startswith("objects-")

    body = [sam3d.Picture("crowd", tmp_path / "people.jpg", boxes=((1, 2, 30, 40),), focal=1200.0)]
    sam3d.make(
        "body", body, tmp_path / "out2", bucket=bucket, place=sam3d.Place("p", "r"), run=container
    )
    assert seen[1].items[0].boxes == ((1.0, 2.0, 30.0, 40.0),)
    assert seen[1].items[0].focal == 1200.0


@pytest.mark.parametrize(
    "image", ["../a.png", "/etc/passwd", "sub/a.png", "a.png/..", ".a.png", "a.exe", "a.png\n"]
)
def test_a_request_names_only_plain_pictures_in_its_own_folder(tmp_path: Path, image: str) -> None:
    folder = _job(
        tmp_path, {"model": "objects", "items": [{"name": "x", "image": image, "masks": ["a.png"]}]}
    )
    with pytest.raises(request.RequestError):
        request.read(folder)


def test_a_linked_file_is_refused(tmp_path: Path) -> None:
    folder = _job(
        tmp_path,
        {"model": "objects", "items": [{"name": "x", "image": "b.png", "masks": ["a.png"]}]},
    )
    (folder / "in" / "b.png").symlink_to(tmp_path / "secret.png")
    (tmp_path / "secret.png").write_bytes(b"x")
    with pytest.raises(request.RequestError, match="not found"):
        request.read(folder)


@pytest.mark.parametrize(
    "payload",
    [
        {"model": "shell", "items": [{"name": "x", "image": "a.png"}]},
        {"model": "body", "items": [{"name": "x", "image": "a.png", "masks": ["a.png"]}]},
        {"model": "body", "items": [{"name": "x", "image": "a.png", "extra": 1}]},
        {"model": "body", "items": [{"name": "x", "image": "a.png", "boxes": [[5, 5, 1, 1]]}]},
        {"model": "body", "items": [{"name": "x", "image": "a.png", "focal": True}]},
        {"model": "body", "items": [{"name": "../x", "image": "a.png"}]},
        {
            "model": "body",
            "items": [{"name": "x", "image": "a.png"}, {"name": "x", "image": "a.png"}],
        },
        {"model": "objects", "items": [{"name": "x", "image": "a.png"}]},
        {"model": "body", "items": []},
    ],
)
def test_anything_unexpected_is_refused_before_a_model_loads(
    tmp_path: Path, payload: object
) -> None:
    with pytest.raises(request.RequestError):
        request.read(_job(tmp_path, payload))


@pytest.mark.parametrize("job_id", ["../x", "X", "-x", "a/b", "a" * 64, ""])
def test_a_job_id_is_a_plain_name(tmp_path: Path, job_id: str) -> None:
    with pytest.raises(request.RequestError):
        request.job_folder(tmp_path, job_id)
