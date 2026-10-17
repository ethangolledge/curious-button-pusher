"""Where people's motions come from: free motion capture recordings (BVH), fetched one take at
a time.

- The CMU Graphics Lab Motion Capture Database: "may be copied, modified, or redistributed
  without permission" (mocap.cs.cmu.edu/faqs.php), in Bruce Hahne's BVH conversion, which adds
  no restrictions; each take is its own small zip in a public mirror.
- 100STYLE (Ian Mason, CC BY 4.0: a video using it credits "The 100STYLE Dataset - Ian
  Mason"): a hundred styles of walking and standing, all in one 1.5 GB zip on Zenodo, of which
  only the takes asked for are read (HTTP range requests: a few MB each)."""

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from content.providers.assets import USER_AGENT

Source = Literal["cmu", "100style"]
CMU_MIRROR = "https://raw.githubusercontent.com/Shriinivas/cmubvh/main"
# CMU's takes by subject, as the mirror groups them.
CMU_GROUPS = (
    (1, 9), (10, 14), (15, 19), (20, 29), (30, 34), (35, 39), (40, 45), (46, 56), (60, 75),
    (76, 80), (81, 85), (86, 94), (102, 111), (113, 128), (131, 135), (136, 140), (141, 144),
)  # fmt: skip
STYLE_ZIP = "https://zenodo.org/records/8127870/files/100STYLE.zip?download=1"
# Read from a remote zip this much at a time.
CHUNK = 1 << 20


@dataclass(frozen=True)
class Rights:
    source: str
    licence: str
    author: str
    page: str


RIGHTS: dict[Source, Rights] = {
    "cmu": Rights(
        "CMU Graphics Lab Motion Capture Database",
        "no restrictions",  # "may be copied, modified, or redistributed without permission"
        "Carnegie Mellon University",
        "http://mocap.cs.cmu.edu",
    ),
    "100style": Rights(
        "The 100STYLE Dataset", "CC-BY", "Ian Mason", "https://www.ianxmason.com/100style/"
    ),
}


def fetch(source: Source, take: str, folder: Path) -> Path:
    """A take's BVH, downloaded into `folder` (once): a CMU take by its number ("113_15"), a
    100STYLE take by its file ("Neutral/Neutral_FW.bvh")."""
    target = folder / f"{source}-{take.replace('/', '-')}"
    target = target if target.suffix == ".bvh" else target.with_suffix(".bvh")
    if target.is_file():
        return target
    folder.mkdir(parents=True, exist_ok=True)
    if source == "cmu":
        data = _cmu(take)
    else:
        with zipfile.ZipFile(io.BufferedReader(_Remote(STYLE_ZIP), CHUNK)) as styles:
            data = styles.read(f"100STYLE/{take}")
    target.write_bytes(data)
    return target


def _cmu(take: str) -> bytes:
    subject = int(take.split("_")[0])
    low, high = next(g for g in CMU_GROUPS if g[0] <= subject <= g[1])
    # The mirror names a subject's folder with at least two digits (`02`, `113`).
    url = f"{CMU_MIRROR}/Sequence-{low:03d}-{high:03d}/{subject:02d}/Data/{take}.zip"
    with zipfile.ZipFile(io.BytesIO(_get(url))) as zipped:
        return zipped.read(f"{take}.bvh")


def _get(url: str, headers: dict[str, str] | None = None) -> bytes:
    import httpx

    response = httpx.get(
        url, headers={"User-Agent": USER_AGENT, **(headers or {})}, timeout=120.0,
        follow_redirects=True,
    )  # fmt: skip
    response.raise_for_status()
    return response.content


class _Remote(io.RawIOBase):
    """A file on a server read as if it were here, a range of bytes at a time: enough for
    Python's zipfile to read one entry of a large zip without fetching the rest."""

    def __init__(self, url: str) -> None:
        import httpx

        self._url = url
        self._at = 0
        head = httpx.head(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
        head.raise_for_status()
        self._size = int(head.headers["content-length"])

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._at

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        self._at = {io.SEEK_SET: offset, io.SEEK_CUR: self._at + offset}.get(
            whence, self._size + offset
        )
        return self._at

    def readinto(self, buffer: Any) -> int:
        wanted = min(len(buffer), self._size - self._at)
        if wanted <= 0:
            return 0
        data = _get(self._url, {"Range": f"bytes={self._at}-{self._at + wanted - 1}"})
        buffer[: len(data)] = data
        self._at += len(data)
        return len(data)
