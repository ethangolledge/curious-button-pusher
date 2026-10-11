"""From a staged scene's description to a shot: the room is built (on a rehearsal stage, so
its marks, surfaces and furniture are known), every thing is resolved to a model at its
real size, and every copy is placed by its relation to something else, clear of everything
already there. Background detail is added where there is room. The result is an ordinary
render job: each placed thing is a `put` actor, every set of copies a named group, and the
actions are given to each copy in turn.

Pure Python and deterministic (seeded by the scene), so it runs the same in the free check
before a run and when the shot is rendered."""

import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from content.blender.api import Box, Mark, standing_in
from content.blender.blocks.base import Layout, SettingError, read, settings
from content.blender.job import ActorCall, BlockCall, ModelFile
from content.blender.maths import FRONT, UP, Vec, axis_angle, degrees_round
from content.blender.registry import Registry, RegistryError
from content.blender.rehearsal import RehearsalStage
from content.blender.sets import resting_on
from content.schemas.staging import Action, Setting, StagePlan, Thing

# Room to leave between things that stand side by side, and round a thing's edge.
GAP = 0.08
# Where a chair's centre stands from the edge of the table it is drawn up to.
CHAIR_REACH = 0.3
# How far beyond a thing's front something set before it may go to land on a table.
REACH = 0.6
# Random spots tried for each copy before settling for the best one found.
TRIES = 60
# An open place without walls is used out to this far from its centre.
OPEN_REACH = 12.0


@dataclass(frozen=True)
class Resolved:
    """What a thing is drawn with: a model the job can name, its size as drawn (width,
    depth, height in metres), and, for a model the library does not hold as it is (a
    version, a figure made to fit), how to make it."""

    model: str
    size: Vec
    file: ModelFile | None = None
    seated: bool = False  # a figure already in a seated pose: it needs a seat


Resolve = Callable[[Thing], Resolved | None]


@dataclass(frozen=True)
class Placed:
    actor_id: str
    thing_id: str
    box: Box
    heading: float
    support: str = ""  # what it stands on

    @property
    def facing(self) -> Vec:
        return axis_angle(UP, self.heading).rotate(FRONT)


@dataclass
class Composition:
    """The shot as composed: the actors, the groups of copies, the models to send, and
    what could not be done (each a line a person or the Visual Director can act on)."""

    actors: list[ActorCall] = field(default_factory=list)
    groups: dict[str, tuple[str, ...]] = field(default_factory=dict)
    models: list[ModelFile] = field(default_factory=list)
    actions: list[BlockCall] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    crowded: list[str] = field(default_factory=list)


# Background detail a room is given, by layout: what, where, and how many. `some` adds the
# pieces against the walls; `lived_in` also the small things on surfaces.
FURNISHING: dict[str, list[tuple[str, str, str, int]]] = {
    "office": [
        ("bookcase", "against_wall", "floor", 1),
        ("filing cabinet", "against_wall", "floor", 1),
        ("potted plant", "against_wall", "floor", 1),
        ("folder", "stacked_on", "desk", 3),
        ("coffee mug", "on", "desk", 1),
        ("book", "on", "desk", 2),
    ],
    "boardroom": [
        ("potted plant", "against_wall", "floor", 2),
        ("bookcase", "against_wall", "floor", 1),
        ("document", "scattered_on", "table", 4),
        ("glass", "on", "table", 3),
    ],
    "room": [
        ("bookcase", "against_wall", "floor", 1),
        ("armchair", "against_wall", "floor", 1),
        ("potted plant", "against_wall", "floor", 1),
    ],
    "corridor": [("potted plant", "against_wall", "floor", 2)],
}
SMALL = {"on", "scattered_on", "stacked_on", "in_row_on"}


class Composer:
    def __init__(self, registry: Registry, resolve: Resolve, *, seed: str) -> None:
        self._registry = registry
        self._resolve = resolve
        self._chance = random.Random(seed)
        self._placed: list[Placed] = []
        self._copies: dict[str, list[Placed]] = {}
        self._out = Composition()
        self._stage = RehearsalStage(frames=1, props=registry.props())

    # --- The room ------------------------------------------------------------------------

    def _build_room(self, plan: StagePlan) -> None:
        layout = self._registry.get("layouts", plan.layout.block)
        assert issubclass(layout, Layout)
        layout().build(self._stage, read(layout, _settings(plan.layout.settings)))
        try:
            interior = self._stage.find_mark("interior").surface
        except KeyError:
            interior = None
        self._room = interior or Box(
            Vec(-OPEN_REACH, -OPEN_REACH, 0), Vec(OPEN_REACH, OPEN_REACH, 2 * OPEN_REACH)
        )
        # The room's own furniture: what things may stand on or beside, and must not cross.
        self._furniture = {
            name: self._stage.bounds(self._stage.actor(name)) for name in self._stage.cast_names()
        }
        self._fixed = standing_in(self._room, list(self._furniture.values()))
        # Every solid piece of the room within it (a sill, the blinds, each chair's legs):
        # what placed things must keep clear of.
        self._solids = [b for b in self._stage.solids() if _shrink(b, 0.01).overlaps(self._room)]

    # --- Composing -----------------------------------------------------------------------

    def compose(self, plan: StagePlan) -> Composition:
        self._build_room(plan)
        for thing in _in_order(plan.things):
            self._place_thing(thing, required=True)
        if plan.furnish != "bare":
            for index, (what, relation, target, count) in enumerate(
                FURNISHING.get(plan.layout.block, [])
            ):
                if relation in SMALL and plan.furnish != "lived_in":
                    continue
                if target != "floor" and target not in self._furniture:
                    continue
                extra = Thing.model_validate(
                    {
                        "thing_id": f"furnish_{index}",
                        "what": what,
                        "count": count,
                        "place": {"relation": relation, "target": target},
                    }
                )
                self._place_thing(extra, required=False)
        self._out.actions = [call for action in plan.actions for call in self._act(action)]
        return self._out

    def _place_thing(self, thing: Thing, *, required: bool) -> None:
        resolved = self._resolve(thing)
        if resolved is None:
            if required:
                self._out.missing.append(f"model: {thing.what}")
            return
        if resolved.file is not None and resolved.file not in self._out.models:
            self._out.models.append(resolved.file)
        relation, target = thing.place.relation, thing.place.target
        anchors = self._copies.get(target, [])
        groups = [[a] for a in anchors] if thing.place.each and anchors else [anchors]
        copies: list[Placed] = []
        for group in groups:
            anchor = _union([a.box for a in group]) if group else self._target_box(target)
            if anchor is None and relation != "against_wall" and target != "floor":
                self._out.missing.append(f"place: '{target}' for {thing.what}")
                return
            for index in range(thing.count):
                actor_id = (
                    thing.thing_id
                    if thing.count * len(groups) == 1
                    else f"{thing.thing_id}_{len(copies)}"
                )
                spot = self._spot(relation, target, anchor, group, resolved, index, thing.count)
                if spot is None:
                    if required:
                        self._out.crowded.append(f"no room for every {thing.what}")
                    break
                at, heading, support = spot
                box = _box(at, resolved.size, heading)
                placed = Placed(actor_id, thing.thing_id, box, heading, support)
                self._placed.append(placed)
                copies.append(placed)
                self._out.actors.append(_put(actor_id, resolved, at, heading))
        self._copies[thing.thing_id] = copies
        if len(copies) > 1:
            self._out.groups[thing.thing_id] = tuple(p.actor_id for p in copies)

    def _target_box(self, target: str) -> Box | None:
        if target == "floor":
            return self._room
        if target in self._furniture:
            return self._furniture[target]
        try:
            mark = self._stage.find_mark(target)
        except KeyError:
            return None
        return mark.surface or Box(mark.at, mark.at)

    # --- Where one copy goes -------------------------------------------------------------

    def _spot(
        self,
        relation: str,
        target: str,
        anchor: Box | None,
        group: Sequence[Placed],
        resolved: Resolved,
        index: int,
        count: int,
    ) -> tuple[Vec, float, str] | None:
        size = resolved.size
        facing = group[0].facing if len(group) == 1 else FRONT
        if relation == "against_wall":
            return self._against_wall(size)
        if anchor is None:
            return None
        if relation == "at":
            mark = self._stage.find_mark(target)
            return resting_on(mark), degrees_round(mark.facing), target
        if relation == "stacked_on":
            base = self._stacked_height(target, anchor)
            return Vec(anchor.centre.x, anchor.centre.y, base), self._jitter(4), target
        if relation == "in_row_on":
            along_x = anchor.size.x >= anchor.size.y
            span = (anchor.size.x if along_x else anchor.size.y) - 2 * GAP
            u = (index + 0.5) / count - 0.5
            offset = Vec(u * span, 0, 0) if along_x else Vec(0, u * span, 0)
            return Vec(anchor.centre.x, anchor.centre.y, anchor.top) + offset, 0.0, target
        if relation in ("on", "scattered_on"):
            spin = 180.0 if relation == "scattered_on" else 12.0
            return self._clear_on(anchor, size, target, spin)
        if relation in ("around", "seated_at"):
            return self._around(relation, anchor, resolved, index, count, target)
        # Beside, in front of, behind: next to the anchor, on whatever is under that spot.
        if relation == "beside":
            side = Vec(-facing.y, facing.x, 0) * (1 if index % 2 == 0 else -1)
            reach = _half_across(anchor, side) + _half_across(_box(Vec(), size, 0), side) + GAP
            ring = index // 2
            point = anchor.centre + side * (reach + ring * (size.x + GAP))
        else:
            way = facing if relation == "in_front_of" else -facing
            reach = _half_across(anchor, way) + max(size.x, size.y) / 2 + GAP
            sideways = Vec(-way.y, way.x, 0) * ((index - (count - 1) / 2) * (size.x + GAP))
            point = anchor.centre + way * reach + sideways
            # Within arm's reach a table or a desk takes it (a glass before a seated man).
            for step in range(int(REACH / 0.05) + 1):
                ahead = point + way * (step * 0.05 + max(size.x, size.y) / 2)
                if self._support_under(ahead, below=anchor.top + 0.05)[0] > 0:
                    point = ahead
                    break
        heading = degrees_round(facing)
        z, support = self._support_under(point, below=anchor.top + 0.05)
        return self._nudged(Vec(point.x, point.y, z), size, heading, support, ignore=group)

    def _clear_on(
        self, surface: Box, size: Vec, target: str, spin: float
    ) -> tuple[Vec, float, str] | None:
        for _ in range(TRIES):
            heading = self._jitter(spin)
            footprint = _box(Vec(), size, heading)
            hx, hy = footprint.size.x / 2, footprint.size.y / 2
            if surface.size.x < 2 * hx or surface.size.y < 2 * hy:
                return None
            at = Vec(
                self._chance.uniform(surface.low.x + hx, surface.high.x - hx),
                self._chance.uniform(surface.low.y + hy, surface.high.y - hy),
                surface.top,
            )
            if self._clear(_box(at, size, heading)):
                return at, heading, target
        return None

    def _stacked_height(self, target: str, anchor: Box) -> float:
        on_it = [p for p in self._placed if p.support == target]
        return max([anchor.top, *(p.box.top for p in on_it)])

    def _around(
        self,
        relation: str,
        anchor: Box,
        resolved: Resolved,
        index: int,
        count: int,
        target: str,
    ) -> tuple[Vec, float, str] | None:
        seated = relation == "seated_at"
        if seated:
            seat = self._free_seat(anchor)
            if seat is not None:
                return seat.at, degrees_round(seat.facing), seat.name
        depth = max(resolved.size.x, resolved.size.y)
        margin = CHAIR_REACH if seated else depth / 2 + 0.25
        point, facing = _round_edge(anchor, margin, (index + 0.5) / count)
        heading = degrees_round(facing)
        if seated:
            self._add_chair(point, heading)
            return point, heading, f"chair for {target}"
        return self._nudged(point, resolved.size, heading, "floor", ignore=[])

    def _free_seat(self, anchor: Box) -> Mark | None:
        """A seat the room already has beside this table, not yet taken."""
        taken = {p.support for p in self._placed}
        seats = [
            m for m in self._stage.marks()
            if m.name.startswith("seat_") and m.name not in taken
            and _distance_to(anchor, m.at) < 1.0
        ]  # fmt: skip
        return min(seats, key=lambda m: (m.at.x, m.at.y), default=None)

    def _add_chair(self, at: Vec, heading: float) -> None:
        chair = Thing.model_validate(
            {"thing_id": "chair", "what": "chair", "place": {"relation": "at", "target": "floor"}}
        )
        resolved = self._resolve(chair)
        if resolved is None:
            return
        actor_id = f"chair_{sum(p.thing_id == 'added_chair' for p in self._placed)}_added"
        self._placed.append(
            Placed(actor_id, "added_chair", _box(at, resolved.size, heading), heading, "floor")
        )
        self._out.actors.append(_put(actor_id, resolved, at, heading))

    def _against_wall(self, size: Vec) -> tuple[Vec, float, str] | None:
        """A spot with its back to the back or a side wall, facing into the room (never the
        front wall: that is where the camera usually stands)."""
        room = self._room
        # The back wall, then the left and right ones, each with the way into the room.
        walls = [Vec(0, -1, 0), Vec(1, 0, 0), Vec(-1, 0, 0)]
        for _ in range(TRIES):
            facing = walls[self._chance.randrange(len(walls))]
            heading = degrees_round(facing)
            footprint = _box(Vec(), size, heading)
            along_x = facing.y != 0
            half_along = (footprint.size.x if along_x else footprint.size.y) / 2
            depth = (footprint.size.y if along_x else footprint.size.x) / 2 + 0.02
            low, high = (room.low.x, room.high.x) if along_x else (room.low.y, room.high.y)
            if high - low < 2 * half_along:
                continue
            u = self._chance.uniform(low + half_along, high - half_along)
            if along_x:
                at = Vec(u, room.high.y - depth, 0)
            else:
                at = Vec(room.low.x + depth if facing.x > 0 else room.high.x - depth, u, 0)
            if self._clear(_box(at, size, heading)):
                return at, heading, "floor"
        return None

    def _support_under(self, point: Vec, *, below: float) -> tuple[float, str]:
        """The highest top under a spot that is no higher than `below`: a table, or the
        floor."""
        tops = [(0.0, "floor")]
        for name, box in self._furniture.items():
            if box in self._fixed and _over(box, point) and box.top <= below:
                tops.append((box.top, name))
        for placed in self._placed:
            if _over(placed.box, point) and placed.box.top <= below:
                tops.append((placed.box.top, placed.actor_id))
        return max(tops)

    def _nudged(
        self, at: Vec, size: Vec, heading: float, support: str, *, ignore: Sequence[Placed]
    ) -> tuple[Vec, float, str] | None:
        """The spot, or the nearest clear one round it; None if all round it is taken."""
        for step in range(TRIES):
            radius = 0.1 * math.ceil(step / 8)
            angle = step * math.tau / 8
            moved = at + Vec(math.cos(angle) * radius, math.sin(angle) * radius, 0)
            if self._clear(_box(moved, size, heading), ignore=ignore, support=support):
                return moved, heading, support
        return None

    def _clear(self, box: Box, *, ignore: Sequence[Placed] = (), support: str = "") -> bool:
        if not _inside_room(box, self._room):
            return False
        others = [p.box for p in self._placed if p not in ignore and p.actor_id != support]
        others += self._solids
        shrunk = _shrink(box, 0.01)
        return not any(shrunk.overlaps(other) for other in others)

    def _jitter(self, degrees: float) -> float:
        return self._chance.uniform(-degrees, degrees)

    # --- What happens --------------------------------------------------------------------

    def _act(self, action: Action) -> list[BlockCall]:
        """An action for each copy of `who`, in turn: every setting naming `who` names the
        copy, and its start (if it has one) is `stagger` later for each."""
        members = [p.actor_id for p in self._copies.get(action.who, [])] or [action.who]
        try:
            block = self._registry.get("actions", action.block)
            timed = {s.name for s in settings(block) if s.name in ("start", "when")}
        except RegistryError:
            timed = set()
        calls = []
        for index, member in enumerate(members):
            values = {s.name: member if s.value == action.who else s.value for s in action.settings}
            for name in timed:
                begins = float(values.get(name, "0") or 0)
                values[name] = _n(min(0.9, begins + index * action.stagger))
            calls.append(BlockCall(action.block, values))
        return calls


def compose(plan: StagePlan, registry: Registry, resolve: Resolve, *, seed: str) -> Composition:
    try:
        return Composer(registry, resolve, seed=seed).compose(plan)
    except (KeyError, RegistryError, SettingError) as exc:
        return Composition(missing=[str(exc).strip("'\"")])


# --- Geometry ------------------------------------------------------------------------------


def _settings(given: Sequence[Setting]) -> dict[str, str]:
    return {setting.name: setting.value for setting in given}


def _put(actor_id: str, resolved: Resolved, at: Vec, heading: float) -> ActorCall:
    """A placed thing, drawn at the size it was resolved to."""
    values = {"x": _n(at.x), "y": _n(at.y), "z": _n(at.z), "heading": _n(heading)}
    if resolved.file is None:
        values["height"] = _n(resolved.size.z)
    return ActorCall(actor_id, "put", resolved.model, values)


def _n(value: float) -> str:
    return f"{value:.3f}"


def _box(at: Vec, size: Vec, heading: float) -> Box:
    """Where a thing standing at `at` (its base's centre), turned `heading`, takes up room."""
    turn = math.radians(heading)
    c, s = abs(math.cos(turn)), abs(math.sin(turn))
    half = Vec((c * size.x + s * size.y) / 2, (s * size.x + c * size.y) / 2, 0)
    return Box(at - half, at + half + Vec(0, 0, size.z))


def _union(boxes: Sequence[Box]) -> Box | None:
    if not boxes:
        return None
    out = boxes[0]
    for box in boxes[1:]:
        out = out.union(box)
    return out


def _shrink(box: Box, by: float) -> Box:
    margin = Vec(by, by, by)
    return Box(box.low + margin, box.high - margin)


def _over(box: Box, point: Vec) -> bool:
    return box.low.x <= point.x <= box.high.x and box.low.y <= point.y <= box.high.y


def _inside_room(box: Box, room: Box) -> bool:
    return (
        room.low.x <= box.low.x and box.high.x <= room.high.x
        and room.low.y <= box.low.y and box.high.y <= room.high.y
    )  # fmt: skip


def _half_across(box: Box, way: Vec) -> float:
    """How far a box reaches from its centre in a ground direction."""
    return abs(way.x) * box.size.x / 2 + abs(way.y) * box.size.y / 2


def _distance_to(box: Box, point: Vec) -> float:
    dx = max(box.low.x - point.x, 0.0, point.x - box.high.x)
    dy = max(box.low.y - point.y, 0.0, point.y - box.high.y)
    return math.hypot(dx, dy)


def _round_edge(box: Box, margin: float, u: float) -> tuple[Vec, Vec]:
    """A point `u` of the way round a box's edge, `margin` out from it, and the way facing
    in: round a long table, along both long sides first, then the ends."""
    w, d = box.size.x + 2 * margin, box.size.y + 2 * margin
    perimeter = 2 * (w + d)
    # Start in the middle of the near long side, so a few copies sit facing the camera's way.
    t = (u * perimeter + w / 2) % perimeter
    low = Vec(box.low.x - margin, box.low.y - margin, 0)
    if t < w:
        return low + Vec(t, 0, 0), Vec(0, 1, 0)
    if t < w + d:
        return low + Vec(w, t - w, 0), Vec(-1, 0, 0)
    if t < 2 * w + d:
        return low + Vec(w - (t - w - d), d, 0), Vec(0, -1, 0)
    return low + Vec(0, d - (t - 2 * w - d), 0), Vec(1, 0, 0)


def _in_order(things: Sequence[Thing]) -> list[Thing]:
    """Things placed after whatever they are placed in relation to."""
    ids = {thing.thing_id for thing in things}
    done: list[Thing] = []
    waiting = list(things)
    while waiting:
        placed = {d.thing_id for d in done}
        ready = [t for t in waiting if t.place.target not in ids or t.place.target in placed]
        if not ready:  # a loop: place the rest as they come
            ready = waiting[:1]
        for thing in ready:
            done.append(thing)
            waiting.remove(thing)
    return done
