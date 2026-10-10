"""Content-addressed storage for every paid generation: media and text.

Every paid generation is keyed by its full request, including the digests of any input
files. Asking again for the same thing returns the stored file for free, so a rerun, a
crash, or a revision of one scene never pays twice for unchanged work. `INDEX.csv` at the
cache's root lists everything that was paid for, readably: when, what, which model, the
cost, and the file.
"""

import csv
import hashlib
import json
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from content.providers.base import Usage


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AssetCache:
    def __init__(self, root: Path) -> None:
        self.root = root

    def fetch(
        self,
        kind: str,
        request: Mapping[str, Any],
        suffix: str,
        produce: Callable[[], tuple[bytes, Usage]],
        *,
        refusal: type[Exception] | None = None,
        about: str = "",
    ) -> tuple[Path, Usage | None]:
        """Return the stored asset, or produce and store it. Usage is None on a cache hit.

        A `refusal` raised by `produce` is remembered too, and raised again from the cache:
        a resumed run otherwise paid to be refused once more."""
        encoded = json.dumps({"kind": kind, **request}, sort_keys=True, default=str)
        key = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]
        path = self.root / kind / f"{key}{suffix}"
        refused = path.with_suffix(".refused")
        if path.is_file():
            return path, None
        if refusal is not None and refused.is_file():
            raise refusal(refused.read_text(encoding="utf-8"))
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            content, usage = produce()
        except Exception as error:
            if refusal is not None and isinstance(error, refusal):
                refused.write_text(str(error), encoding="utf-8")
            raise
        path.with_suffix(".request.json").write_text(encoded, encoding="utf-8")
        # Write then rename, so an interrupted run never leaves a half-written asset. Each
        # write gets its own partial file: identical requests can run in parallel.
        partial = path.with_suffix(f"{suffix}.{uuid.uuid4().hex}.partial")
        partial.write_bytes(content)
        partial.replace(path)
        self._index(kind, about, usage, path)
        return path, usage

    def _index(self, kind: str, about: str, usage: Usage, path: Path) -> None:
        """One readable line per paid generation, so what the cache holds can be seen."""
        index = self.root / "INDEX.csv"
        new = not index.is_file()
        with index.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            if new:
                writer.writerow(["when", "kind", "about", "model", "cost_usd", "file"])
            writer.writerow(
                [
                    datetime.now(UTC).isoformat(timespec="seconds"),
                    kind,
                    " ".join(about.split())[:200],
                    usage.model,
                    "" if usage.cost_usd is None else f"{usage.cost_usd:.4f}",
                    path.relative_to(self.root).as_posix(),
                ]
            )
