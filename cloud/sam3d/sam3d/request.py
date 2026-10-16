"""What a job asks for, checked before anything is loaded. Standard library only, so the engine's
tests can check it without the models.

A job is a folder in the work bucket, `jobs/<id>/`: the client puts the pictures in `in/` and
`request.json` beside them; the container writes into `out/` and finishes with
`out/result.json`. Everything a request names is a plain file name inside `in/`: nothing
in a request can point the container anywhere else."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

JOB_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
FILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.(png|jpg|jpeg)$")
MODELS = ("objects", "body")
# A job is one GPU start, so every picture of a run goes in one; these bound a mistaken one.
MAX_ITEMS = 64
MAX_MASKS = 32
MAX_BOXES = 16
MAX_FILE_BYTES = 40 * 1024 * 1024
MAX_PIXELS = 4096 * 4096


class RequestError(ValueError):
    """The request is not one the container will run."""


@dataclass(frozen=True)
class Item:
    name: str
    image: Path
    masks: tuple[Path, ...] = ()
    boxes: tuple[tuple[float, float, float, float], ...] = ()
    focal: float | None = None
    seed: int = 42


@dataclass(frozen=True)
class Request:
    model: str
    items: tuple[Item, ...]
    inputs: Path
    outputs: Path


def job_folder(work: Path, job_id: str) -> Path:
    if not JOB_ID.fullmatch(job_id):
        raise RequestError(f"job id {job_id!r}: lower-case letters, digits and hyphens only")
    return work / "jobs" / job_id


def read(folder: Path) -> Request:
    """The job's request, every file it names checked to be a plain file in `in/`."""
    inputs = folder / "in"
    try:
        data = json.loads((folder / "request.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RequestError(f"request.json: {exc}") from exc
    _keys(data, {"model", "items"}, "request")
    model = data["model"]
    if model not in MODELS:
        raise RequestError(f"model {model!r}: one of {', '.join(MODELS)}")
    raw_items = data["items"]
    if not isinstance(raw_items, list) or not 1 <= len(raw_items) <= MAX_ITEMS:
        raise RequestError(f"items: a list of 1 to {MAX_ITEMS}")
    items = tuple(_item(raw, model, inputs) for raw in raw_items)
    if len({item.name for item in items}) != len(items):
        raise RequestError("items: every name must be different")
    return Request(model, items, inputs, folder / "out")


def _item(raw: object, model: str, inputs: Path) -> Item:
    allowed = {"name", "image", "seed"} | ({"masks"} if model == "objects" else {"boxes", "focal"})
    _keys(raw, allowed, "item", required={"name", "image"})
    assert isinstance(raw, dict)
    name = raw["name"]
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise RequestError(f"item name {name!r}: letters, digits, '_' and '-', up to 64")
    seed = raw.get("seed", 42)
    if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < 2**31:
        raise RequestError(f"{name}: seed must be a whole number from 0")
    masks = raw.get("masks", [])
    if model == "objects" and (not isinstance(masks, list) or not 1 <= len(masks) <= MAX_MASKS):
        raise RequestError(f"{name}: masks must list 1 to {MAX_MASKS} pictures, one per thing")
    boxes = raw.get("boxes", [])
    if not isinstance(boxes, list) or len(boxes) > MAX_BOXES:
        raise RequestError(f"{name}: boxes must list up to {MAX_BOXES} [x0, y0, x1, y1]")
    focal = raw.get("focal")
    if focal is not None and not (_number(focal) and 0 < focal < 1e6):
        raise RequestError(f"{name}: focal is the focal length in pixels")
    return Item(
        name=name,
        image=_file(inputs, raw["image"]),
        masks=tuple(_file(inputs, mask) for mask in masks),
        boxes=tuple(_box(box, name) for box in boxes),
        focal=float(focal) if focal is not None else None,
        seed=seed,
    )


def _file(inputs: Path, name: object) -> Path:
    if not isinstance(name, str) or not FILE.fullmatch(name):
        raise RequestError(f"file {name!r}: a plain .png or .jpg name inside in/")
    path = inputs / name
    if path.is_symlink() or not path.is_file():
        raise RequestError(f"{name}: not found in in/")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise RequestError(f"{name}: larger than {MAX_FILE_BYTES // 2**20} MB")
    return path


def _box(box: object, name: str) -> tuple[float, float, float, float]:
    if not (isinstance(box, list) and len(box) == 4 and all(_number(v) for v in box)):
        raise RequestError(f"{name}: a box is [x0, y0, x1, y1] in pixels")
    x0, y0, x1, y1 = (float(v) for v in box)
    if not (0 <= x0 < x1 and 0 <= y0 < y1):
        raise RequestError(f"{name}: box {box} is empty or outside the picture")
    return x0, y0, x1, y1


def _number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _keys(raw: object, allowed: set[str], what: str, required: set[str] | None = None) -> None:
    if not isinstance(raw, dict):
        raise RequestError(f"{what}: an object")
    unknown = set(raw) - allowed
    missing = (allowed if required is None else required) - set(raw)
    if unknown or missing:
        raise RequestError(f"{what}: unknown {sorted(unknown)}, missing {sorted(missing)}")
