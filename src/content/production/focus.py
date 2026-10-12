"""Where the eye should land in a keyframe: the scene's named focus, found in the picture.

Grounding DINO (`providers/vision.py`, a published open-vocabulary detector) finds a short
phrase in an image and returns its box. On a real storyboard it found all eleven keyframes'
subjects when each scene named its focus ("the woman at the lectern"), against eight from the
anchor's first clause, which often names the room before the subject. A saliency guess drifted
to bright edges, so it is not used (docs/machine-learning.md).

It runs on the CPU in about nine seconds per keyframe; the producer caches every answer.
Without the optional `vision` extra installed, or when nothing is found, the camera aims
at the frame's centre, as it did before.
"""

from pathlib import Path
from typing import Literal

from content.providers import vision
from content.schemas.base import ImmutableModel

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
    if not vision.ready() or not phrase.strip():
        return CENTRE
    from PIL import Image

    found = vision.find(image, phrase.strip().lower().rstrip(".") + ".", threshold=MIN_SCORE)
    if not found:
        return CENTRE
    width, height = Image.open(image).size
    left, top, right, bottom = found[0].box
    down = (bottom - top) * FACE_HEIGHT if person else (bottom - top) / 2
    return FocalPoint(
        x=round((left + right) / 2 / width, 3),
        y=round((top + down) / height, 3),
        score=round(found[0].score, 2),
        source="detector",
    )
