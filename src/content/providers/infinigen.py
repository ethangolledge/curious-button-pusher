"""Infinigen (Princeton's procedural generator, BSD licence) as a source of models: about a
hundred kinds of everyday object (sofas, beds, office chairs, cabinets, microwaves,
televisions, lamps, crockery, plants), each in endless variations, made on this computer.
What it makes is the channel's own: free to use, nothing to credit.

It needs Blender 4.2 and Python 3.11, so it lives in its own environment beside this one
(`.cache/infinigen`, installed by `content staging infinigen`); the generator runs there
(`blender/generate.py`) and hands back a glTF file."""

import os
import re
import subprocess
import tempfile
from pathlib import Path

from content.providers.assets import Candidate

PROJECT = Path(__file__).parents[3]
HOME = PROJECT / ".cache" / "infinigen"
PYTHON = HOME / ".venv" / "bin" / "python"
MAKE = PROJECT / "src" / "content" / "blender" / "generate.py"
REPOSITORY = "https://github.com/princeton-vl/infinigen.git"
# Infinigen's own lists of what its generators make, indoors and out.
LISTS = (
    "tests/infinigen/assets/list_indoor_meshes.txt",
    "tests/infinigen/assets/list_nature_meshes.txt",
)
# Infinigen's things face +X; the library's face −Y.
TURN = -90.0
# Variations offered of each generator a search finds.
VARIATIONS = 2


class Infinigen:
    name = "infinigen"
    key = ""
    key_required = False

    @classmethod
    def ready(cls) -> bool:
        return PYTHON.is_file()

    def search(self, words: str, limit: int) -> list[Candidate]:
        asked = _words(words)
        scored = []
        for generator in _generators():
            named = _words(_plain_name(generator))
            shared = len(asked & named)
            if shared:
                scored.append((shared / len(asked | named), generator))
        scored.sort(key=lambda pair: -pair[0])
        return [
            Candidate(
                source=self.name,
                title=f"{_plain_name(generator)} (variation {seed})",
                page=f"https://infinigen.org/#{_plain_name(generator)}-{seed}",
                file_url=f"{generator}#{seed}",
                file_type="glb",
                licence="own",
                author="made with Infinigen (Princeton Vision & Learning Lab)",
                turn=TURN,
            )
            for _, generator in scored[: max(1, limit // VARIATIONS)]
            for seed in range(1, VARIATIONS + 1)
        ][:limit]

    def download(self, candidate: Candidate) -> bytes:
        generator, seed = candidate.file_url.split("#")
        with tempfile.TemporaryDirectory() as work:
            made = Path(work) / "made.glb"
            done = subprocess.run(
                [str(PYTHON), str(MAKE), generator, seed, str(made)],
                capture_output=True, timeout=900, cwd=HOME,
            )  # fmt: skip
            # Blender as a module can fail as it shuts down after the file is written: the
            # file is what counts.
            if not made.is_file():
                tail = done.stderr.decode(errors="ignore").strip().splitlines()[-3:]
                raise RuntimeError(f"Infinigen could not make {generator}: {' '.join(tail)}")
            return made.read_bytes()


def install() -> None:
    """Infinigen in its own Python 3.11 environment (a few GB, once), with uv."""
    if not (HOME / ".git").is_dir():
        subprocess.run(["git", "clone", "--depth", "1", REPOSITORY, str(HOME)], check=True)
    subprocess.run(["uv", "venv", "-p", "3.11", str(HOME / ".venv")], check=True)
    subprocess.run(
        ["uv", "pip", "install", "--python", str(PYTHON), "-e", f"{HOME}[terrain,vis]",
         "gin-config", "scikit-learn<1.4", "psutil"],
        check=True, env={**os.environ, "INFINIGEN_MINIMAL_INSTALL": "True"},
    )  # fmt: skip


def _generators() -> list[str]:
    return [
        line.strip()
        for listed in LISTS
        if (HOME / listed).is_file()
        for line in (HOME / listed).read_text(encoding="utf-8").splitlines()
        if line.strip().endswith("Factory")
    ]


def _plain_name(generator: str) -> str:
    """`infinigen.assets.objects.seating.chairs.OfficeChairFactory` → "office chair"."""
    camel = generator.rsplit(".", 1)[-1].removesuffix("Factory")
    return re.sub(r"(?<!^)(?=[A-Z])", " ", camel).lower()


def _words(text: str) -> set[str]:
    return {word.rstrip("s") for word in re.findall(r"[a-z]+", text.lower()) if len(word) > 2}
