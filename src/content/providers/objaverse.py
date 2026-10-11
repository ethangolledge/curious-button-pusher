"""Objaverse (the Allen Institute's collection of about 800,000 Sketchfab models, each with
its own Creative Commons licence) as a source of models, searched on this computer: a
local index (`.cache/objaverse/index.sqlite`) of every model's name, tags, categories,
licence and maker, and Objaverse++'s quality score for each (0 to 3, judged from its
renders). Only CC0 and CC BY models of good quality that are one thing (not a scene) are
offered; files come from Hugging Face, no key needed.

`content staging objaverse` builds the index (about 800 MB of metadata, once)."""

import gzip
import json
import re
import sqlite3
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from content.providers.assets import Candidate, licence_terms

PROJECT = Path(__file__).parents[3]
HOME = PROJECT / ".cache" / "objaverse"
INDEX = HOME / "index.sqlite"
DATASET = "https://huggingface.co/datasets/allenai/objaverse/resolve/main"
QUALITY = (
    "https://huggingface.co/datasets/cindyxl/ObjaversePlusPlus/resolve/main/annotated_800k.json"
)
SHARDS = 160
# Each model's judgement: its score and style, and whether it is a scene or several things.
Graded = dict[str, dict[str, Any]]
# Offered from this quality (Objaverse++: 0 poor to 3 excellent).
GOOD = 2
TOO_DETAILED = 1_000_000
SCHEMA = """
create table if not exists models (
    uid text primary key, name text, maker text, licence text, faces integer, path text,
    quality integer, style text
);
create virtual table if not exists words using fts5(uid unindexed, name, tags, categories);
"""


class Objaverse:
    name = "objaverse"
    key = ""
    key_required = False

    def __init__(self, http: Any | None = None) -> None:
        if http is None:
            import httpx

            http = httpx.Client(timeout=300.0, follow_redirects=True)
        self._http = http

    @classmethod
    def ready(cls) -> bool:
        return INDEX.is_file()

    def search(self, words: str, limit: int) -> list[Candidate]:
        terms = [t for t in re.findall(r"[a-z0-9]+", words.lower()) if len(t) > 2]
        if not terms:
            return []
        # Every word wanted, each as itself or its plural.
        query = " AND ".join(f'("{t}" OR "{t}s" OR "{t.rstrip("s")}")' for t in terms)
        with sqlite3.connect(INDEX) as db:
            rows = db.execute(
                "select m.uid, m.name, m.maker, m.licence, m.faces, m.path from words w "
                "join models m on m.uid = w.uid where words match ? and m.quality >= ? "
                "and m.faces <= ? order by m.quality desc, bm25(words) limit ?",
                (query, GOOD, TOO_DETAILED, limit),
            ).fetchall()
        return [
            Candidate(
                source=self.name,
                title=name,
                page=f"https://sketchfab.com/3d-models/{uid}",
                file_url=f"{DATASET}/{path}",
                file_type="glb",
                licence=licence,
                author=maker,
                faces=faces,
            )
            for uid, name, maker, licence, faces, path in rows
        ]

    def download(self, candidate: Candidate) -> bytes:
        response = self._http.get(candidate.file_url)
        response.raise_for_status()
        content: bytes = response.content
        return content


def build_index(say: Callable[[str], None]) -> None:
    """Fetch Objaverse's metadata and Objaverse++'s scores, and index the models anyone may
    use: CC0 or CC BY, one thing, not a scene."""
    import httpx

    HOME.mkdir(parents=True, exist_ok=True)
    with (
        tempfile.TemporaryDirectory(dir=HOME) as work,
        httpx.Client(timeout=600.0, follow_redirects=True) as http,
    ):
        say("Fetching the quality scores (Objaverse++)…")
        scores = Path(work) / "scores.json"
        _fetch(http, QUALITY, scores)
        quality = dict(_quality(scores))
        say("Fetching where each model's file is…")
        paths_file = Path(work) / "paths.json.gz"
        _fetch(http, f"{DATASET}/object-paths.json.gz", paths_file)
        paths: dict[str, str] = json.loads(gzip.decompress(paths_file.read_bytes()))
        building = INDEX.with_suffix(".building")
        building.unlink(missing_ok=True)
        with sqlite3.connect(building) as db:
            db.executescript(SCHEMA)
            for shard in range(SHARDS):
                say(f"Indexing part {shard + 1} of {SHARDS}…")
                name = f"{shard // 1000:03d}-{shard % 1000:03d}.json.gz"
                records = json.loads(
                    gzip.decompress(http.get(f"{DATASET}/metadata/{name}").content)
                )
                db.executemany("insert or replace into models values (?, ?, ?, ?, ?, ?, ?, ?)",
                               _rows(records, paths, quality))  # fmt: skip
                db.executemany("insert into words values (?, ?, ?, ?)",
                               _words(records, paths, quality))  # fmt: skip
        building.replace(INDEX)


def _usable(uid: str, record: dict[str, Any], paths: dict[str, str], quality: Graded) -> bool:
    graded = quality.get(uid)
    return (
        uid in paths
        and graded is not None
        and not graded["scene"]
        and not graded["multi"]
        and bool(licence_terms(_licence_label(record.get("license", ""))))
    )


def _rows(
    records: dict[str, Any], paths: dict[str, str], quality: Graded
) -> Iterator[tuple[Any, ...]]:
    for uid, record in records.items():
        if _usable(uid, record, paths, quality):
            yield (
                uid, record.get("name", ""), (record.get("user") or {}).get("username", ""),
                licence_terms(_licence_label(record.get("license", ""))),
                int(record.get("faceCount") or 0), paths[uid], quality[uid]["score"],
                quality[uid]["style"],
            )  # fmt: skip


def _words(
    records: dict[str, Any], paths: dict[str, str], quality: Graded
) -> Iterator[tuple[Any, ...]]:
    for uid, record in records.items():
        if _usable(uid, record, paths, quality):
            tags = " ".join(t.get("name", "") for t in record.get("tags") or [])
            categories = " ".join(c.get("name", "") for c in record.get("categories") or [])
            yield uid, record.get("name", ""), tags, categories


def _licence_label(slug: str) -> str:
    """Objaverse's licence slugs ("by", "cc0", "by-nc") as the words licence_terms reads."""
    return "cc0" if slug == "cc0" else f"attribution {slug.replace('-', ' ')}"


def _quality(path: Path) -> Iterator[tuple[str, dict[str, Any]]]:
    """Objaverse++'s judgements, read entry by entry (the file is a quarter of a gigabyte)."""
    entry: dict[str, Any] = {}
    with path.open(encoding="utf-8") as lines:
        for line in lines:
            found = re.match(r'\s*"(\w+)":\s*"?([^",]*)"?,?\s*$', line)
            if found:
                entry[found.group(1)] = found.group(2)
            elif line.strip().startswith("}") and "UID" in entry:
                yield (
                    entry["UID"],
                    {
                        "score": int(entry.get("score", 0)),
                        "style": entry.get("style", ""),
                        "scene": entry.get("is_scene") == "true",
                        "multi": entry.get("is_multi_object") == "true",
                    },
                )
                entry = {}


def _fetch(http: Any, url: str, target: Path) -> None:
    with http.stream("GET", url) as response:
        response.raise_for_status()
        with target.open("wb") as out:
            for chunk in response.iter_bytes():
                out.write(chunk)
