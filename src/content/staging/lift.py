"""A keyframe lifted into depth, so it can move in Blender as itself (docs/picture-shots.md):
the picture's geometry and lens (MoGe-2), its people found, outlined and posed (Grounding DINO,
SAM 2, ViTPose), and the background behind them painted in (LaMa), in colour and in depth.

The result is one file (`.npz`) kept in the library as a set, like any set: the camera where
the picture was taken from (`mark_camera`, with its lens), a point straight ahead at the
picture's middle distance (`mark_ahead`), each person an actor (`actor_person_<n>`), and the
space the camera may move in (`interior`). Blender builds it (`blender/lift.py`); the same
picture is lifted once."""

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from content.providers import vision
from content.staging.library import Library, Model
from content.staging.store import Store

SOURCE = "lifted from its picture (MoGe-2, Grounding DINO, SAM 2, ViTPose, LaMa)"
# How the lifting works: raised when that changes, so pictures are lifted again.
LIFTER = 6
# Pixels between the vertices of a layer's mesh: finer than this adds nothing the picture's
# own resolution shows across a few pixels of camera travel.
GRID = 4
PEOPLE = "a person."
# The detector's confidence below which a box is not a person.
MIN_PERSON = 0.35
# How much wider than a person's outline the hole behind them is painted (pixels), so no rim
# of them is left on the wall; and how soft their own edge is.
HOLE_MARGIN = 10
FEATHER = 1.5
# A depth model blurs depth across an outline over a few pixels, so a person's edge would
# ramp back towards the wall and smear as the camera moves: the band this wide inside their
# outline takes the depth of their solid middle instead (pixels).
EDGE = 6
# How far the background reaches beyond the picture's edges, as a fraction of its longer
# side, continuing its edge colours: a camera move never shows an empty border.
MARGIN = 0.06
# How much further than a person the background behind them is at least (a fraction).
BEHIND = 0.05
# A depth edge (a chair before the floor, a figure before a wall): where depth across a few
# pixels (`SHARP`) changes by more than this fraction. A depth model blurs it into a ramp,
# which would stretch as the camera moves; each pixel of the ramp is snapped to the side it
# is nearer, so the edge is a clean step the mesh is cut at.
EDGE_JUMP = 0.15
SHARP = 4
# Behind the nearer side of every depth edge, a band this wide is painted in (pixels): what
# a moving camera sees past the edge. Only a band as wide as the parallax is ever seen.
BAND = 32
# How far round the picture the camera may wander, beyond everything it shows (metres).
ROOM = 0.5
# Blender's camera sensor, fitted to the picture's longer side (`blender/camera.py`).
SENSOR_MM = 36.0


def lift_id(picture: Path) -> str:
    """The same picture, the same lifted set."""
    digest = hashlib.sha256(picture.read_bytes() + f"lifter {LIFTER}".encode()).hexdigest()
    return f"lifted_{digest[:12]}"


def lifted(library: Library, picture: Path, *, make: bool) -> Model | None:
    """The picture lifted into a set: from the library if lifted before, else lifted now
    (when `make`, with the vision models installed), else None."""
    model_id = lift_id(picture)
    if model_id in library.models:
        return library.models[model_id]
    if not make or library.folder is None or not vision.ready():
        return None
    arrays, parts, size, people = lift(picture)
    store = Store(library.folder)
    with tempfile.TemporaryDirectory() as work:
        made = Path(work) / "lifted.npz"
        np.savez_compressed(made, **arrays)
        kept = store.keep_file(made)
    model = Model(
        model_id=model_id,
        names=(f"lifted {picture.stem}",),
        describe=f"The picture {picture.name} lifted into depth, with {people} people in it",
        size=size,
        capabilities=("set", "lifted"),
        source=SOURCE,
        licence="own",
        file=kept,
        parts=tuple(parts),
        motions=("breathing", "talking") if people else (),
    )
    library.add(model, alongside=True)
    store.note(model_id, "lifted", {"picture": picture.name, "lifter": LIFTER, "people": people})
    return model


def lift(
    picture: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], tuple[float, float, float], int]:
    """What Blender builds the set from, its parts, its size, and how many people it holds."""
    from PIL import Image

    pixels = np.asarray(Image.open(picture).convert("RGB"))
    height, width = pixels.shape[:2]
    shape = vision.geometry(picture)
    found = [
        f.box for f in vision.find(picture, PEOPLE, threshold=MIN_PERSON) if "person" in f.label
    ]
    masks = vision.outline(picture, found) if found else np.zeros((0, height, width), bool)
    joints = vision.poses(picture, found) if found else np.zeros((0, 17, 3), np.float32)
    # Behind the people: the picture painted in where each stood, and the depth carried in
    # from around them.
    background, depth = pixels, _sharpened(shape.points[..., 2])
    solid = [_spread(shape.points[..., 2], _shrunk(mask, EDGE)) for mask in masks]
    for mask, theirs in zip(masks, solid, strict=True):
        hole = _grown(mask, HOLE_MARGIN)
        background = vision.fill(background, hole)
        # Whatever is behind a person is further away than they are: depth carried in from
        # a desk in front of them would otherwise stand in front of them.
        depth = np.where(hole, np.maximum(_carried(depth, hole), theirs * (1 + BEHIND)), depth)
    # Past every other depth edge: the far side carried on behind the near side's band.
    band, far = _behind(depth)
    hidden = vision.fill(background, band)
    # The background's vertices, a grid reaching a margin beyond the picture's edges; each
    # person's, a grid over the picture.
    reach = int(MARGIN * max(height, width)) // GRID * GRID
    rows = np.arange(GRID // 2 - reach, height + reach, GRID)
    cols = np.arange(GRID // 2 - reach, width + reach, GRID)
    inside = np.ix_(np.clip(rows, 0, height - 1), np.clip(cols, 0, width - 1))
    ground = _blender(_points(depth[inside], rows, cols, (height, width), shape.focal))
    beyond = _blender(_points(far[inside], rows, cols, (height, width), shape.focal))
    points = _blender(shape.points)
    # Standing on the origin, centred over it, as every model in the library is.
    low = np.minimum(points.reshape(-1, 3).min(0), ground.reshape(-1, 3).min(0))
    high = np.maximum(points.reshape(-1, 3).max(0), ground.reshape(-1, 3).max(0))
    shift = np.array([-(low[0] + high[0]) / 2, -(low[1] + high[1]) / 2, -low[2]], np.float32)
    points, ground, beyond = points + shift, ground + shift, beyond + shift
    camera = shift.astype(float)
    every = (slice(GRID // 2, None, GRID), slice(GRID // 2, None, GRID))
    grid_rows, grid_cols = np.mgrid[every[0].start : height : GRID, every[1].start : width : GRID]
    alphas = np.stack([_soft(mask) for mask in masks]) if len(masks) else masks.astype(np.uint8)
    # Each person's own surface: their points, and just beyond their outline the point of
    # them nearest, so the soft edge of their picture lies on them, not on the wall behind.
    people_points = np.zeros((len(masks), *grid_rows.shape, 3), np.float32)
    for n, theirs in enumerate(solid):
        spread = theirs[every]
        people_points[n] = (
            _blender(_points(spread, grid_rows[:, 0], grid_cols[0], (height, width), shape.focal))
            + shift
        )
    around = np.zeros((len(masks), *grid_rows.shape), bool)
    for n, mask in enumerate(masks):
        around[n] = _grown(mask, 2 * GRID)[every]
    joints3d = np.array(
        [[[*_at(points, mask, x, y), score] for x, y, score in person]
         for person, mask in zip(joints, masks, strict=True)],
        np.float32,
    ).reshape(len(masks), 17, 4)  # fmt: skip
    arrays = {
        "picture": pixels,
        "background": background,
        "people_points": people_points,
        "people_reach": around,
        "points_pixels": np.stack([grid_cols, grid_rows], axis=-1).astype(np.int32),
        "ground": ground,
        "ground_pixels": np.stack(np.meshgrid(cols, rows), axis=-1).astype(np.int32),
        "hidden": hidden,
        "beyond": beyond,
        "beyond_reach": _grown(band, GRID)[inside],
        "people": alphas,
        "joints": joints3d,
        "grid": np.array(GRID),
    }
    lens = SENSOR_MM * (shape.focal[0] if width >= height else shape.focal[1])
    ahead = float(np.median(depth))
    room = _box(np.vstack([points.reshape(-1, 3), [camera]]), margin=ROOM)
    parts = [
        _part("mark_camera", camera, (0, 1, 0), lens=round(lens, 2)),
        _part("mark_ahead", camera + np.array([0, ahead, 0]), (0, -1, 0)),
        *(
            _part(f"actor_person_{n}", middle, (0, -1, 0), size)
            for n, mask in enumerate(masks)
            for middle, size in [_box(points[mask])]
        ),
        _part("interior", room[0], (0, -1, 0), room[1]),
    ]
    arrays["parts"] = np.array(json.dumps(parts))
    w, d, h = (round(float(v), 3) for v in high - low)
    return arrays, parts, (w, d, h), len(masks)


def _blender(points: np.ndarray) -> np.ndarray:
    """Camera coordinates (x right, y down, z ahead) as Blender's (x right, y ahead, z up)."""
    return np.stack([points[..., 0], points[..., 2], -points[..., 1]], axis=-1).astype(np.float32)


def _points(
    depth: np.ndarray,
    rows: np.ndarray,
    cols: np.ndarray,
    size: tuple[int, int],
    focal: tuple[float, float],
) -> np.ndarray:
    """The point at `depth` seen at each pixel (`rows` by `cols`, which may lie beyond the
    picture), through a lens whose focal length is `focal` (fractions of the picture's width
    and height) and whose centre is the picture's."""
    height, width = size
    u = (cols + 0.5) / width - 0.5
    v = (rows + 0.5) / height - 0.5
    x = u[None, :] / focal[0] * depth
    y = v[:, None] / focal[1] * depth
    return np.stack([x, y, depth], axis=-1).astype(np.float32)


def _spread(depth: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """`depth` inside `mask`, and outside it the depth of the nearest pixel inside."""
    from scipy.ndimage import distance_transform_edt

    nearest = distance_transform_edt(~mask, return_distances=False, return_indices=True)
    return np.asarray(depth[nearest[0], nearest[1]], dtype=np.float32)


def _sharpened(depth: np.ndarray) -> np.ndarray:
    """`depth` with every ramp across a depth edge snapped to the nearer of its two sides."""
    import cv2

    kernel = np.ones((2 * SHARP + 1, 2 * SHARP + 1), np.uint8)
    near = cv2.erode(depth.astype(np.float32), kernel)
    far = cv2.dilate(depth.astype(np.float32), kernel)
    ramp = far > near * (1 + EDGE_JUMP)
    snapped = np.where(depth - near < far - depth, near, far)
    return np.where(ramp, snapped, depth).astype(np.float32)


def _behind(depth: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The band on the near side of every depth edge (pixels with something much further
    within `BAND` of them), and the depth of that further thing, carried behind them."""
    import cv2

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * BAND + 1, 2 * BAND + 1))
    far = cv2.dilate(depth.astype(np.float32), kernel)
    band = far > depth * (1 + EDGE_JUMP)
    return band, np.where(band, far, depth).astype(np.float32)


def _shrunk(mask: np.ndarray, pixels: int) -> np.ndarray:
    """`mask` without a band `pixels` wide round its edge (all of it, if that leaves none)."""
    import cv2

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * pixels + 1, 2 * pixels + 1))
    inner = np.asarray(cv2.erode(mask.astype(np.uint8), kernel) > 0)
    return inner if inner.any() else mask


def _grown(mask: np.ndarray, pixels: int) -> np.ndarray:
    import cv2

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * pixels + 1, 2 * pixels + 1))
    return np.asarray(cv2.dilate(mask.astype(np.uint8), kernel) > 0)


def _carried(depth: np.ndarray, hole: np.ndarray) -> np.ndarray:
    """Depth carried into a hole from around it (OpenCV's Telea inpainting), in whole
    millimetres: on floating-point depth it overshoots far beyond what surrounds the hole
    (behind a seated figure, depths from −0.7 m to 4 m round a wall 1 to 2.6 m away)."""
    import cv2

    millimetres = (depth * 1000).round().clip(1, 65535).astype(np.uint16)
    painted = cv2.inpaint(millimetres, hole.astype(np.uint8), 8, cv2.INPAINT_TELEA) / 1000
    return np.where(hole, painted, depth).astype(np.float32)


def _soft(mask: np.ndarray) -> np.ndarray:
    """A person's outline as an alpha channel with a slightly soft edge."""
    import cv2

    soft = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), FEATHER)
    return np.asarray((soft * 255).round().clip(0, 255), dtype=np.uint8)


def _at(points: np.ndarray, mask: np.ndarray, x: float, y: float) -> np.ndarray:
    """Where a pixel of a person is in 3D: on them, or at the nearest pixel that is."""
    height, width = mask.shape
    col, row = int(np.clip(x, 0, width - 1)), int(np.clip(y, 0, height - 1))
    if not mask[row, col]:
        rows, cols = np.nonzero(mask)
        nearest = int(np.argmin((rows - row) ** 2 + (cols - col) ** 2))
        row, col = int(rows[nearest]), int(cols[nearest])
    return np.asarray(points[row, col])


def _box(points: np.ndarray, margin: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """The middle and size of what `points` take up."""
    low, high = points.min(0) - margin, points.max(0) + margin
    return (low + high) / 2, high - low


def _part(name: str, at: Any, facing: Any, size: Any = (0, 0, 0), **extra: float) -> dict[str, Any]:
    """A set's part as the library keeps it: where it is (a box's middle), the way it faces,
    and its size (none for a mark)."""
    return {
        "name": name,
        "at": [round(float(v), 3) for v in at],
        "facing": [round(float(v), 3) for v in facing],
        "size": [round(float(v), 3) for v in size],
        **extra,
    }
