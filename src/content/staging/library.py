"""The models a channel can put in a shot: the props the engine makes in code, and the
channel's own library of fetched or generated models (kept in `themes/<name>/assets/` by
`store.py`, private, saved with the rest of the channel).

Search is by meaning, not spelling: every model has one id and the other words for it, and a
search matches whole phrases, the words in them, and (when a local embedding model is
available) what they mean. Adding a model that a search already finds is refused, so the
library never holds the same thing twice under different names."""

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from content.blender.blocks.base import Prop, read, summary
from content.blender.job import ModelFile
from content.blender.materials import ROLES
from content.blender.maths import fit_scale
from content.blender.registry import discover
from content.blender.rehearsal import RehearsalStage
from content.providers.assets import CREDITED
from content.staging.store import Store

MADE_IN_CODE = "made in code"
# A picture in the library (a map, a painting) is kept as it is and drawn on a card.
PICTURES = (".png", ".jpg", ".jpeg", ".webp")
# Words that say nothing about what a thing is.
FILLER = frozenset(
    [
        "a",
        "an",
        "the",
        "of",
        "with",
        "and",
        "or",
        "on",
        "in",
        "to",
        "for",
        "from",
        "some",
        "old",
        "new",
        "small",
        "large",
        "big",
        "little",
        "one",
        "two",
        "very",
        "its",
        "his",
        "her",
        "their",
        "our",
        "your",
    ]
)
# A search result counts from this score; adding a model this close to an existing one is
# refused as a duplicate.
MATCH, DUPLICATE = 0.45, 0.8

Embed = Callable[[Sequence[str]], np.ndarray]
Size = tuple[float, float, float]


@dataclass(frozen=True)
class Model:
    model_id: str
    names: tuple[str, ...]
    describe: str
    size: tuple[float, float, float]
    capabilities: tuple[str, ...] = ()
    # Where it came from: "made in code" for the engine's props.
    source: str = MADE_IN_CODE
    licence: str = ""
    page: str = ""
    author: str = ""
    cost_usd: float = 0.0
    file: str = ""  # relative to the library folder
    # "kept" (a person chose it, or made it), "auto" (taken automatically for a scene, for a
    # person to review), "vetoed" (turned down: never used again).
    status: str = "kept"
    # How sure the automatic choice was, from 0 to 1 (`sourcing.score`).
    score: float = 0.0
    # A seated figure: how high the seat it fits is (metres), so it is sat on any chair.
    seat: float = 0.0
    # A figure posed to hold something: where each held thing's base goes (metres right, back
    # and up from where the figure stands), by name ("drink", "document", "phone").
    holds: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    # A set's named parts (marks, surfaces, paths, actors, interior), each with where it is,
    # which way it faces and its size: what a shot using the set can refer to.
    parts: tuple[dict[str, Any], ...] = ()
    # A character's motions, by name (what a placed figure can play).
    motions: tuple[str, ...] = ()
    # A version of another model (`base`): its parts, materials or roles drawn as other roles
    # (`paint`), and its own size. It has no file of its own.
    base: str = ""
    paint: dict[str, str] = field(default_factory=dict)

    @property
    def words(self) -> list[str]:
        """Every way of naming it, the id first."""
        return [self.model_id.replace("_", " "), *self.names]


@dataclass(frozen=True)
class Found:
    model: Model
    score: float


@dataclass
class Library:
    folder: Path | None
    models: dict[str, Model] = field(default_factory=dict)
    # The props made in code, by name: the families things can be made from.
    props: dict[str, type[Prop]] = field(default_factory=dict)

    def get(self, model_id: str) -> Model:
        if model_id not in self.models:
            raise KeyError(f"no model '{model_id}' (see: content staging models)")
        return self.models[model_id]

    def search(self, words: str, embed: Embed | None = None, limit: int = 5) -> list[Found]:
        query = _terms(words)
        usable = [m for m in self.models.values() if m.status != "vetoed"]
        scores = {m.model_id: max(_lexical(query, _terms(w)) for w in m.words) for m in usable}
        if embed is not None and usable:
            texts = [f"{m.words[0]}: {m.describe}" for m in usable]
            vectors = embed([words, *texts])
            asked, rest = vectors[0], vectors[1:]
            similarity = (
                rest @ asked / (np.linalg.norm(rest, axis=1) * np.linalg.norm(asked) + 1e-12)
            )
            for model, close in zip(usable, similarity, strict=True):
                scores[model.model_id] = max(scores[model.model_id], float(close))
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return [
            Found(self.models[mid], round(score, 3))
            for mid, score in ranked[:limit]
            if score >= MATCH
        ]

    def add(self, model: Model, *, embed: Embed | None = None, alongside: bool = False) -> None:
        """Add a model to the channel's library, unless it is already there by another name
        (`alongside` adds it anyway, for a genuinely different version of a thing)."""
        if self.folder is None:
            raise ValueError("models can only be added to a channel's library")
        if model.model_id in self.models:
            raise ValueError(f"'{model.model_id}' is already in the library")
        for words in model.words:
            close = [f for f in self.search(words, embed) if f.score >= DUPLICATE]
            if close and not alongside:
                raise ValueError(
                    f"'{words}' is already in the library as '{close[0].model.model_id}'. Add "
                    f"the new words to it instead (content staging models name "
                    f'{close[0].model.model_id} "{words}"), or pass --alongside if it is '
                    "really a different thing."
                )
        self.models[model.model_id] = model
        self._store().write(asdict(model))
        self._store().note(
            model.model_id,
            "added",
            {
                "source": model.source,
                "page": model.page,
                "licence": model.licence,
                "status": model.status,
            },
        )

    def name(self, model_id: str, words: str) -> None:
        """Another word for a model, so searches find it."""
        model = self.get(model_id)
        if model.source == MADE_IN_CODE:
            raise ValueError(f"'{model_id}' is made in code: add the words to its file's `names`")
        if words not in model.names:
            self.models[model_id] = _replace(model, names=(*model.names, words))
            self._store().write(asdict(self.models[model_id]))

    def vary(
        self,
        model_id: str,
        base_id: str,
        *,
        describe: str,
        names: Sequence[str] = (),
        paint: Mapping[str, str] | None = None,
        height: float | None = None,
    ) -> Model:
        """A version of a model: the same shape, repainted and resized, under its own name
        (a red ballot box from a cardboard box, a gold statue from a stone one). It keeps the
        original's rights: whoever must be credited for it is credited for this."""
        base = self.get(base_id)
        unknown = sorted(set((paint or {}).values()) - set(ROLES))
        if unknown:
            raise ValueError(f"no role {', '.join(unknown)} (roles: {', '.join(ROLES)})")
        scale = height / base.size[2] if height and base.size[2] else 1.0
        variant = Model(
            model_id=model_id,
            names=tuple(names),
            describe=describe,
            size=(
                round(base.size[0] * scale, 3),
                round(base.size[1] * scale, 3),
                round(base.size[2] * scale, 3),
            ),
            capabilities=base.capabilities,
            source=f"a version of {base_id}",
            licence=base.licence,
            page=base.page,
            author=base.author,
            parts=base.parts,
            motions=base.motions,
            base=base_id,
            paint=dict(paint or {}),
        )
        self.add(variant, alongside=True)
        return variant

    def root(self, model: Model) -> tuple[Model, dict[str, str]]:
        """The model a version is ultimately made from, and the paint its versions add up to
        (a later version's choice wins)."""
        paint = dict(model.paint)
        while model.base:
            model = self.get(model.base)
            paint = {**model.paint, **paint}
        return model, paint

    def model_file(
        self,
        model_id: str,
        *,
        key: str = "",
        paint: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
        fit: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> ModelFile | None:
        """What Blender needs to draw a model: the file (or prop) it is made from, under
        `key` in the job (its id, unless it is made to fit a scene), its paint, a family's
        settings, and its size: as made, or stretched to `fit` (width, depth, height; 0 for
        any keeps its proportions). None for a prop made in code drawn as it is: Blender
        has its file."""
        model = self.get(model_id)
        root, painted = self.root(model)
        painted = {**painted, **(paint or {})}
        path = self.path(root)
        made_in_code = root.source == MADE_IN_CODE
        size = self.measure(root.model_id, params) if params else model.size
        if model.base and not any(fit):
            fit = (0.0, 0.0, model.size[2])
        if path is None and not model.base and not painted and not params and not any(fit):
            return None
        return ModelFile(
            key or model_id,
            str(path or ""),
            fitted_size(size, fit),
            prop=root.model_id if made_in_code else "",
            paint=painted,
            base=model_id,
            params=dict(params or {}),
            fit=fit,
        )

    def measure(self, prop_id: str, params: Mapping[str, str] | None = None) -> Size:
        """A family's width, depth and height with these settings."""
        prop = self.props[prop_id]
        return _measured(prop, read(prop, params or {}))

    def credit(self, model_id: str) -> str:
        """The line a video using this model must carry where it is published, naming the
        original it is (a version of), or "" when its licence asks for none."""
        model, _ = self.root(self.get(model_id))
        if model.licence not in CREDITED:
            return ""
        maker = f" by {model.author}" if model.author else ""
        return f"{model.describe}{maker} ({model.source}, {model.licence}): {model.page}"

    def used(self, model_id: str, video: str) -> None:
        """Note that a video used a model (and, for a version, the model it is made from)."""
        model, _ = self.root(self.get(model_id))
        if model.source != MADE_IN_CODE:
            self._store().used(model.model_id, video)

    def veto(self, model_id: str, reason: str) -> None:
        """Turn a model down: searches never find it again, and the source it came from is
        not offered again for the same words."""
        model = self.get(model_id)
        if model.source == MADE_IN_CODE:
            raise ValueError(f"'{model_id}' is made in code: change or delete its file instead")
        self.models[model_id] = _replace(model, status="vetoed")
        self._store().write(asdict(self.models[model_id]))
        self._store().note(model_id, "vetoed", {"reason": reason})

    def keep(self, model_id: str) -> None:
        """A person has looked at a model taken automatically, and keeps it."""
        self.models[model_id] = _replace(self.get(model_id), status="kept")
        self._store().write(asdict(self.models[model_id]))
        self._store().note(model_id, "kept", {})

    def path(self, model: Model) -> Path | None:
        return self.folder / model.file if self.folder is not None and model.file else None

    def _store(self) -> Store:
        if self.folder is None:
            raise ValueError("models can only be kept in a channel's library")
        return Store(self.folder)


def load_library(folder: Path | None, channel_blocks: Sequence[Path] = ()) -> Library:
    """The engine's props and, if a channel folder is given, its own models."""
    library = Library(folder)
    library.props = dict(discover(channel_blocks, ("props",)).props())
    for prop in library.props.values():
        library.models[prop.name] = Model(
            model_id=prop.name,
            names=prop.names,
            describe=summary(prop),
            size=_measured(prop),
            capabilities=tuple(sorted(prop.capabilities)),
        )
    for data in Store(folder).records() if folder is not None else []:
        for listed in ("names", "size", "capabilities", "parts", "motions"):
            data[listed] = tuple(data.get(listed, ()))
        data["paint"] = dict(data.get("paint", {}))
        data["holds"] = {name: tuple(at) for name, at in data.get("holds", {}).items()}
        model = Model(**data)
        if model.model_id in library.models:
            raise ValueError(f"{folder}: '{model.model_id}' is already a prop made in code")
        library.models[model.model_id] = model
    return library


def _measured(prop: type[Prop], values: Any = None) -> Size:
    """A prop's width, depth and height, from building it without Blender."""
    stage = RehearsalStage(frames=1)
    size = stage.bounds(prop(values).build(stage, prop.name)).size
    return (round(size.x, 3), round(size.y, 3), round(size.z, 3))


def fitted_size(size: Size, fit: tuple[float, float, float]) -> Size:
    """A thing's size once stretched to `fit`, as Blender stretches it."""
    x, y, z = fit_scale(size, fit)
    return (round(size[0] * x, 3), round(size[1] * y, 3), round(size[2] * z, 3))


def _replace(model: Model, **changes: object) -> Model:
    return Model(**{**asdict(model), **changes})


def match(words: str, name: str) -> float:
    """How well a name matches some words, from 0 to 1 (as a library search scores them)."""
    return _lexical(_terms(words), _terms(name))


def _terms(text: str) -> tuple[str, ...]:
    words = re.findall(r"[a-z0-9]+", text.lower().replace("_", " "))
    return tuple(_singular(w) for w in words if w not in FILLER)


def _singular(word: str) -> str:
    if len(word) > 4 and word.endswith(("ses", "xes", "ches", "shes")):
        return word[:-2]
    if len(word) > 4 and word.endswith("lves"):
        return word[:-3] + "f"
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us")):
        return word[:-1]
    return word


def _lexical(query: tuple[str, ...], name: tuple[str, ...]) -> float:
    """How well a name matches a query: the same phrase scores 1; a name whose every word is
    in the query ("car" in "a dark saloon car") nearly as much; otherwise the share of words
    they have in common."""
    if not query or not name:
        return 0.0
    if query == name:
        return 1.0
    asked, named = set(query), set(name)
    if named <= asked:
        return 0.9 * (0.5 + 0.5 * len(named) / len(asked))
    shared = len(asked & named)
    return shared / len(asked | named)
