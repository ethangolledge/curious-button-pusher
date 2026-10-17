"""People's poses: stretches of real recorded motion, read once as the joints of a body frame by
frame (`blender/poses.py`) and kept in the library like any model, with their rights, so the
credit a recording asks for reaches the video. A person in a shot is one of these poses, placed
and fitted to the shot's furniture (`blender/body.py`), and drawn over the layout as a skeleton
for the image model to draw them from (`draw`). Everyone is posed and drawn the same way.

Sources: free animated characters on Sketchfab (CC BY: credited), the CMU motion capture
library (no restrictions) and 100STYLE (CC BY)."""

import hashlib
import json
import math
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from content.blender.api import Figure
from content.blender.blocks.props.chair import SEAT_HEIGHT
from content.blender.body import (
    JOINTS,
    RECORDED_FPS,
    STANDARD_HEIGHT,
    Frame,
    extent,
    holds,
    pace,
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
# What makes a moment of a recording seated or standing: the middle of the hips this low
# (metres, at the standard height) with the thighs within so much of level and the knees
# so far ahead of the hips; or this high with both legs straighter than so many degrees.
SEATED_HIPS, SEATED_THIGH, SEATED_KNEE = 0.7, 0.2, 0.2
STANDING_HIPS, STRAIGHT = 0.8, 160.0
# How far a person may lean, tilt and turn and still look quiet and natural (degrees): seated
# people lean back a little; the head looks a little down; a fault is anything past these.
SEATED_LEAN, STANDING_LEAN, LEVEL = 12.0, 6.0, 4.0
LOOK_UP, LOOK_DOWN, TURNED, TWIST = 3.0, 25.0, 15.0, 10.0
# Crossed legs count as this many degrees of fault (a pose to place anyone in is neutral).
CROSSED = 15.0
# How far out to its side a hand may be from its shoulder (metres) before the arms are out, as
# in the T-pose a recording often starts in to calibrate its skeleton; past it, a centimetre is
# a degree of fault.
ARMS_OUT = 0.25
# A plausible body: each limb's upper bone between these shares of its lower one, and the
# shoulders between these shares of the torso (neck to hips).
PROPORTION, SHOULDERS = (0.7, 1.45), (0.4, 1.1)
# A face's size (metres at the standard height): the neck to the nose, and ear to ear, at most.
FACE_SIZE = (0.08, 0.35)
# A clip taken for a pose is marked `stance:<pose>`; a walk is posed this far through its loop.
STANCE, TAKEN_WALK = "stance:", 0.25
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


def chosen(library: Library, pose: str, variant: int, *, make: bool) -> tuple[Model | None, float]:
    """The pose clip a person in this pose is posed from, and how far through it: one of the
    clips taken for the pose (`take`), the `variant`th in turn, so a group is not one man
    repeated; or, with none taken, the engine's own (`STANCES`, read now when `make`)."""
    taken = sorted(
        (m for m in library.models.values() if f"{STANCE}{pose}" in m.capabilities and m.file),
        key=lambda m: m.model_id,
    )
    if taken:
        model = taken[variant % len(taken)]
        return model, (TAKEN_WALK if pose == "walking" else 0.0)
    name, at = STANCES[pose]
    return clip(library, name, make=make), at


def take(
    library: Library,
    figures: list[Figure],
    pose: str,
    *,
    name: str,
    rights: dict[str, str],
    fps: float = RECORDED_FPS,
) -> Model:
    """A moment (sitting, standing) or a walking loop of a recording, kept as one of the clips
    a person in this pose is posed from (`chosen`), with the recording's rights: `figures` as
    written (`blender/poses.py`); a walk is cut to one clean loop and its pace kept."""
    assert library.folder is not None
    if pose == "walking":
        figures = loop(figures)
    speed = pace(figures, 1 / fps) if pose == "walking" else 0.0
    model_id = f"pose_{pose}_{re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')}"[:64]
    frames = [[[round(c, 4) for c in f.joints[j].tuple()] for j in JOINTS] for f in figures]
    with tempfile.TemporaryDirectory() as work:
        out = Path(work) / f"{model_id}.json"
        out.write_text(json.dumps({
            "fps": fps, "seconds": round(len(figures) / fps, 3), "speed": round(speed, 3),
            "loop": pose == "walking", "frames": frames,
        }))  # fmt: skip
        kept = Store(library.folder).keep_file(out)
    model = Model(
        model_id=model_id,
        names=(f"{pose} pose", name),
        describe=f"{name}, {pose}",
        size=(0.0, 0.0, 0.0),
        capabilities=("pose", f"{STANCE}{pose}"),
        source=rights["source"],
        licence=rights["licence"],
        author=rights.get("author", ""),
        page=rights.get("page", ""),
        file=kept,
        movement=Movement(len(figures), round(len(figures) / fps, 3), speed, pose == "walking"),
    )
    library.save(model, "taken", {"pose": pose, "frames": len(figures)})
    return model


def loop(figures: list[Figure]) -> list[Figure]:
    """The shortest stretch of a walk that comes back to how it began (two steps): the frame
    count, between half a second and two, where the body is posed most nearly as at the
    start (its hips' place over the ground left out)."""

    def apart(a: Figure, b: Figure) -> float:
        shift_a, shift_b = a.hips.flat(), b.hips.flat()
        return sum(((a.joints[n] - shift_a) - (b.joints[n] - shift_b)).length() for n in a.joints)

    lengths = range(int(RECORDED_FPS * 0.5), min(len(figures), int(RECORDED_FPS * 2)))
    if not lengths:
        return figures
    gaps = {n: apart(figures[0], figures[n]) for n in lengths}
    # The shortest that comes back as nearly as any (a longer one is the same loop again).
    closest = min(gaps.values())
    return figures[: next(n for n in lengths if gaps[n] <= closest * 1.05 + 1e-6)]


@dataclass(frozen=True)
class Room:
    """The room a person takes, posed: their size (width, depth, height), where its middle is
    from where they stand (a seated person's knees reach forward of their hips), and where each
    thing they hold goes (its base), by name."""

    size: Vec
    middle: Vec
    holds: dict[str, Vec]


def room(
    library: Library, model: Model | None, pose: str, doing: str, height: float, at: float
) -> Room:
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
    figure = clip[round(at * (len(clip) - 1))]
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


@dataclass(frozen=True)
class Judged:
    """What one moment of a recording is (`seated`, `standing`, or `other`), whether its body is
    plausibly a person's (bones in proportion, nothing under the floor), and how far it is from
    a quiet, natural way of being (each fault in degrees past what is natural; 0 is none)."""

    kind: str
    plausible: bool
    faults: dict[str, float]

    @property
    def score(self) -> float:
        """Lower is better: the faults added up (an implausible body never ranks)."""
        return sum(self.faults.values()) if self.plausible else math.inf


def judged(figure: Figure) -> Judged:
    """One moment of a recording, judged as a pose to place a person in (as written: facing
    −Y, at the standard height). Measured, never guessed: what would make a person look
    strange in a picture (leaning, a tilted head, a twisted chest, arms raised or held out,
    crossed legs)."""
    j = figure.joints
    hips, neck = figure.hips, j["neck"]
    plausible = _plausible(figure)
    thighs_flat = all(abs(j[f"knee.{s}"].z - j[f"hip.{s}"].z) < SEATED_THIGH for s in "LR")
    knees_ahead = all(j[f"knee.{s}"].y < j[f"hip.{s}"].y - SEATED_KNEE for s in "LR")
    straight = all(_angle(j[f"hip.{s}"], j[f"knee.{s}"], j[f"ankle.{s}"]) > STRAIGHT for s in "LR")
    kind = (
        "seated" if hips.z < SEATED_HIPS and thighs_flat and knees_ahead
        else "standing" if hips.z > STANDING_HIPS and straight
        else "other"
    )  # fmt: skip
    spine = neck - hips
    lean = math.degrees(math.atan2(math.hypot(spine.x, spine.y), spine.z))
    across = j["shoulder.L"] - j["shoulder.R"]
    tilt = math.degrees(math.atan2(abs(across.z), math.hypot(across.x, across.y)))
    ears = j["ear.L"].lerp(j["ear.R"], 0.5)
    look = j["nose"] - ears
    pitch = math.degrees(math.atan2(look.z, math.hypot(look.x, look.y)))
    facing = across.cross(Vec(0.0, 0.0, 1.0)).flat().normalised()
    turn = math.degrees(math.acos(max(-1.0, min(1.0, look.flat().normalised().dot(facing)))))
    hips_across = (j["hip.L"] - j["hip.R"]).flat().normalised()
    twist = math.degrees(
        math.acos(max(-1.0, min(1.0, across.flat().normalised().dot(hips_across))))
    )
    raised = sum(max(0.0, j[f"wrist.{s}"].z - j[f"shoulder.{s}"].z) for s in "LR") * 100
    side = across.flat().normalised()
    out = (
        sum(
            max(0.0, (j[f"wrist.{s}"] - j[f"shoulder.{s}"]).dot(side) * sign - ARMS_OUT)
            for s, sign in (("L", 1.0), ("R", -1.0))
        )
        * 100
    )
    crossed = 1.0 if j["knee.L"].x < j["knee.R"].x or j["ankle.L"].x < j["ankle.R"].x else 0.0
    natural_lean = SEATED_LEAN if kind == "seated" else STANDING_LEAN
    faults = {
        "lean": max(0.0, lean - natural_lean),
        "shoulders": max(0.0, tilt - LEVEL),
        "looks up": max(0.0, pitch - LOOK_UP),
        "looks down": max(0.0, -pitch - LOOK_DOWN),
        "head turned": max(0.0, turn - TURNED),
        "twisted": max(0.0, twist - TWIST),
        "arms raised": raised,
        "arms out": out,
        "legs crossed": crossed * CROSSED,
    }
    return Judged(kind, plausible, {name: round(v, 1) for name, v in faults.items() if v > 0})


def _plausible(figure: Figure) -> bool:
    """Whether a pose is a person's body: each limb's two bones in proportion, the shoulders
    as wide as a body, the head above the hips, nothing under the floor."""
    j = figure.joints
    for side in "LR":
        thigh, shin = (
            (j[f"hip.{side}"] - j[f"knee.{side}"]).length(),
            (j[f"knee.{side}"] - j[f"ankle.{side}"]).length(),
        )
        upper, fore = (
            (j[f"shoulder.{side}"] - j[f"elbow.{side}"]).length(),
            (j[f"elbow.{side}"] - j[f"wrist.{side}"]).length(),
        )
        if not (PROPORTION[0] < thigh / max(shin, 1e-6) < PROPORTION[1]):
            return False
        if not (PROPORTION[0] < upper / max(fore, 1e-6) < PROPORTION[1]):
            return False
    torso = (j["neck"] - figure.hips).length()
    width = (j["shoulder.L"] - j["shoulder.R"]).length()
    floor = min(point.z for point in j.values())
    # A face its own size: the nose a head's length from the neck, the ears beside it.
    head = (j["nose"] - j["neck"]).length()
    ears = (j["ear.L"] - j["ear.R"]).length()
    return (
        SHOULDERS[0] < width / max(torso, 1e-6) < SHOULDERS[1]
        and floor > -0.05
        and j["nose"].z > figure.hips.z
        and FACE_SIZE[0] < head < FACE_SIZE[1]
        and ears < FACE_SIZE[1]
    )


def jitter(figures: list[Figure]) -> float:
    """How much a recording shakes: the joints' typical change of speed from frame to frame
    (metres a frame per frame), a clean recording near 0.001, a noisy one past 0.005."""
    if len(figures) < 3:
        return 0.0
    shakes = sorted(
        (a.joints[n] - b.joints[n] * 2 + c.joints[n]).length()
        for a, b, c in zip(figures, figures[1:], figures[2:], strict=False)
        for n in a.joints
    )
    return shakes[len(shakes) // 2]


def _angle(a: Vec, b: Vec, c: Vec) -> float:
    """The angle at `b` between `a` and `c`, in degrees."""
    one, two = (a - b).normalised(), (c - b).normalised()
    return math.degrees(math.acos(max(-1.0, min(1.0, one.dot(two)))))


def draw(picture: Path, skeletons: dict[str, dict[str, list[float]]], out: Path) -> Path:
    """The skeletons drawn over the picture in OpenPose's colours: what the image model draws
    each person's pose from. Each joint is its place in the picture (pixels across and down),
    then (as the worker reports it) how far in front of the camera and whether it is seen; a
    limb behind the desk or a chair is left out, as a picture would hide it."""
    from PIL import Image, ImageDraw

    image = Image.open(picture).convert("RGB")
    pen = ImageDraw.Draw(image)
    scale = image.height / FOR_HEIGHT
    line, dot = max(2, round(LINE * scale)), max(2, round(DOT * scale))
    for joints in skeletons.values():
        seen = {name: at for name, at in joints.items() if len(at) < 4 or at[3] > 0}
        for a, b, colour in LIMBS:
            if a in seen and b in seen:
                pen.line([tuple(seen[a][:2]), tuple(seen[b][:2])], fill=colour, width=line)
        for x, y, *_ in seen.values():
            pen.ellipse([x - dot, y - dot, x + dot, y + dot], fill=(255, 255, 255))
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out)
    return out
