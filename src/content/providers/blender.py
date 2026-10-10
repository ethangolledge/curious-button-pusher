"""Blender, run as a separate program on a job file, as ffmpeg is: the worker builds and
renders inside it (`content/blender/worker.py`), and this side only writes jobs and reads
reports. Blender 5.2 LTS is the version the blocks are written for; point `BLENDER` at it if
it is not on the path. `FakeBlender` stands in for tests."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Protocol

from content.blender.job import Job, Report

WORKER = Path(__file__).parents[1] / "blender" / "worker.py"
INGEST = Path(__file__).parents[1] / "blender" / "ingest.py"
VERSION = "5.2"


class BlenderError(RuntimeError):
    pass


class Renderer(Protocol):
    def render(self, job: Job, out: Path, *, force: bool = False) -> Report: ...


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

    def render(self, job: Job, out: Path, *, force: bool = False) -> Report:
        out.mkdir(parents=True, exist_ok=True)
        job_file = out / "job.json"
        job_file.write_text(job.dumps(), encoding="utf-8")
        self._run(WORKER, str(job_file), str(out), *(["--force"] if force else []))
        return _report(out / "report.json")

    def ingest(
        self, source: Path, target: Path, *, height: float | None, max_faces: int
    ) -> dict[str, float]:
        """Bring a downloaded model into the library's form (`blender/ingest.py`); returns
        its size and face count."""
        target.parent.mkdir(parents=True, exist_ok=True)
        facts = target.with_suffix(".ingest.json")
        self._run(INGEST, str(source), str(target), str(facts), str(height or 0), str(max_faces))
        result: dict[str, float] = json.loads(facts.read_text(encoding="utf-8"))
        facts.unlink()
        return result

    def _run(self, script: Path, *arguments: str) -> None:
        command = [
            str(self.program), "-b", "--factory-startup", "--python-exit-code", "1",
            "-P", str(script), "--", *arguments,
        ]  # fmt: skip
        try:
            done = subprocess.run(command, capture_output=True, text=True, timeout=self.seconds)
        except subprocess.TimeoutExpired as exc:
            raise BlenderError(f"Blender took longer than {self.seconds:.0f} s") from exc
        if done.returncode not in (0, 2):  # 2: the shot was checked and not rendered
            tail = "\n".join((done.stdout + done.stderr).strip().splitlines()[-12:])
            raise BlenderError(f"Blender failed ({done.returncode}):\n{tail}")


def _report(path: Path) -> Report:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Report(**data)


class FakeBlender:
    """Renders nothing: records each job and reports the frames it would have written."""

    def __init__(self) -> None:
        self.jobs: list[Job] = []

    def render(self, job: Job, out: Path, *, force: bool = False) -> Report:
        self.jobs.append(job)
        frames = job.frames or tuple(range(1, job.frame_count + 1))
        return Report(
            job.shot_id, [str(out / "frames" / f"{f:04d}.png") for f in frames], [], 0.0, 0.0
        )
