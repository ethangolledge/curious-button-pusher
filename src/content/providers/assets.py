"""Where models come from when the library has nothing for a request. The Smithsonian's open
access collection first: free, every 3D model in it marked CC0 (public domain), with the
museum's page for each. Sources are tried in order; each is a small class, as image sources
are (`providers/images.py`)."""

import os
from dataclasses import dataclass
from typing import Any, Protocol

from content.providers.http import RETRY_WAITS

# Only these may enter a library: anything else needs attribution, or forbids commercial use.
# "own": made for the channel (drawn, generated or built by hand), so the channel's to use.
FREE = frozenset({"CC0", "Public Domain", "own"})
USER_AGENT = "content/0.1 (learning project; 3D models for illustration)"


@dataclass(frozen=True)
class Candidate:
    """A model a source offers, with the rights information it gives."""

    source: str
    title: str
    page: str
    file_url: str
    file_type: str  # glb, obj (in a zip), …
    licence: str
    author: str = ""


class AssetSource(Protocol):
    name: str

    def search(self, words: str, limit: int) -> list[Candidate]: ...

    def download(self, url: str) -> bytes: ...


class Smithsonian:
    """The Smithsonian Open Access API. It needs a free key from api.data.gov, read from
    `SMITHSONIAN_API_KEY`; `DEMO_KEY` works for a few searches an hour."""

    name = "smithsonian"
    api = "https://api.si.edu/openaccess/api/v1.0/search"

    def __init__(self, http: Any | None = None) -> None:
        if http is None:
            import httpx

            http = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60.0)
        self._http = http
        self._key = os.environ.get("SMITHSONIAN_API_KEY", "DEMO_KEY")

    def search(self, words: str, limit: int) -> list[Candidate]:
        response = self._http.get(self.api, params={"q": words, "rows": 100, "api_key": self._key})
        response.raise_for_status()
        found = []
        for row in response.json()["response"]["rows"]:
            content = row.get("content", {})
            for media in (
                content.get("descriptiveNonRepeating", {}).get("online_media", {}).get("media", [])
            ):
                if (
                    media.get("type") != "3d_voyager"
                    or media.get("usage", {}).get("access") != "CC0"
                ):
                    continue
                best = _best_file(media.get("resources", []))
                if best is not None:
                    found.append(
                        Candidate(
                            source=self.name,
                            title=row.get("title", ""),
                            page=content.get("descriptiveNonRepeating", {}).get("record_link", ""),
                            file_url=best["url"],
                            file_type=_file_type(best),
                            licence="CC0",
                            author=content.get("descriptiveNonRepeating", {}).get(
                                "data_source", ""
                            ),
                        )
                    )
                    break
            if len(found) >= limit:
                break
        return found

    def download(self, url: str) -> bytes:
        for _ in RETRY_WAITS:
            response = self._http.get(url, follow_redirects=True)
            if response.status_code != 429:
                response.raise_for_status()
                content: bytes = response.content
                return content
        raise RuntimeError(f"the Smithsonian kept refusing {url} (rate limited)")


def _file_type(resource: dict[str, Any]) -> str:
    attributes = {k: v for item in resource.get("attributes", []) for k, v in item.items()}
    return str(attributes.get("MODEL_FILE_TYPE", attributes.get("FILE_TYPE", ""))).lower()


def _best_file(resources: list[dict[str, Any]]) -> dict[str, Any] | None:
    """A glb if there is one (the medium quality, small enough to render quickly), else an
    obj package."""
    meshes = [r for r in resources if r.get("type") == "3D mesh"]
    for wanted in ("glb", "obj"):
        options = [r for r in meshes if _file_type(r) == wanted]
        if options:
            options.sort(
                key=lambda r: (
                    "Medium" not in r.get("category", ""),
                    "Full" in r.get("category", ""),
                )
            )
            return options[0]
    return None


class FakeAssetSource:
    """Offline stand-in: one CC0 candidate per search, named after the words."""

    name = "fake"

    def __init__(self, payload: bytes = b"model") -> None:
        self.payload = payload
        self.searches: list[str] = []

    def search(self, words: str, limit: int) -> list[Candidate]:
        self.searches.append(words)
        return [
            Candidate(
                self.name, words.title(), f"fake://{words}", f"fake://{words}.glb", "glb", "CC0"
            )
        ][:limit]

    def download(self, url: str) -> bytes:
        return self.payload
