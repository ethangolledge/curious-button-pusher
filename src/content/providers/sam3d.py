"""SAM 3D Objects and SAM 3D Body, run on a GPU in Google Cloud (cloud/sam3d/README.md).

One call is one job: every picture goes up to the work bucket together, the `sam3d-run`
Cloud Run job runs once over all of them (one GPU start, paid by the second), and everything it
made comes back into a folder here. The job reads only what the request names; the bucket
deletes a job's files after 7 days."""

import json
import os
import secrets
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

JOB = "sam3d-run"
# A job that has not finished in this long is stuck; the job's own limit is an hour.
WAIT_SECONDS = 2 * 60 * 60

Model = Literal["objects", "body"]


class Bucket(Protocol):
    def upload(self, name: str, source: Path, content_type: str) -> None: ...
    def download(self, name: str, target: Path) -> None: ...
    def names(self, prefix: str) -> list[str]: ...


@dataclass(frozen=True)
class Place:
    project: str
    region: str


def from_environment() -> tuple[Place, str] | None:
    """Where the job runs and its work bucket, from `.env` (cloud/sam3d/setup.sh prints them);
    None when they are not set."""
    project, region, bucket = (
        os.environ.get(f"SAM3D_{n}") for n in ("PROJECT", "REGION", "BUCKET")
    )
    if not (project and region and bucket):
        return None
    return Place(project, region), bucket


@dataclass(frozen=True)
class Picture:
    """One picture, and what to make from it: a mask per thing (objects), or the people's boxes
    and the lens in pixels (body; both optional)."""

    name: str
    image: Path
    masks: tuple[Path, ...] = ()
    boxes: tuple[tuple[float, float, float, float], ...] = ()
    focal: float | None = None


def run_job(place: Place, job_id: str) -> None:
    """Start the job on this request and wait for it to end."""
    done = subprocess.run(
        ["gcloud", "run", "jobs", "execute", JOB, f"--args=run,{job_id}", "--wait", "--quiet",
         f"--region={place.region}", f"--project={place.project}"],
        capture_output=True, text=True, timeout=WAIT_SECONDS,
    )  # fmt: skip
    if done.returncode != 0:
        raise RuntimeError(f"the {JOB} job failed: {done.stderr.strip()[-2000:]}")


def make(
    model: Model,
    pictures: list[Picture],
    out: Path,
    *,
    bucket: Bucket,
    place: Place,
    run: Callable[[Place, str], None] = run_job,
) -> dict[str, Any]:
    """Run `model` on every picture; the results land in `out/<picture name>/`."""
    job_id = f"{model}-{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"
    prefix = f"jobs/{job_id}"
    items = []
    for picture in pictures:
        image = f"{picture.name}{picture.image.suffix.lower()}"
        bucket.upload(f"{prefix}/in/{image}", picture.image, _content_type(picture.image))
        item: dict[str, Any] = {"name": picture.name, "image": image}
        if model == "objects":
            item["masks"] = []
            for index, mask in enumerate(picture.masks):
                name = f"{picture.name}-mask-{index}{mask.suffix.lower()}"
                bucket.upload(f"{prefix}/in/{name}", mask, _content_type(mask))
                item["masks"].append(name)
        else:
            if picture.boxes:
                item["boxes"] = [list(box) for box in picture.boxes]
            if picture.focal is not None:
                item["focal"] = picture.focal
        items.append(item)
    with tempfile.TemporaryDirectory() as scratch:
        request = Path(scratch) / "request.json"
        request.write_text(json.dumps({"model": model, "items": items}, indent=2), encoding="utf-8")
        bucket.upload(f"{prefix}/request.json", request, "application/json")
    run(place, job_id)
    for name in bucket.names(f"{prefix}/out/"):
        target = out / name.removeprefix(f"{prefix}/out/")
        if not target.resolve().is_relative_to(out.resolve()):
            raise RuntimeError(f"job {job_id} wrote {name}, outside its out/ folder")
        target.parent.mkdir(parents=True, exist_ok=True)
        bucket.download(name, target)
    if not (out / "result.json").is_file():
        raise RuntimeError(f"job {job_id} ended without a result: see its logs in the console")
    result: dict[str, Any] = json.loads((out / "result.json").read_text(encoding="utf-8"))
    result["job"] = job_id
    return result


def _content_type(path: Path) -> str:
    return "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
