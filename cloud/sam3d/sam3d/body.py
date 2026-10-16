"""SAM 3D Body: each person in a picture as a full-body mesh (`.glb`, in the picture's camera)
and its parameters (`.npz`: the MHR body, hand, shape and face parameters, 3D and 2D keypoints,
joints, camera translation and focal length). The people's boxes and the focal length come from
the client (the engine already finds people and measures the lens on the computer); without
boxes the whole picture is one person, without a focal length the model's default lens is used.
No detector, segmenter or lens model is loaded here."""

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from sam3d.request import Item

REPO = "facebook/sam-3d-body-dinov3"
KEEP = (
    "bbox", "focal_length", "pred_keypoints_3d", "pred_keypoints_2d", "pred_vertices",
    "pred_cam_t", "global_rot", "body_pose_params", "hand_pose_params", "scale_params",
    "shape_params", "expr_params", "pred_joint_coords", "pred_global_rots", "mhr_model_params",
)  # fmt: skip


def load(revision: str) -> Any:
    from huggingface_hub import snapshot_download
    from sam_3d_body import SAM3DBodyEstimator, load_sam_3d_body

    folder = Path(snapshot_download(REPO, revision=revision, local_files_only=True))
    model, config = load_sam_3d_body(
        str(folder / "model.ckpt"), device="cuda", mhr_path=str(folder / "assets/mhr_model.pt")
    )
    return SAM3DBodyEstimator(sam_3d_body_model=model, model_cfg=config)


def run(estimator: Any, item: Item, out: Path) -> dict[str, Any]:
    import torch
    import trimesh

    image = np.array(Image.open(item.image).convert("RGB"), dtype=np.uint8)
    height, width = image.shape[:2]
    cam_int = None
    if item.focal is not None:
        cam_int = torch.tensor(
            [[[item.focal, 0, width / 2], [0, item.focal, height / 2], [0, 0, 1]]],
            dtype=torch.float32,
        )
    boxes = np.array(item.boxes, dtype=np.float32) if item.boxes else None
    people = estimator.process_one_image(image, bboxes=boxes, cam_int=cam_int)
    faces = np.asarray(estimator.faces)
    for index, person in enumerate(people):
        stem = out / f"person_{index}"
        np.savez_compressed(f"{stem}.npz", faces=faces, **{k: np.asarray(person[k]) for k in KEEP})
        vertices = np.asarray(person["pred_vertices"]) + np.asarray(person["pred_cam_t"])
        trimesh.Trimesh(vertices, faces, process=False).export(f"{stem}.glb")
    return {"people": len(people)}
