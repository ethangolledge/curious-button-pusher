"""Where a channel's models are kept: `themes/<name>/assets/catalogue.sqlite` and the files
beside it, private to the channel and saved with it.

- `models`: one row a model, its record as JSON beside the columns worth asking about
  (where it came from, its licence, whether a person kept it or it was taken automatically,
  or turned down);
- `lineage`: every step that made or changed a model (fetched, prepared, scored, taken,
  versioned, turned down), with what the step was given and decided, so any model can be
  traced back to its source and remade;
- `usage`: which videos used which models.

Files are stored by what they hold (`files/<hash>.glb`): the same file fetched twice is
kept once, and a record can never point at a file that has changed under it."""

import hashlib
import json
import shutil
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DATABASE = "catalogue.sqlite"
FILES = "files"
# What came before the database: one JSON file, read once and kept as a backup.
OLD_LIBRARY = "library.json"
SCHEMA = """
create table if not exists models (
    model_id text primary key,
    source text not null,
    licence text not null,
    status text not null,
    record text not null
);
create table if not exists lineage (
    model_id text not null,
    at text not null,
    step text not null,
    detail text not null
);
create table if not exists usage (
    model_id text not null,
    video text not null,
    at text not null,
    primary key (model_id, video)
);
"""


class Store:
    def __init__(self, folder: Path) -> None:
        self.folder = folder

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        self.folder.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.folder / DATABASE)
        try:
            connection.executescript(SCHEMA)
            yield connection
            connection.commit()
        finally:
            connection.close()

    def records(self) -> list[dict[str, Any]]:
        """Every model's record; on first use, those of the old JSON library, moved in."""
        if not (self.folder / DATABASE).is_file():
            self._move_old_library()
        if not (self.folder / DATABASE).is_file():
            return []
        with self._db() as db:
            rows = db.execute("select record from models order by model_id").fetchall()
        return [json.loads(row[0]) for row in rows]

    def write(self, record: Mapping[str, Any]) -> None:
        with self._db() as db:
            db.execute(
                "insert or replace into models values (?, ?, ?, ?, ?)",
                (
                    record["model_id"],
                    record["source"],
                    record["licence"],
                    record.get("status", "kept"),
                    json.dumps(record, sort_keys=True),
                ),
            )

    def note(self, model_id: str, step: str, detail: Mapping[str, Any]) -> None:
        """A step in a model's making, for its lineage."""
        with self._db() as db:
            db.execute(
                "insert into lineage values (?, ?, ?, ?)",
                (model_id, _now(), step, json.dumps(detail, sort_keys=True)),
            )

    def lineage(self, model_id: str) -> list[tuple[str, str, dict[str, Any]]]:
        with self._db() as db:
            rows = db.execute(
                "select at, step, detail from lineage where model_id = ? order by rowid",
                (model_id,),
            ).fetchall()
        return [(at, step, json.loads(detail)) for at, step, detail in rows]

    def used(self, model_id: str, video: str) -> None:
        with self._db() as db:
            db.execute("insert or ignore into usage values (?, ?, ?)", (model_id, video, _now()))

    def usage(self, model_id: str) -> list[str]:
        with self._db() as db:
            rows = db.execute(
                "select video from usage where model_id = ? order by at", (model_id,)
            ).fetchall()
        return [row[0] for row in rows]

    def keep_file(self, source: Path) -> str:
        """A file kept by what it holds; returns its path within the library folder."""
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:20]
        relative = f"{FILES}/{digest}{source.suffix.lower()}"
        target = self.folder / relative
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        return relative

    def _move_old_library(self) -> None:
        old = self.folder / OLD_LIBRARY
        if not old.is_file():
            return
        for record in json.loads(old.read_text(encoding="utf-8"))["models"]:
            record.pop("used_in", None)
            self.write(record)
            self.note(record["model_id"], "moved", {"from": OLD_LIBRARY})
        old.rename(old.with_suffix(".json.moved"))


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
