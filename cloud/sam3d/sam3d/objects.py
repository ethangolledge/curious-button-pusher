"""SAM 3D Objects: each masked thing in a picture made into a textured mesh (`.glb`), its
Gaussian splat (`.ply`), and where it sits in the picture's camera (`.json`). The calls are the
ones the authors' own `notebook/inference.py` makes, without its notebook and web-demo imports."""

import json
import os
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from sam3d.request import Item

REPO = "facebook/sam-3d-objects"
# The pipeline is built from the checkpoint's own config; only these packages' classes may be
# named in it (the authors' whitelist in notebook/inference.py).
ALLOWED = {"sam3d_objects", "torch", "torchvision", "moge"}


def load(revision: str) -> Any:
    os.environ["LIDRA_SKIP_INIT"] = "true"
    import sam3d_objects  # noqa: F401  (registers what the config names, as the authors note)
    from huggingface_hub import snapshot_download
    from hydra.utils import instantiate
    from omegaconf import OmegaConf

    folder = Path(snapshot_download(REPO, revision=revision, local_files_only=True)) / "checkpoints"
    config = OmegaConf.load(folder / "pipeline.yaml")
    config.rendering_engine = "pytorch3d"
    config.compile_model = False
    config.workspace_dir = str(folder)
    _check_targets(OmegaConf.to_container(config))
    return instantiate(config)


def run(pipeline: Any, item: Item, out: Path) -> dict[str, Any]:
    image = np.array(Image.open(item.image).convert("RGB"), dtype=np.uint8)
    made = []
    for index, mask_path in enumerate(item.masks):
        mask = np.array(Image.open(mask_path).convert("L")) > 127
        if mask.shape != image.shape[:2]:
            raise ValueError(f"{mask_path.name} is not the size of {item.image.name}")
        rgba = np.concatenate([image, (mask[..., None] * 255).astype(np.uint8)], axis=-1)
        output = pipeline.run(
            rgba,
            None,
            item.seed,
            stage1_only=False,
            with_mesh_postprocess=False,
            with_texture_baking=False,
            with_layout_postprocess=False,
            use_vertex_color=True,
            stage1_inference_steps=None,
            pointmap=None,
        )
        stem = out / f"{index}"
        output["glb"].export(f"{stem}.glb")
        output["gs"].save_ply(f"{stem}.ply")
        pose = {
            "mask": mask_path.name,
            "rotation_wxyz": _list(output["rotation"]),
            "translation": _list(output["translation"]),
            "scale": _list(output["scale"]),
        }
        Path(f"{stem}.json").write_text(json.dumps(pose, indent=2), encoding="utf-8")
        made.append(pose)
    return {"objects": made}


def _check_targets(node: object) -> None:
    if isinstance(node, dict):
        target = node.get("_target_")
        if target is not None and str(target).split(".", 1)[0] not in ALLOWED:
            raise ValueError(f"the checkpoint's config names {target!r}, outside {sorted(ALLOWED)}")
        for value in node.values():
            _check_targets(value)
    elif isinstance(node, list):
        for value in node:
            _check_targets(value)


def _list(tensor: Any) -> list[float]:
    return [float(v) for v in tensor.detach().cpu().reshape(-1)]
