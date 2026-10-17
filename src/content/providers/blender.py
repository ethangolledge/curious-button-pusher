"""Blender, run as a separate program on a job file, as ffmpeg is: the worker builds and
renders inside it (`content/blender/worker.py`), and this side only writes jobs and reads
reports. Blender 5.2 LTS is the version the blocks are written for; point `BLENDER` at it if
it is not on the path. `FakeBlender` stands in for tests."""

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from content.blender.job import Job, Join, Report

SOURCE = Path(__file__).parents[2]
WORKER = SOURCE / "content" / "blender" / "worker.py"
INGEST = SOURCE / "content" / "blender" / "ingest.py"
PERSON = SOURCE / "content" / "blender" / "person.py"
RETARGET = SOURCE / "content" / "blender" / "retarget.py"
FIT = SOURCE / "content" / "blender" / "fit.py"
VERSION = "5.2"
# Where Blender keeps its user extensions (the MPFB extension that makes people, and its
# CC0 clothes and hair), on macOS and on Linux.
CONFIG = (
    Path("~/Library/Application Support/Blender")
    if sys.platform == "darwin"
    else Path("~/.config/blender")
)
EXTENSIONS = CONFIG.expanduser() / VERSION / "extensions"
PEOPLE = EXTENSIONS / "user_default" / "mpfb"
PEOPLE_ASSETS = EXTENSIONS / ".user" / "user_default" / "mpfb" / "data"


class BlenderError(RuntimeError):
    pass


class Renderer(Protocol):
    def render(self, job: Job | Join, out: Path, *, force: bool = False) -> Report: ...


# What making people needs, all CC0 (MakeHuman's asset packs): the base body's eyes,
# teeth and skins, suits, shoes and hair; casual and work clothes come with the base.
PEOPLE_PACKS = ("makehuman_system_assets", "suits01", "shoes01", "hair01")
PACKS_URL = "https://files.makehumancommunity.org/asset_packs/{name}/{name}_cc0.zip"
EXTENSIONS_URL = "https://extensions.blender.org/api/v1/extensions/"


def install_people(blender: "LocalBlender", say: Callable[[str], None]) -> None:
    """Install the MPFB extension into Blender and its CC0 clothes and hair (about 650 MB,
    once): what `people_ready` needs."""
    import httpx

    listing = httpx.get(EXTENSIONS_URL, params={"format": "json"}, timeout=60).json()
    mpfb = next(e for e in listing["data"] if e["id"] == "mpfb")
    with tempfile.TemporaryDirectory() as work:
        archive = Path(work) / "mpfb.zip"
        say(f"Fetching the MPFB extension {mpfb['version']}…")
        archive.write_bytes(
            httpx.get(mpfb["archive_url"], timeout=600, follow_redirects=True).content
        )
        subprocess.run(
            [str(blender.program), "-b", "--command", "extension", "install-file",
             "-r", "user_default", "--enable", str(archive)],
            check=True, capture_output=True,
        )  # fmt: skip
        PEOPLE_ASSETS.mkdir(parents=True, exist_ok=True)
        for name in PEOPLE_PACKS:
            say(f"Fetching {name} (CC0)…")
            pack = Path(work) / f"{name}.zip"
            with httpx.stream("GET", PACKS_URL.format(name=name), timeout=1800,
                              follow_redirects=True) as response:  # fmt: skip
                response.raise_for_status()
                with pack.open("wb") as out:
                    for chunk in response.iter_bytes():
                        out.write(chunk)
            zipfile.ZipFile(pack).extractall(PEOPLE_ASSETS)
            pack.unlink()


def people_ready() -> bool:
    """Whether people can be made: the MPFB extension and its clothes and hair are here
    (`content staging people` installs them)."""
    return (PEOPLE / "__init__.py").is_file() and (PEOPLE_ASSETS / "clothes").is_dir()


def blender_path() -> Path | None:
    """Blender, from `BLENDER` or the path."""
    named = os.environ.get("BLENDER")
    if named:
        return Path(named).expanduser()
    found = shutil.which("blender")
    return Path(found) if found else None


class LocalBlender:
    """Blender on this computer. Fine for stills and checks; finals want a real GPU."""

    def __init__(self, program: Path | None = None, *, seconds: float = 3600) -> None:
        found = program or blender_path()
        if found is None or not found.exists():
            raise BlenderError(
                f"Blender {VERSION} not found: install it (docs/staging.md) and put it on the "
                "path, or set BLENDER=/path/to/blender"
            )
        self.program = found
        self.seconds = seconds

    def render(self, job: Job | Join, out: Path, *, force: bool = False) -> Report:
        out.mkdir(parents=True, exist_ok=True)
        job_file = out / "job.json"
        job_file.write_text(job.dumps(), encoding="utf-8")
        self._run(WORKER, str(job_file), str(out), *(["--force"] if force else []))
        return _report(out / "report.json")

    def ingest(
        self,
        source: Path,
        target: Path,
        *,
        height: float | None,
        max_faces: int,
        turn: float = 0.0,
        up: str = "Y",
    ) -> dict[str, Any]:
        """Bring a downloaded model into the library's form (`blender/ingest.py`); returns
        its size, face count and named parts (a set's marks and paths)."""
        target.parent.mkdir(parents=True, exist_ok=True)
        facts = target.with_suffix(".ingest.json")
        self._run(
            INGEST,
            str(source),
            str(target),
            str(facts),
            str(height or 0),
            str(max_faces),
            str(turn),
            up,
        )
        result: dict[str, Any] = json.loads(facts.read_text(encoding="utf-8"))
        facts.unlink()
        return result

    def person(self, description: dict[str, Any], target: Path) -> dict[str, Any]:
        """Make a person to a description (`blender/person.py`); returns their size."""
        target.parent.mkdir(parents=True, exist_ok=True)
        described = target.with_suffix(".person.json")
        facts = target.with_suffix(".facts.json")
        described.write_text(json.dumps(description), encoding="utf-8")
        self._run(PERSON, str(described), str(target), str(facts))
        result: dict[str, Any] = json.loads(facts.read_text(encoding="utf-8"))
        described.unlink()
        facts.unlink()
        return result

    def retarget(self, request: dict[str, Any], target: Path) -> dict[str, Any]:
        """A stretch of a motion capture recording retargeted onto the shared skeleton
        (`blender/retarget.py`), saved as an action; returns its length and pace."""
        target.parent.mkdir(parents=True, exist_ok=True)
        asked = target.with_suffix(".request.json")
        facts = target.with_suffix(".facts.json")
        asked.write_text(json.dumps(request), encoding="utf-8")
        self._run(RETARGET, str(asked), str(target), str(facts))
        result: dict[str, Any] = json.loads(facts.read_text(encoding="utf-8"))
        asked.unlink()
        facts.unlink()
        return result

    def fit(self, request: dict[str, Any], out: Path) -> dict[str, Any]:
        """A person's body fitted to their design's outlines (`blender/fit.py`); returns the
        dials found and how well they fit, its pictures in `out`."""
        out.mkdir(parents=True, exist_ok=True)
        asked, result = out / "request.json", out / "result.json"
        asked.write_text(json.dumps(request), encoding="utf-8")
        self._run(FIT, str(asked), str(out), str(result))
        found: dict[str, Any] = json.loads(result.read_text(encoding="utf-8"))
        return found

    def _run(self, script: Path, *arguments: str) -> None:
        command = [
            str(self.program), "-b", "--factory-startup", "--python-use-system-env",
            "--python-exit-code", "1", "-P", str(script), "--", *arguments,
        ]  # fmt: skip
        # Blender's own Python, finding this package (and nothing else of this computer's).
        environment = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
        environment["PYTHONPATH"] = str(SOURCE)
        try:
            done = subprocess.run(
                command, capture_output=True, text=True, timeout=self.seconds, env=environment
            )
        except subprocess.TimeoutExpired as exc:
            raise BlenderError(f"Blender took longer than {self.seconds:.0f} s") from exc
        if done.returncode not in (0, 2):  # 2: the shot was checked and not rendered
            tail = "\n".join((done.stdout + done.stderr).strip().splitlines()[-12:])
            raise BlenderError(f"Blender failed ({done.returncode}):\n{tail}")


def _report(path: Path) -> Report:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Report(**data)


class FakeBlender:
    """Offline stand-in: every frame a flat colour at the given brightness and saturation
    (give it the theme's neutral tone, as the fake media provider has), each shot a little
    different; the report is written as the worker writes it. Records each job. Shots named
    in `refuse` fail their checks, as a shot with two things passing into each other does."""

    def __init__(
        self,
        *,
        brightness: float = 128.0,
        saturation: float = 0.0,
        refuse: frozenset[str] = frozenset(),
    ) -> None:
        self.jobs: list[Job | Join] = []
        self.brightness = brightness
        self.saturation = saturation
        self.refuse = refuse

    def render(self, job: Job | Join, out: Path, *, force: bool = False) -> Report:
        self.jobs.append(job)
        if isinstance(job, Job) and job.shot_id in self.refuse:
            issue = "frame 1: desk and safe pass into each other"
            report = Report(job.shot_id, [], [issue], 0.0, 0.0)
            out.mkdir(parents=True, exist_ok=True)
            (out / "report.json").write_text(report.dumps(), encoding="utf-8")
            return report
        wanted = job.frames or tuple(range(1, job.frame_count + 1))
        folder = out / "frames"
        folder.mkdir(parents=True, exist_ok=True)
        name = job.shot_id if isinstance(job, Job) else job.join_id
        luma = round(self.brightness) + sum(name.encode()) % 3
        tint = round(128 - self.saturation / math.sqrt(2))
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-nostdin", "-y", "-f", "lavfi", "-i",
                f"color=c=black:s={job.width}x{job.height},format=yuv444p,"
                f"lutyuv=y={luma}:u={tint}:v={tint}",
                "-frames:v", str(max(wanted)), str(folder / "%04d.png"),
            ],
            check=True,
            capture_output=True,
        )  # fmt: skip
        for path in folder.glob("*.png"):
            if int(path.stem) not in wanted:
                path.unlink()
        report = Report(name, [str(folder / f"{f:04d}.png") for f in wanted], [], 0.0, 0.0)
        (out / "report.json").write_text(report.dumps(), encoding="utf-8")
        return report
