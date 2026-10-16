"""`python -m sam3d fetch`: copy the pinned model weights from Hugging Face into the weights
bucket, once. Each file streams straight from Hugging Face into the bucket (nothing touches
the container's memory-backed disk) and is checked against the hash Hugging Face publishes for
that revision; a file that does not match is deleted and the fetch fails.

The files land in Hugging Face's own cache layout (`hf/models--<org>--<name>/snapshots/<rev>/`),
so the run job reads them offline exactly as if they had been downloaded there. A repository's
`refs/main` is written last: a repository without it was not fetched completely. Files already
in the bucket with the right hash are skipped, so running it again only finishes what is missing.

Needs HF_TOKEN (from Secret Manager, never the image) and WEIGHTS_BUCKET."""

import fnmatch
import hashlib
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

HUB = "https://huggingface.co"
MODELS = Path(__file__).parents[1] / "models.json"
CHUNK = 64 * 1024 * 1024


def main() -> None:
    from google.cloud import storage

    token = os.environ["HF_TOKEN"].strip()
    bucket = storage.Client().bucket(os.environ["WEIGHTS_BUCKET"])
    for repo, pin in json.loads(MODELS.read_text(encoding="utf-8")).items():
        root = f"hf/models--{repo.replace('/', '--')}"
        files = [
            f for f in _tree(repo, pin["revision"], token) if _wanted(f["path"], pin["include"])
        ]
        if not files:
            raise SystemExit(f"{repo}@{pin['revision']}: nothing matches {pin['include']}")
        for entry in files:
            _copy(
                bucket, repo, pin["revision"], entry, f"{root}/snapshots/{pin['revision']}", token
            )
        bucket.blob(f"{root}/refs/main").upload_from_string(pin["revision"])
        print(f"{repo}@{pin['revision'][:12]}: {len(files)} files ready", flush=True)


def _tree(repo: str, revision: str, token: str) -> list[dict[str, Any]]:
    """Every file of the repository at that revision, with its size and published hash."""
    files: list[dict[str, Any]] = []
    url: str | None = f"{HUB}/api/models/{repo}/tree/{revision}?recursive=true"
    while url:
        with urllib.request.urlopen(_get(url, token), timeout=60) as answer:
            files += [entry for entry in json.load(answer) if entry["type"] == "file"]
            url = _next_page(answer.headers.get("Link", ""))
    return files


def _wanted(path: str, include: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in include)


def _copy(
    bucket: Any, repo: str, revision: str, entry: dict[str, Any], prefix: str, token: str
) -> None:
    path, size = entry["path"], entry["size"]
    expected = entry["lfs"]["oid"] if entry.get("lfs") else entry["oid"]
    blob = bucket.blob(f"{prefix}/{path}")
    if blob.exists():
        blob.reload()
        if (blob.metadata or {}).get("hf_oid") == expected and blob.size == size:
            return
    # Large files are hashed with SHA-256 (Git LFS); small ones as a git blob, with SHA-1.
    digest = hashlib.sha256() if entry.get("lfs") else hashlib.sha1(f"blob {size}\0".encode())
    url = f"{HUB}/{repo}/resolve/{revision}/{urllib.parse.quote(path)}"
    blob.metadata = {"hf_oid": expected}
    with (
        urllib.request.urlopen(_get(url, token), timeout=120) as answer,
        blob.open("wb", chunk_size=CHUNK) as out,
    ):
        while chunk := answer.read(CHUNK):
            digest.update(chunk)
            out.write(chunk)
    if digest.hexdigest() != expected:
        blob.delete()
        raise SystemExit(
            f"{repo}/{path}: hash {digest.hexdigest()} is not the published {expected}"
        )
    print(f"  {path} ({size / 1e6:.0f} MB)", flush=True)


def _get(url: str, token: str) -> urllib.request.Request:
    request = urllib.request.Request(url)
    # Sent to huggingface.co only, never along a redirect to the file host.
    request.add_unredirected_header("Authorization", f"Bearer {token}")
    return request


def _next_page(link: str) -> str | None:
    for part in link.split(","):
        if 'rel="next"' in part:
            return part.split(";")[0].strip(" <>")
    return None
