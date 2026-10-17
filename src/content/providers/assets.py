"""Where models come from when the library has nothing for a request: free, openly licensed
collections, searched together (`staging/scan.py`). Each source is a small class, as image
sources are (`providers/images.py`):

- Sketchfab: over a million models, searched by licence; downloading needs a free account's
  API token in `SKETCHFAB_API_TOKEN` (sketchfab.com → Settings → Password & API).
- Poly Pizza: about ten thousand low-poly models (Kenney's, Quaternius's and the old Google
  Poly among them); a free key from poly.pizza/settings/api in `POLY_PIZZA_API_KEY`.
- Gazebo Fuel: an open model library, with Google's thousand scanned household objects.
- The Smithsonian: museum objects, every 3D one CC0 (`SMITHSONIAN_API_KEY` from api.data.gov;
  `DEMO_KEY` works for a few searches an hour).

Only models anyone may use, commercially too, are offered: public domain, or with credit to
their maker (CC BY). Share-alike, non-commercial and no-derivatives models are left out."""

import os
import re
from dataclasses import dataclass
from typing import Any, ClassVar, Protocol

from content.providers.http import RETRY_WAITS

# Free to use as they are; "own": made for the channel (drawn, generated or built by hand);
# "no restrictions": a collection's own terms that ask nothing (CMU's motion capture).
FREE = frozenset({"CC0", "Public Domain", "own", "no restrictions"})
# Free to use with credit to the maker, which the finished video carries.
CREDITED = frozenset({"CC-BY"})
ALLOWED = FREE | CREDITED
USER_AGENT = "content/0.1 (learning project; 3D models for illustration)"


@dataclass(frozen=True)
class Candidate:
    """A model a source offers, with the rights information it gives."""

    source: str
    title: str
    page: str
    file_url: str  # where to download it (for Sketchfab, the model's id)
    file_type: str  # glb, obj (in a zip), …
    licence: str  # one of ALLOWED
    author: str = ""
    faces: int = 0  # 0 when the source does not say
    up: str = "Y"  # the axis its files take as up (glTF's is always Y)
    turn: float = 0.0  # degrees to turn it so its front faces the camera, if its maker's do not


class AssetSource(Protocol):
    name: str

    def search(self, words: str, limit: int) -> list[Candidate]: ...

    def download(self, candidate: Candidate) -> bytes: ...


def licence_terms(label: str) -> str:
    """A source's licence label as one of ALLOWED, or "" when it is not free enough."""
    text = label.lower()
    words = set(re.findall(r"[a-z0-9]+", text))
    if words & {"cc0", "zero"} or "public domain" in text:
        return "CC0"
    restricted = {"sa", "sharealike", "nc", "noncommercial", "nd", "noderivs", "noderivatives"}
    spelt_out = ("share alike", "non commercial", "no deriv")
    if words & restricted or any(phrase in text for phrase in spelt_out):
        return ""
    return "CC-BY" if words & {"by", "attribution"} else ""


class _Http:
    """A source's HTTP client: given (tests), or a real one with the user agent. `key` names
    the setting in `.env` that holds the source's key, if it has one; a source that cannot be
    searched without it (`key_required`) is skipped until it is set."""

    key: ClassVar[str] = ""
    key_required: ClassVar[bool] = False

    @classmethod
    def ready(cls) -> bool:
        return not cls.key_required or bool(os.environ.get(cls.key))

    def __init__(self, http: Any | None, headers: dict[str, str] | None = None) -> None:
        if http is None:
            import httpx

            http = httpx.Client(headers={"User-Agent": USER_AGENT, **(headers or {})}, timeout=60.0)
        self._http = http

    def _get(self, url: str, **params: Any) -> Any:
        """A GET, waiting and trying again while the source says it is too busy."""
        for _ in RETRY_WAITS:
            response = self._http.get(url, params=params or None, follow_redirects=True)
            if response.status_code != 429:
                response.raise_for_status()
                return response
        raise RuntimeError(f"{url} kept refusing (rate limited)")


class Sketchfab(_Http):
    name = "sketchfab"
    api = "https://api.sketchfab.com/v3"
    # Searching is open; downloading needs a signed-in account.
    key, key_required = "SKETCHFAB_API_TOKEN", True

    def __init__(self, http: Any | None = None) -> None:
        token = os.environ.get(self.key, "")
        super().__init__(http, {"Authorization": f"Token {token}"} if token else None)

    def search(self, words: str, limit: int) -> list[Candidate]:
        found = []
        for licence in ("cc0", "by"):
            results = self._get(
                f"{self.api}/search", type="models", q=words, downloadable="true",
                license=licence, count=limit, archives_flavours="false",
            ).json()["results"]  # fmt: skip
            for row in results:
                terms = licence_terms(row["license"]["label"])
                if terms:
                    found.append(
                        Candidate(
                            source=self.name,
                            title=row["name"],
                            page=row["viewerUrl"],
                            file_url=row["uid"],
                            file_type="glb",
                            licence=terms,
                            author=row["user"]["username"],
                            faces=int(row.get("faceCount") or 0),
                        )
                    )
        return found

    def download(self, candidate: Candidate) -> bytes:
        archives = self._get(f"{self.api}/models/{candidate.file_url}/download").json()
        content: bytes = self._get(archives["glb"]["url"]).content
        return content


class PolyPizza(_Http):
    name = "polypizza"
    api = "https://api.poly.pizza/v1"
    key, key_required = "POLY_PIZZA_API_KEY", True

    def __init__(self, http: Any | None = None) -> None:
        super().__init__(http, {"X-Auth-Token": os.environ.get(self.key, "")})

    def search(self, words: str, limit: int) -> list[Candidate]:
        results = self._get(f"{self.api}/search/{words}", limit=limit).json()["results"]
        found = []
        for row in results:
            terms = licence_terms(row.get("Licence", ""))
            if terms and row.get("Download"):
                found.append(
                    Candidate(
                        source=self.name,
                        title=row["Title"],
                        page=f"https://poly.pizza/m/{row['ID']}",
                        file_url=row["Download"],
                        file_type="glb",
                        licence=terms,
                        author=row.get("Creator", {}).get("Username", ""),
                        faces=int(row.get("TriangleCount") or 0),
                    )
                )
        return found

    def download(self, candidate: Candidate) -> bytes:
        content: bytes = self._get(candidate.file_url).content
        return content


class Fuel(_Http):
    """Gazebo Fuel, the open library of models for robot simulation: everyday objects among
    them, Google's scanned household items most of all."""

    name = "fuel"
    api = "https://fuel.gazebosim.org/1.0"

    def __init__(self, http: Any | None = None) -> None:
        super().__init__(http)

    def search(self, words: str, limit: int) -> list[Candidate]:
        rows = self._get(f"{self.api}/models", q=words, per_page=limit).json()
        found = []
        for row in rows:
            terms = licence_terms(row.get("license_name", ""))
            if terms:
                path = f"{row['owner']}/models/{row['name']}"
                found.append(
                    Candidate(
                        source=self.name,
                        title=row.get("description") or row["name"].replace("_", " "),
                        page=f"https://app.gazebosim.org/{path}",
                        file_url=f"{self.api}/{path}.zip",
                        file_type="zip",
                        licence=terms,
                        author=row["owner"],
                        up="Z",  # as robot simulators draw the world
                    )
                )
        return found

    def download(self, candidate: Candidate) -> bytes:
        content: bytes = self._get(candidate.file_url).content
        return content


class Smithsonian(_Http):
    """The Smithsonian Open Access API: museum objects, scanned."""

    name = "smithsonian"
    api = "https://api.si.edu/openaccess/api/v1.0/search"
    # Without a key, the shared demo key allows a few searches an hour.
    key = "SMITHSONIAN_API_KEY"

    def __init__(self, http: Any | None = None) -> None:
        super().__init__(http)
        self._key = os.environ.get(self.key, "DEMO_KEY")

    def search(self, words: str, limit: int) -> list[Candidate]:
        response = self._get(self.api, q=words, rows=100, api_key=self._key)
        found = []
        for row in response.json()["response"]["rows"]:
            record = row.get("content", {}).get("descriptiveNonRepeating", {})
            for media in record.get("online_media", {}).get("media", []):
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
                            page=record.get("record_link", ""),
                            file_url=best["url"],
                            file_type=_file_type(best),
                            licence="CC0",
                            author=record.get("data_source", ""),
                        )
                    )
                    break
            if len(found) >= limit:
                break
        return found

    def download(self, candidate: Candidate) -> bytes:
        content: bytes = self._get(candidate.file_url).content
        return content


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
