"""The models a channel can put in a shot: the props the engine makes in code, and the
channel's own library of fetched or generated models (`themes/<name>/assets/library.json`,
private, kept in its archive with the rest of the channel).

Search is by meaning, not spelling: every model has one id and the other words for it, and a
search matches whole phrases, the words in them, and (when a local embedding model is
available) what they mean. Adding a model that a search already finds is refused, so the
library never holds the same thing twice under different names."""

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from content.blender.blocks.base import Prop, summary
from content.blender.registry import discover
from content.blender.rehearsal import RehearsalStage

LIBRARY = "library.json"
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


@dataclass(frozen=True)
class Model:
    model_id: str
    names: tuple[str, ...]
    describe: str
    size: tuple[float, float, float]
    capabilities: tuple[str, ...] = ()
    # Where it came from: "made in code" for the engine's props.
    source: str = "made in code"
    licence: str = ""
    page: str = ""
    author: str = ""
    cost_usd: float = 0.0
    file: str = ""  # relative to the library folder
    used_in: tuple[str, ...] = ()

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

    def get(self, model_id: str) -> Model:
        if model_id not in self.models:
            raise KeyError(f"no model '{model_id}' (see: content staging models)")
        return self.models[model_id]

    def search(self, words: str, embed: Embed | None = None, limit: int = 5) -> list[Found]:
        query = _terms(words)
        scores = {
            m.model_id: max(_lexical(query, _terms(w)) for w in m.words)
            for m in self.models.values()
        }
        if embed is not None and self.models:
            texts = [f"{m.words[0]}: {m.describe}" for m in self.models.values()]
            vectors = embed([words, *texts])
            asked, rest = vectors[0], vectors[1:]
            similarity = (
                rest @ asked / (np.linalg.norm(rest, axis=1) * np.linalg.norm(asked) + 1e-12)
            )
            for model, close in zip(self.models.values(), similarity, strict=True):
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
        self.save()

    def name(self, model_id: str, words: str) -> None:
        """Another word for a model, so searches find it."""
        model = self.get(model_id)
        if model.source == "made in code":
            raise ValueError(f"'{model_id}' is made in code: add the words to its file's `names`")
        if words not in model.names:
            self.models[model_id] = _replace(model, names=(*model.names, words))
            self.save()

    def used(self, model_id: str, video: str) -> None:
        model = self.get(model_id)
        if model.source != "made in code" and video not in model.used_in:
            self.models[model_id] = _replace(model, used_in=(*model.used_in, video))
            self.save()

    def path(self, model: Model) -> Path | None:
        return self.folder / model.file if self.folder is not None and model.file else None

    def save(self) -> None:
        assert self.folder is not None
        kept = [asdict(m) for m in self.models.values() if m.source != "made in code"]
        self.folder.mkdir(parents=True, exist_ok=True)
        text = json.dumps({"models": sorted(kept, key=lambda m: m["model_id"])}, indent=2)
        (self.folder / LIBRARY).write_text(text + "\n", encoding="utf-8")


def load_library(folder: Path | None, channel_blocks: Sequence[Path] = ()) -> Library:
    """The engine's props and, if a channel folder is given, its own models."""
    library = Library(folder)
    for prop in discover(channel_blocks, ("props",)).props().values():
        library.models[prop.name] = Model(
            model_id=prop.name,
            names=prop.names,
            describe=summary(prop),
            size=_measured(prop),
            capabilities=tuple(sorted(prop.capabilities)),
        )
    stored = folder / LIBRARY if folder is not None else None
    if stored is not None and stored.is_file():
        for data in json.loads(stored.read_text(encoding="utf-8"))["models"]:
            data["names"] = tuple(data["names"])
            data["size"] = tuple(data["size"])
            data["capabilities"] = tuple(data.get("capabilities", ()))
            data["used_in"] = tuple(data.get("used_in", ()))
            model = Model(**data)
            if model.model_id in library.models:
                raise ValueError(f"{stored}: '{model.model_id}' is already a prop made in code")
            library.models[model.model_id] = model
    return library


def _measured(prop: type[Prop]) -> tuple[float, float, float]:
    """A prop's width, depth and height, from building it without Blender."""
    stage = RehearsalStage(frames=1)
    size = stage.bounds(prop().build(stage, prop.name)).size
    return (round(size.x, 3), round(size.y, 3), round(size.z, 3))


def _replace(model: Model, **changes: object) -> Model:
    return Model(**{**asdict(model), **changes})


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
