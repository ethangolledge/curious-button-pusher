"""Where reference images come from. Wikimedia Commons first: a free API, and every file
carries its licence and author. Sources are tried in order."""

import hashlib
import html
import re
import subprocess
import time
from typing import Any, Protocol

from content.providers.http import RETRY_WAITS, retry_after
from content.schemas.references import FoundImage

# Wikimedia asks every API client to identify itself.
USER_AGENT = "content/0.1 (learning project; reference images for illustration)"
IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp")


class ImageSource(Protocol):
    name: str

    def search(self, query: str, limit: int) -> list[FoundImage]: ...

    def download(self, url: str) -> bytes: ...


class WikimediaCommons:
    name = "wikimedia_commons"
    api = "https://commons.wikimedia.org/w/api.php"

    def __init__(self, http: Any | None = None) -> None:
        if http is None:
            import httpx

            http = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30.0)
        self._http = http

    def search(self, query: str, limit: int) -> list[FoundImage]:
        response = self._get(
            self.api,
            params={
                "action": "query",
                "format": "json",
                "generator": "search",
                "gsrsearch": f"{query} filetype:bitmap",
                "gsrnamespace": 6,
                "gsrlimit": limit,
                "prop": "imageinfo",
                "iiprop": "url|size|mime|extmetadata",
                "iiurlwidth": 1024,
            },
        )
        response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", {}).values()
        found = []
        for page in sorted(pages, key=lambda page: page.get("index", 0)):
            info = (page.get("imageinfo") or [{}])[0]
            if info.get("mime") not in IMAGE_TYPES:
                continue
            meta = info.get("extmetadata", {})
            found.append(
                FoundImage(
                    source=self.name,
                    title=page["title"].removeprefix("File:"),
                    description=_plain(meta.get("ImageDescription", {}).get("value", ""))[:300],
                    image_url=info.get("thumburl") or info["url"],
                    page_url=info["descriptionurl"],
                    licence=meta.get("LicenseShortName", {}).get("value"),
                    author=_plain(meta.get("Artist", {}).get("value", "")) or None,
                    width=info["width"],
                    height=info["height"],
                )
            )
        return found

    def download(self, url: str) -> bytes:
        response = self._get(url)
        response.raise_for_status()
        content: bytes = response.content
        return content

    def _get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """GET, waiting and retrying while Wikimedia rate-limits (429); many reference
        downloads in a row are enough to trip it."""
        for wait in RETRY_WAITS:
            response = self._http.get(url, params=params)
            if response.status_code != 429:
                return response
            time.sleep(retry_after(response) or wait)
        return self._http.get(url, params=params)


class FakeImageSource:
    """Deterministic offline stand-in: a dark still per result, titled with the query."""

    name = "fake"

    def __init__(self) -> None:
        self.searches: list[str] = []

    def search(self, query: str, limit: int) -> list[FoundImage]:
        self.searches.append(query)
        return [
            FoundImage(
                source=self.name,
                title=f"{query} ({index})",
                description=f"A photograph of {query}.",
                image_url=f"fake://{query}/{index}",
                page_url=f"fake://{query}/{index}/page",
                licence="CC BY 4.0",
                author="Fake Photographer",
                width=1024,
                height=768,
            )
            for index in range(1, limit + 1)
        ]

    def download(self, url: str) -> bytes:
        shade = 40 + hashlib.sha256(url.encode()).digest()[0] % 40
        result = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                "-i", f"color=c=0x{shade:02x}{shade:02x}{shade:02x}:s=320x240",
                "-frames:v", "1", "-f", "image2pipe", "-c:v", "png", "-",
            ],
            capture_output=True,
            check=True,
        )  # fmt: skip
        return result.stdout


def _plain(markup: str) -> str:
    """Commons metadata is HTML; keep only the words."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", markup)).split())
