"""People's motions: stretches of free motion capture, retargeted once onto the skeleton every
person shares (`blender/retarget.py`) and kept in the library like any model, with their rights,
so every person moves alike and the credit a recording asks for reaches the video.

A motion gives a person their stance (the pose they hold when still: a frame of standing at
ease, of sitting, of mid-stride) and, walking, their stride (a loop played on the spot while
the shot carries them along at its pace, so their feet do not slide). What they do with their
hands is then reached for on the shot's own furniture (`blender/body.py`)."""

import hashlib
import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from content.providers import motions as recordings
from content.providers.blender import LocalBlender
from content.staging.library import Library, Model, Movement
from content.staging.store import Store


@dataclass(frozen=True)
class Clip:
    """A stretch of a recording (from `start` to `end`, in seconds), what it shows, and
    whether it loops (a walk is cut where it comes back to its first pose)."""

    source: recordings.Source
    take: str
    start: float
    end: float
    describe: str
    loop: bool = False


CLIPS: dict[str, Clip] = {
    "stand": Clip("100style", "Neutral/Neutral_ID.bvh", 8.0, 16.0, "standing at ease"),
    "walk": Clip(
        "100style", "Neutral/Neutral_FW.bvh", 10.0, 11.1, "walking at an easy pace", loop=True
    ),  # fmt: skip
    # The squarest moment of the take (shoulders over the hips, upright, level), measured.
    "sit": Clip("cmu", "113_15", 4.2, 4.6, "sitting upright on a chair"),
}
# The walk every person walks with as they travel.
WALK = "walk"
# The stance each pose holds: a motion, and how far through it.
STANCES: dict[str, tuple[str, float]] = {
    "standing": ("stand", 0.0),
    "seated": ("sit", 0.5),
    "walking": ("walk", 0.25),
}
# How motions are made (`blender/retarget.py`): raised when that changes, so each is made again.
RETARGETER = 1
FPS = 30


def motion_id(name: str) -> str:
    """A motion's id in the library, and the name of its action in its file: a stretch taken
    differently, or retargeted differently, is another motion."""
    made = json.dumps([asdict(CLIPS[name]), RETARGETER, FPS], sort_keys=True)
    return f"motion_{name}_{hashlib.sha256(made.encode()).hexdigest()[:6]}"


# Every pose's stance, as one word: a person is made again when any of them changes.
STANCES_MADE = "-".join(motion_id(name) for name, _ in STANCES.values())


def motion(library: Library, name: str, *, make: bool) -> Model | None:
    """A motion from the library, made now if it is not there yet (when `make`: the take
    downloaded, a few MB, and retargeted, a few seconds), else None."""
    model_id = motion_id(name)
    if model_id in library.models:
        return library.models[model_id]
    if not make or library.folder is None:
        return None
    clip = CLIPS[name]
    rights = recordings.RIGHTS[clip.source]
    store = Store(library.folder)
    with tempfile.TemporaryDirectory() as work:
        take = recordings.fetch(clip.source, clip.take, Path(work))
        file = Path(work) / f"{name}.blend"
        request = {"file": str(take), "skeleton": clip.source, "start": clip.start,
                   "end": clip.end, "loop": clip.loop, "name": model_id, "fps": FPS}  # fmt: skip
        facts = LocalBlender().retarget(request, file)
        kept = store.keep_file(file)
    model = Model(
        model_id=model_id,
        names=(f"{name} motion",),
        describe=f"{clip.describe} (motion capture, {clip.take})",
        size=(0.0, 0.0, 0.0),
        capabilities=("motion",),
        source=rights.source,
        licence=rights.licence,
        author=rights.author,
        page=rights.page,
        file=kept,
        movement=Movement(facts["frames"], facts["seconds"], facts["speed"], clip.loop),
    )
    library.save(model, "retargeted", {**asdict(clip), "retargeter": RETARGETER})
    return model


def stance(library: Library, pose: str, *, make: bool) -> tuple[Model, float] | None:
    """The motion a person in this pose stands as, and how far through it."""
    name, at = STANCES[pose]
    found = motion(library, name, make=make)
    return (found, at) if found is not None else None


def stance_files(library: Library) -> dict[str, list[object]]:
    """Every pose's stance as a person is made with it (`blender/person.py`): the motion's
    file, its name and how far through it; each made first if it is not there yet."""
    out: dict[str, list[object]] = {}
    for pose in STANCES:
        found = stance(library, pose, make=True)
        assert found is not None and library.folder is not None
        model, at = found
        out[pose] = [str(library.folder / model.file), model.model_id, at]
    return out


def describe(library: Library) -> str:
    """The motions the library holds, one a line."""
    lines = []
    for name, clip in CLIPS.items():
        model = library.models.get(motion_id(name))
        state = "ready" if model is not None else "not made yet"
        lines.append(f"{name:8} {clip.describe} ({clip.source} {clip.take}): {state}")
    return "\n".join(lines)
