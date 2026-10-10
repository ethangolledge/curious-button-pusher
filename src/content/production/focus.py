"""Where the eye should land in a keyframe: the scene's named focus, found in the picture.

Grounding DINO (`IDEA-Research/grounding-dino-tiny`, a published open-vocabulary
detector) finds a short phrase in an image and returns its box. On a real storyboard it
found all eleven keyframes' subjects when each scene named its focus ("the woman at the
lectern"), against eight from the anchor's first clause, which often names the
room before the subject. A saliency guess drifted to bright edges, so it is not used
(docs/machine-learning.md).

It runs on the CPU in about nine seconds per keyframe; the producer caches every answer.
Without the optional `vision` extra installed, or when nothing is found, the camera aims
at the frame's centre, as it did before.
"""

from functools import cache
from pathlib import Path
from typing import Any, Literal

from content.schemas.base import ImmutableModel

DETECTOR = "IDEA-Research/grounding-dino-tiny"
# The detector's own confidence below which a box is not trusted.
MIN_SCORE = 0.2
# A person's face sits in the top third of their box.
FACE_HEIGHT = 1 / 3


class FocalPoint(ImmutableModel):
    """A point in the keyframe, as fractions of its width and height."""

    x: float
    y: float
    score: float | None = None
    source: Literal["detector", "centre"]


CENTRE = FocalPoint(x=0.5, y=0.5, source="centre")


def find(image: Path, phrase: str, *, person: bool) -> FocalPoint:
    """The best box for `phrase` in `image`: its centre, or a person's face."""
    detector = _detector()
    if detector is None or not phrase.strip():
        return CENTRE
    import torch
    from PIL import Image

    processor, model = detector
    picture = Image.open(image).convert("RGB")
    text = phrase.strip().lower().rstrip(".") + "."
    inputs = processor(images=picture, text=text, return_tensors="pt")
    with torch.no_grad():
        outputs = model(**inputs)
    found = processor.post_process_grounded_object_detection(
        outputs,
        inputs.input_ids,
        threshold=MIN_SCORE,
        text_threshold=MIN_SCORE,
        target_sizes=[picture.size[::-1]],
    )[0]
    if not len(found["scores"]):
        return CENTRE
    best = int(found["scores"].argmax())
    left, top, right, bottom = found["boxes"][best].tolist()
    height = (bottom - top) * FACE_HEIGHT if person else (bottom - top) / 2
    return FocalPoint(
        x=round((left + right) / 2 / picture.width, 3),
        y=round((top + height) / picture.height, 3),
        score=round(float(found["scores"][best]), 2),
        source="detector",
    )


@cache
def _detector() -> tuple[Any, Any] | None:
    try:
        from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
    except ImportError:
        return None
    return (
        AutoProcessor.from_pretrained(DETECTOR),  # type: ignore[no-untyped-call]
        AutoModelForZeroShotObjectDetection.from_pretrained(DETECTOR).eval(),
    )
