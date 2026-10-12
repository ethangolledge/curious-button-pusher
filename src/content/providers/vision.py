"""Published vision models, run on this computer (the `vision` extra): each loaded once, each
answering with plain arrays. What they are and why each was chosen is in
`docs/picture-shots.md` and `docs/machine-learning.md`.

- Grounding DINO tiny (Apache-2.0): boxes for a phrase ("a person").
- SAM 2.1 (Apache-2.0): the outline inside each box.
- ViTPose (Apache-2.0): a person's 17 body points (COCO order).
- MoGe-2 (MIT): a point in metres for every pixel, and the picture's focal length.
- LaMa (Apache-2.0, as ONNX): a picture with a region painted in from its surroundings.

All run on the CPU here (a GPU when there is one). Without the extra installed, `ready()` is
False and nothing here is called."""

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np

DETECTOR = "IDEA-Research/grounding-dino-tiny"
OUTLINER = "facebook/sam2.1-hiera-large"
POSER = "usyd-community/vitpose-base-simple"
GEOMETRY = "Ruicheng/moge-2-vitl-normal"
FILLER = ("Carve/LaMa-ONNX", "lama_fp32.onnx")
# LaMa's fixed input size (pixels a side); holes this close together are painted as one, and
# a hole of fewer pixels than a speck is filled from its edges.
FILL_SIZE = 512
GROUP = 24
SPECK = 400
# MoGe-2's detail: tokens across the picture (its documented range is 1200 to 2500).
GEOMETRY_TOKENS = 2000
# COCO's 17 body points, the order ViTPose gives them in.
BODY = (
    "nose", "left_eye", "right_eye", "left_ear", "right_ear", "left_shoulder",
    "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist", "left_hip",
    "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle",
)  # fmt: skip


@dataclass(frozen=True)
class Found:
    """A box (left, top, right, bottom, in pixels) for a phrase, and how sure."""

    box: tuple[float, float, float, float]
    score: float
    label: str


@dataclass(frozen=True)
class Geometry:
    """Every pixel's point in metres, in the picture's camera (x right, y down, z ahead), and
    the focal length as a fraction of the picture's width and of its height."""

    points: np.ndarray  # (height, width, 3) float32
    focal: tuple[float, float]


def ready() -> bool:
    try:
        import moge  # noqa: F401
        import onnxruntime  # noqa: F401
        import transformers  # noqa: F401
    except ImportError:
        return False
    return True


def find(image: Path, phrases: str, *, threshold: float) -> list[Found]:
    """Boxes for `phrases` ("a person. a lamp.") in `image`, best first."""
    import torch
    from PIL import Image

    processor, model = _detector()
    picture = Image.open(image).convert("RGB")
    inputs = processor(images=picture, text=phrases, return_tensors="pt")
    with torch.no_grad():
        outputs = model(**inputs)
    found = processor.post_process_grounded_object_detection(
        outputs,
        inputs.input_ids,
        threshold=threshold,
        text_threshold=threshold,
        target_sizes=[picture.size[::-1]],
    )[0]
    boxes = [
        Found(tuple(box.tolist()), float(score), label)
        for box, score, label in zip(
            found["boxes"], found["scores"], found["text_labels"], strict=True
        )
    ]
    return sorted(boxes, key=lambda f: -f.score)


def outline(image: Path, boxes: list[tuple[float, float, float, float]]) -> np.ndarray:
    """A mask (count, height, width, bool) of what is inside each box."""
    import torch
    from PIL import Image

    processor, model = _outliner()
    picture = Image.open(image).convert("RGB")
    inputs = processor(images=picture, input_boxes=[[list(b) for b in boxes]], return_tensors="pt")
    with torch.no_grad():
        outputs = model(**inputs, multimask_output=False)
    masks = processor.post_process_masks(outputs.pred_masks.cpu(), inputs["original_sizes"])[0]
    return np.asarray(masks[:, 0].numpy(), dtype=bool)


def poses(image: Path, boxes: list[tuple[float, float, float, float]]) -> np.ndarray:
    """Each person's 17 body points (count, 17, 3): x and y in pixels, and how sure."""
    import torch
    from PIL import Image

    processor, model = _poser()
    picture = Image.open(image).convert("RGB")
    wide = [[left, top, right - left, bottom - top] for left, top, right, bottom in boxes]
    inputs = processor(picture, boxes=[wide], return_tensors="pt")
    with torch.no_grad():
        outputs = model(**inputs)
    found = processor.post_process_pose_estimation(outputs, boxes=[wide])[0]
    return np.array(
        [
            np.column_stack([person["keypoints"].numpy(), person["scores"].numpy()])
            for person in found
        ],
        dtype=np.float32,
    ).reshape(len(boxes), len(BODY), 3)


def geometry(image: Path) -> Geometry:
    import torch
    from PIL import Image

    model = _geometry()
    pixels = np.asarray(Image.open(image).convert("RGB"), dtype=np.float32) / 255
    with torch.no_grad():
        out = model.infer(
            torch.tensor(pixels).permute(2, 0, 1),
            num_tokens=GEOMETRY_TOKENS,
            use_fp16=torch.cuda.is_available(),
        )
    intrinsics = out["intrinsics"].cpu().numpy()
    return Geometry(
        points=out["points"].cpu().numpy().astype(np.float32),
        focal=(float(intrinsics[0, 0]), float(intrinsics[1, 1])),
    )


def fill(pixels: np.ndarray, hole: np.ndarray) -> np.ndarray:
    """`pixels` (height, width, 3, uint8) with `hole` (height, width, bool) painted in from
    around it; only the hole's pixels change. Each group of holes (those within `GROUP` pixels
    of each other) is painted in a square of its own at LaMa's size, so a small hole is filled
    as sharply as a large one; a speck is filled from its edges (OpenCV's Telea), which is as
    good there and far quicker."""
    import cv2

    if not hole.any():
        return pixels
    near = cv2.dilate(hole.astype(np.uint8), np.ones((GROUP, GROUP), np.uint8))
    count, groups = cv2.connectedComponents(near)
    out = pixels.copy()
    for label in range(1, count):
        part = hole & (groups == label)
        if part.sum() < SPECK:
            out = cv2.inpaint(out, part.astype(np.uint8), 5, cv2.INPAINT_TELEA)
        elif part.any():
            out = _painted(out, part)
    return out


def _painted(pixels: np.ndarray, hole: np.ndarray) -> np.ndarray:
    """One hole painted in by LaMa, seeing a square round it at its own size."""
    from PIL import Image

    rows, cols = np.nonzero(hole)
    height, width = hole.shape
    # A square round the hole, with as much again of its surroundings for context.
    side = int(max(np.ptp(rows), np.ptp(cols)) * 2) + 16
    side = min(side, max(height, width))
    top = int(np.clip((rows.min() + rows.max()) / 2 - side / 2, 0, max(height - side, 0)))
    left = int(np.clip((cols.min() + cols.max()) / 2 - side / 2, 0, max(width - side, 0)))
    crop = (slice(top, top + side), slice(left, left + side))
    region = Image.fromarray(pixels[crop]).resize((FILL_SIZE, FILL_SIZE), Image.Resampling.LANCZOS)
    gap = Image.fromarray(hole[crop].astype(np.uint8) * 255).resize(
        (FILL_SIZE, FILL_SIZE), Image.Resampling.NEAREST
    )
    image = (np.asarray(region, dtype=np.float32) / 255).transpose(2, 0, 1)[None]
    mask = (np.asarray(gap, dtype=np.float32) > 127).astype(np.float32)[None, None]
    painted = _filler().run(None, {"image": image, "mask": mask})[0][0].transpose(1, 2, 0)
    if painted.max() <= 1.0:  # some exports answer in 0 to 1, others in 0 to 255
        painted = painted * 255
    back = Image.fromarray(painted.clip(0, 255).astype(np.uint8)).resize(
        (pixels[crop].shape[1], pixels[crop].shape[0]), Image.Resampling.LANCZOS
    )
    out = pixels.copy()
    out[crop][hole[crop]] = np.asarray(back)[hole[crop]]
    return out


@cache
def _detector() -> tuple[Any, Any]:
    from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor

    return (
        AutoProcessor.from_pretrained(DETECTOR),  # type: ignore[no-untyped-call]
        AutoModelForZeroShotObjectDetection.from_pretrained(DETECTOR).eval(),
    )


@cache
def _outliner() -> tuple[Any, Any]:
    from transformers import Sam2Model, Sam2Processor

    return Sam2Processor.from_pretrained(OUTLINER), Sam2Model.from_pretrained(OUTLINER).eval()  # type: ignore[no-untyped-call]


@cache
def _poser() -> tuple[Any, Any]:
    from transformers import AutoProcessor, VitPoseForPoseEstimation

    return (
        AutoProcessor.from_pretrained(POSER),  # type: ignore[no-untyped-call]
        VitPoseForPoseEstimation.from_pretrained(POSER).eval(),  # type: ignore[no-untyped-call]
    )


@cache
def _geometry() -> Any:
    import torch
    from moge.model.v2 import MoGeModel

    device = "cuda" if torch.cuda.is_available() else "cpu"
    return MoGeModel.from_pretrained(GEOMETRY).to(device).eval()


@cache
def _filler() -> Any:
    import onnxruntime
    from huggingface_hub import hf_hub_download

    return onnxruntime.InferenceSession(
        hf_hub_download(*FILLER), providers=["CPUExecutionProvider"]
    )
