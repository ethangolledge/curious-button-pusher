"""How sure we are that a model is the thing asked for, judged by eye on this computer: a
CLIP model (an open model that matches pictures with words) looks at the model drawn on the
studio plinth and weighs "a 3D model of <the thing>" against a fixed set of other things.
The score is how much of its belief goes to the thing: near 1 when it plainly is one, low
when the picture looks more like something else, or like nothing.

Free and local (the `vision` extra; the model, about 600 MB, is fetched once). Without it,
nothing is taken automatically: candidates wait for a person to pick."""

from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any

MODEL = "openai/clip-vit-base-patch32"
# What a picture is weighed against: everyday things, and the ways a download goes wrong.
OTHERS = (
    "a chair", "a table", "a car", "a person", "a building", "a tree", "a box", "a bottle",
    "a lamp", "a book", "a phone", "a cup", "a bag", "a sofa", "a bed", "a door",
    "an animal", "a weapon", "a computer", "a plant", "a toy", "a sculpture", "a vehicle",
    "a piece of furniture", "a tool", "a rock", "a shoe", "a hat", "a sign", "a ship",
    "a blank background", "a broken 3D model", "an abstract shape", "a texture",
)  # fmt: skip
# A model is taken automatically from this score.
ACCEPT = 0.5

Scorer = Callable[[Path, str], float]


def clip_scorer() -> Scorer | None:
    """The scorer, or None when the vision extra is not installed."""
    if _clip() is None:
        return None
    return score


def score(picture: Path, what: str) -> float:
    """How much of CLIP's belief about the picture goes to `what` rather than to anything
    else (other things that share a word with it are left out: a mug is not marked down for
    looking like a cup)."""
    loaded = _clip()
    assert loaded is not None
    processor, model = loaded
    import torch
    from PIL import Image

    asked = set(what.lower().split())
    others = [o for o in OTHERS if not asked & set(o.split()[1:])]
    texts = [f"a 3D model of {what}", *(f"a 3D model of {o}" for o in others)]
    with Image.open(picture) as image:
        inputs = processor(text=texts, images=image.convert("RGB"), return_tensors="pt",
                           padding=True)  # fmt: skip
    with torch.no_grad():
        logits = model(**inputs).logits_per_image[0]
    return round(float(logits.softmax(dim=0)[0]), 3)


@cache
def _clip() -> tuple[Any, Any] | None:
    try:
        from transformers import CLIPModel, CLIPProcessor
    except ImportError:
        return None
    return (
        CLIPProcessor.from_pretrained(MODEL),
        CLIPModel.from_pretrained(MODEL).eval(),  # type: ignore[no-untyped-call]
    )
