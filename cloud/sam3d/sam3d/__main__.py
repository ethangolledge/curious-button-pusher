"""The container's one entry point; the Cloud Run job's arguments choose what it does:

  run <job-id>   read jobs/<job-id>/request.json from the work bucket (mounted at /work), run the
                 model it names on every picture, write jobs/<job-id>/out/
  fetch          copy the pinned weights from Hugging Face into the weights bucket (fetch.py)
  check          at build time: everything the models import is installed (no GPU needed)

The weights bucket is mounted read-only at /weights and holds Hugging Face's cache layout, so
the models load with the network off (HF_HUB_OFFLINE in the image)."""

import json
import sys
import time
import traceback
from pathlib import Path

from sam3d import request

WORK = Path("/work")
# The model code fetches these backbones' code from GitHub through torch.hub; the image holds
# them at pinned commits instead (Dockerfile).
HUB = {"facebookresearch/dinov2": "/opt/hub/dinov2", "facebookresearch/dinov3": "/opt/hub/dinov3"}
PINS = json.loads((Path(__file__).parents[1] / "models.json").read_text(encoding="utf-8"))


def main(arguments: list[str]) -> int:
    match arguments:
        case ["run", job_id]:
            return run(request.job_folder(WORK, job_id))
        case ["fetch"]:
            from sam3d import fetch

            fetch.main()
            return 0
        case ["check"]:
            return check()
    print(__doc__, file=sys.stderr)
    return 2


def run(folder: Path) -> int:
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = request.MAX_PIXELS
    started = time.monotonic()
    try:
        job = request.read(folder)
    except request.RequestError as exc:
        _finish(folder / "out", {"error": str(exc)})
        return 1
    _offline()
    if job.model == "objects":
        from sam3d import objects as model
    else:
        from sam3d import body as model  # type: ignore[no-redef]
    loaded = model.load(PINS[model.REPO]["revision"])
    print(f"{job.model} loaded in {time.monotonic() - started:.0f} s", flush=True)
    results = {}
    for item in job.items:
        out = job.outputs / item.name
        out.mkdir(parents=True, exist_ok=True)
        began = time.monotonic()
        try:
            results[item.name] = model.run(loaded, item, out)
        except Exception as exc:  # one picture failing does not lose the others' work
            traceback.print_exc()
            results[item.name] = {"error": f"{type(exc).__name__}: {exc}"}
        results[item.name]["seconds"] = round(time.monotonic() - began, 1)
        print(f"{item.name}: {results[item.name]}", flush=True)
    failed = sum("error" in result for result in results.values())
    _finish(
        job.outputs,
        {"model": job.model, "items": results, "seconds": round(time.monotonic() - started, 1)},
    )
    return 1 if failed == len(results) else 0


def _offline() -> None:
    """A run reads only the image and the two buckets. Anything that still tries the internet
    fails in seconds (the job has no route out), not after minutes of paid waiting."""
    import socket

    import torch

    socket.setdefaulttimeout(10)
    load = torch.hub.load

    def from_image(
        repo_or_dir: str, model: str, *args: object, source: str = "github", **kwargs: object
    ) -> object:
        if source == "github":
            repo = repo_or_dir.split(":")[0]
            if repo not in HUB:
                raise RuntimeError(f"torch.hub wants {repo}, which is not in the image (HUB)")
            repo_or_dir, source = HUB[repo], "local"
        return load(repo_or_dir, model, *args, source=source, **kwargs)

    torch.hub.load = from_image


def check() -> int:
    """Import all the models need, so a missing package fails the build, not a paid run."""
    import os

    os.environ["LIDRA_SKIP_INIT"] = "true"
    import gsplat  # noqa: F401
    import kaolin  # noqa: F401
    import moge.model.v1  # noqa: F401
    import pytorch3d.renderer  # noqa: F401
    import sam3d_objects.pipeline.inference_pipeline_pointmap  # noqa: F401
    import spconv.pytorch  # noqa: F401
    import trimesh  # noqa: F401
    from google.cloud import storage  # noqa: F401
    from sam_3d_body import SAM3DBodyEstimator, load_sam_3d_body  # noqa: F401

    print("every import the models need is installed")
    return 0


def _finish(out: Path, result: dict[str, object]) -> None:
    """`result.json` is written last: the client waits for it."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
