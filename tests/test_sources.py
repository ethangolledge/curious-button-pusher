"""Reading the model sources' own data: Infinigen's generators found by plain words, and
Objaverse's index holding only good, single, freely licensed models, searched by words."""

import gzip
import json
from pathlib import Path

import pytest

from content.providers import infinigen, objaverse
from content.providers.infinigen import Infinigen
from content.providers.objaverse import Objaverse

GENERATORS = """infinigen.assets.objects.seating.chairs.OfficeChairFactory
infinigen.assets.objects.seating.SofaFactory
infinigen.assets.objects.tables.TableDiningFactory
infinigen.assets.objects.tableware.WineglassFactory
"""


def test_an_infinigen_generator_is_found_by_the_words_for_what_it_makes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listed = tmp_path / infinigen.LISTS[0]
    listed.parent.mkdir(parents=True)
    listed.write_text(GENERATORS, encoding="utf-8")
    monkeypatch.setattr(infinigen, "HOME", tmp_path)

    chairs = Infinigen().search("office chair", 6)
    tables = Infinigen().search("dining tables", 6)

    assert [c.title for c in chairs][:2] == [
        "office chair (variation 1)",
        "office chair (variation 2)",
    ]
    assert chairs[0].file_url == "infinigen.assets.objects.seating.chairs.OfficeChairFactory#1"
    assert chairs[0].licence == "own" and chairs[0].turn == infinigen.TURN
    assert len({c.page for c in chairs}) == len(chairs)  # each variation its own
    assert tables[0].title.startswith("table dining")
    assert Infinigen().search("oil tanker", 6) == []


def _graded(uid: str, score: int, *, scene: bool = False) -> dict[str, object]:
    """One of Objaverse++'s judgements."""
    return {"UID": uid, "score": score, "style": "realistic",
            "is_scene": "true" if scene else "false", "is_multi_object": "false"}  # fmt: skip


def _record(
    name: str, licence: str, faces: int = 2000, tags: tuple[str, ...] = ()
) -> dict[str, object]:
    return {"name": name, "license": licence, "faceCount": str(faces),
            "user": {"username": "a maker"}, "tags": [{"name": t} for t in tags],
            "categories": []}  # fmt: skip


def test_objaverse_offers_only_good_single_freely_licensed_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = {
        "u1": _record("Ballot Box", "by", tags=("election",)),
        "u2": _record("ballot box (share alike)", "by-sa"),
        "u3": _record("Ballot box, poor", "cc0"),
        "u4": _record("Polling station with ballot boxes", "cc0"),
        "u5": _record("Wooden ballot box", "cc0"),
    }
    quality = [_graded("u1", 3), _graded("u2", 3), _graded("u3", 0),
               _graded("u4", 3, scene=True), _graded("u5", 2)]  # fmt: skip
    scores = tmp_path / "scores.json"
    scores.write_text(json.dumps(quality, indent=4), encoding="utf-8")
    paths = {uid: f"glbs/000-000/{uid}.glb" for uid in records}

    class Http:
        def get(self, url: str) -> object:
            return type("Response", (), {"content": gzip.compress(json.dumps(records).encode())})

    monkeypatch.setattr(objaverse, "HOME", tmp_path)
    monkeypatch.setattr(objaverse, "INDEX", tmp_path / "index.sqlite")
    monkeypatch.setattr(objaverse, "SHARDS", 1)
    monkeypatch.setattr(objaverse, "_fetch", lambda http, url, target: target.write_bytes(
        scores.read_bytes() if url == objaverse.QUALITY
        else gzip.compress(json.dumps(paths).encode())))  # fmt: skip
    monkeypatch.setattr("httpx.Client", lambda **_: _Context(Http()))

    objaverse.build_index(lambda _: None)
    found = Objaverse(http=Http()).search("ballot box", 8)

    assert [c.title for c in found] == ["Ballot Box", "Wooden ballot box"]  # best first
    assert [c.licence for c in found] == ["CC-BY", "CC0"]
    assert found[0].file_url.endswith("glbs/000-000/u1.glb") and found[0].author == "a maker"


class _Context:
    def __init__(self, inner: object) -> None:
        self.inner = inner

    def __enter__(self) -> object:
        return self.inner

    def __exit__(self, *_: object) -> None:
        return None
