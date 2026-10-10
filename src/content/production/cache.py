"""Content-addressed storage for generated media.

Every paid generation is keyed by its full request, including the digests of any
input files. Asking again for the same thing returns the stored file for free, so a
rerun, a crash, or a revision of one scene never pays twice for unchanged assets.
"""

import hashlib
import json
import uuid
from collections.abc import Callable, Mapping
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
        return path, usage
