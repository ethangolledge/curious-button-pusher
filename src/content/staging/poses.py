"""People's poses: stretches of real recorded motion, read once as the joints of a body frame by
frame (`blender/poses.py`) and kept in the library like any model, with their rights, so the
credit a recording asks for reaches the video. A person in a shot is one of these poses, placed
and fitted to the shot's furniture (`blender/body.py`), and drawn over the layout as a skeleton
for the image model to draw them from (`draw`). Everyone is posed and drawn the same way.

Sources: free animated characters on Sketchfab (CC BY: credited), the CMU motion capture
library (no restrictions) and 100STYLE (CC BY)."""

import hashlib
import json
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from content.blender.blocks.props.chair import SEAT_HEIGHT
from content.blender.body import (
    RECORDED_FPS,
    STANDARD_HEIGHT,
    Frame,
    extent,
    holds,
    placed,
    reached,
    reaches,
    recording,
    seated,
)
from content.blender.maths import Quat, Vec
from content.providers import motions as recordings
from content.providers.assets import Candidate, Sketchfab, licence_terms
from content.providers.blender import LocalBlender
from content.staging.library import Library, Model, Movement
from content.staging.store import Store

Source = Literal["sketchfab", "cmu", "100style"]


@dataclass(frozen=True)
class Clip:
    """A stretch of a recording (`start` to `end` seconds; 0 for its end), what it shows, and
    whether it loops (a walk). A Sketchfab take is a model's id; CMU's a take number; 100STYLE's
    a file."""

    source: Source
    take: str
    describe: str
    start: float = 0.0
    end: float = 0.0
    loop: bool = False


CLIPS: dict[str, Clip] = {
    "sit": Clip("sketchfab", "d8ca320050c6494581c34292356a280b", "a man sitting at ease"),
    "stand": Clip("sketchfab", "8401da7cb2564fc08681836cbeff39bc", "a man standing at ease"),
    "walk": Clip("sketchfab", "143a2b1ea5eb4385ae90a73657aca3bc", "a man walking", loop=True),
}
# The pose each way of being placed holds: a clip, and how far through it.
STANCES: dict[str, tuple[str, float]] = {
    "standing": ("stand", 0.3),
    "seated": ("sit", 0.5),
    "walking": ("walk", 0.25),
}
# Words for a thing that is a person, when a scene forgot to say so.
HUMAN = frozenset(
    {"person", "people", "man", "men", "woman", "women", "figure", "figures", "official",
     "officials", "guard", "guards", "aide", "aides", "crowd", "worker", "workers", "clerk",
     "banker", "lawyer", "politician", "minister", "delegate", "silhouette", "child"}
)  # fmt: skip
# The standing height a person is when the scene gives none.
USUAL_HEIGHT = {"man": 1.78, "woman": 1.65}
# The room a person takes in each pose before its clip is read (width, depth, height, and how
# far its middle is in front of where they stand), for someone of the standard height.
STAND_INS = {
    "standing": (0.62, 0.42, 1.8, -0.05),
    "seated": (0.62, 0.95, 1.4, -0.3),
    "walking": (0.62, 0.8, 1.8, -0.05),
}
# How poses are read (`blender/poses.py`): raised when that changes, so each is read again.
READER = 1
FPS = RECORDED_FPS
# The skeleton as it is drawn for the image model: OpenPose's limbs and colours, which pose
# models and image models were trained to read.
LIMBS: tuple[tuple[str, str, tuple[int, int, int]], ...] = (
    ("neck", "shoulder.R", (255, 0, 0)), ("neck", "shoulder.L", (255, 85, 0)),
    ("shoulder.R", "elbow.R", (255, 170, 0)), ("elbow.R", "wrist.R", (255, 255, 0)),
    ("shoulder.L", "elbow.L", (170, 255, 0)), ("elbow.L", "wrist.L", (85, 255, 0)),
    ("neck", "hip.R", (0, 255, 0)), ("hip.R", "knee.R", (0, 255, 85)),
    ("knee.R", "ankle.R", (0, 255, 170)), ("neck", "hip.L", (0, 255, 255)),
    ("hip.L", "knee.L", (0, 170, 255)), ("knee.L", "ankle.L", (0, 85, 255)),
    ("neck", "nose", (0, 0, 255)), ("nose", "eye.R", (85, 0, 255)),
    ("eye.R", "ear.R", (170, 0, 255)), ("nose", "eye.L", (255, 0, 255)),
    ("eye.L", "ear.L", (255, 0, 170)),
)  # fmt: skip
# Lines and joints are drawn this thick for a frame this many pixels high.
LINE, DOT, FOR_HEIGHT = 9, 6, 1920


def is_person(what: str) -> bool:
    """Whether a thing's words name a person (a scene that forgot to describe them)."""
    return bool(HUMAN & set(re.findall(r"[a-z]+", what.lower())))


def pose_id(name: str) -> str:
    """A pose clip's id in the library: a stretch taken or read differently is another clip."""
    made = json.dumps([asdict(CLIPS[name]), READER, FPS], sort_keys=True)
    return f"pose_{name}_{hashlib.sha256(made.encode()).hexdigest()[:6]}"


def clip(library: Library, name: str, *, make: bool) -> Model | None:
    """A pose clip from the library, read now if it is not there yet (when `make`: the
    recording downloaded and read in Blender, free), else None."""
    model_id = pose_id(name)
    if model_id in library.models:
        return library.models[model_id]
    if not make or library.folder is None:
        return None
    wanted = CLIPS[name]
    with tempfile.TemporaryDirectory() as work:
        try:
            source, rights = _fetched(wanted, Path(work))
        except Exception as exc:  # a source down, or no key for it: say which, briefly
            said = str(exc).split(" for url ")[0]
            raise ValueError(f"the '{name}' pose could not be fetched ({said})") from exc
        out = Path(work) / f"{name}.json"
        request = {"file": str(source), "start": wanted.start, "end": wanted.end,
                   "loop": wanted.loop, "fps": FPS}  # fmt: skip
        facts = LocalBlender().poses(request, out)
        kept = Store(library.folder).keep_file(out)
    model = Model(
        model_id=model_id,
        names=(f"{name} pose",),
        describe=f"{wanted.describe} ({rights.title})",
        size=(0.0, 0.0, 0.0),
        capabilities=("pose",),
        source=rights.source,
        licence=rights.licence,
        author=rights.author,
        page=rights.page,
        file=kept,
        movement=Movement(len(facts["frames"]), facts["seconds"], facts["speed"], wanted.loop),
    )
    library.save(model, "read", {**asdict(wanted), "reader": READER, "family": facts["family"]})
    return model


@dataclass(frozen=True)
class _Rights:
    source: str
    title: str
    licence: str
    author: str
    page: str


def _fetched(wanted: Clip, folder: Path) -> tuple[Path, _Rights]:
    """A clip's recording, downloaded, and the rights it comes with."""
    if wanted.source == "sketchfab":
        sketchfab = Sketchfab()
        about = sketchfab.about(wanted.take)
        licence = licence_terms(about["license"]["label"])
        if not licence:
            raise ValueError(f"{about['name']}: its licence does not allow it")
        candidate = Candidate("sketchfab", about["name"], about["viewerUrl"], wanted.take, "glb",
                              licence, about["user"]["username"])  # fmt: skip
        path = folder / "take.glb"
        path.write_bytes(sketchfab.download(candidate))
        rights = _Rights("Sketchfab", about["name"], licence, candidate.author, candidate.page)
        return path, rights
    take = recordings.fetch(wanted.source, wanted.take, folder)
    known = recordings.RIGHTS[wanted.source]
    return take, _Rights(known.source, wanted.take, known.licence, known.author, known.page)


@dataclass(frozen=True)
class Room:
    """The room a person takes, posed: their size (width, depth, height), where its middle is
    from where they stand (a seated person's knees reach forward of their hips), and where each
    thing they hold goes (its base), by name."""

    size: Vec
    middle: Vec
    holds: dict[str, Vec]


def room(library: Library, model: Model | None, pose: str, doing: str, height: float) -> Room:
    """The room a person takes in this pose, measured as a shot will pose them (at the engine's
    chair and the usual table: `body.py`), at their height; for a pose not read yet, the room
    of an average person that tall (enough to compose and check a shot)."""
    scale = height / STANDARD_HEIGHT
    if model is None or library.path(model) is None:
        w, d, h, ahead = STAND_INS[pose]
        return Room(Vec(w, d, h) * scale, Vec(0.0, ahead * scale, 0.0), {})
    path = library.path(model)
    assert path is not None
    clip = recording(path)
    figure = clip[round(STANCES[pose][1] * (len(clip) - 1))]
    turn = Quat()
    posed = placed(figure, Vec(), turn, scale)
    if pose == "seated":
        posed = seated(posed, SEAT_HEIGHT, 0.0, turn, scale)
    frame = Frame(posed.hips, 0.0, turn, scale)
    for hand in reaches(pose, doing, frame, None):
        posed = reached(posed, hand.side, hand.at, hand.elbow)
    box = extent(posed)
    middle = Vec(box.centre.x, box.centre.y, 0.0)
    return Room(box.size, middle, holds(pose, doing, frame, None))


def draw(picture: Path, skeletons: dict[str, dict[str, list[float]]], out: Path) -> Path:
    """The skeletons (each joint's place in the picture, in pixels) drawn over the picture in
    OpenPose's colours: what the image model draws each person's pose from."""
    from PIL import Image, ImageDraw

    image = Image.open(picture).convert("RGB")
    pen = ImageDraw.Draw(image)
    scale = image.height / FOR_HEIGHT
    line, dot = max(2, round(LINE * scale)), max(2, round(DOT * scale))
    for joints in skeletons.values():
        for a, b, colour in LIMBS:
            if a in joints and b in joints:
                pen.line([tuple(joints[a][:2]), tuple(joints[b][:2])], fill=colour, width=line)
        for x, y, *_ in joints.values():
            pen.ellipse([x - dot, y - dot, x + dot, y + dot], fill=(255, 255, 255))
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out)
    return out
