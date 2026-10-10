"""A run's folder: everything the person opens, with the working files tucked behind it.

    runs/<slug>/
      review.html      the current review, with Approve / Revise / Stop
      brief.md         the topic and the person's brief
      1-script.md      the fact-checked script, at the Script sign-off
      2-narration.m4a  the narration over the music, at the Narration sign-off
      3-scenes/        a picture per scene, the animatic and the story sheet, at Pictures
      4-final.mp4      the finished video, at the Final cut sign-off
      building-blocks/ what each stage made, readable (.md) and exact (.json): research,
                       plan, script, fact check, storyboard; a later video can start from
                       the research (`--research building-blocks/research.json`)
      decisions.md     every review answered, by whom, in order
      cost.csv         what each session spent, by stage
      calls.csv        every paid call: what it made, on which model, how long, what it cost
      .work/           review files, the saved steps and state to resume from, traces

While a review waits, a small server on this machine serves the folder, so the page's
buttons answer the review directly; the assistant can answer the same review by writing its
response file. The server is the run's own, or, when the run stopped at the review
(`--detach`), a separate `content review <run>` that outlives it. Comments are saved as
they are typed. Standard library only.
"""

import csv
import json
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from content.choices import RunChoices
from content.production.budget import NARRATION_TAKE_USD
from content.review.page import review_page, review_title
from content.review.render import (
    render_fact_check,
    render_plan,
    render_research,
    render_script,
    render_visuals,
)
from content.schemas.package import FinalContentPackage, ReviewHandoff
from content.schemas.review import ReviewItem, ReviewRequest, ReviewResponse
from content.spend import cost_stage


def slug(topic: str) -> str:
    """A readable folder name from the first few words of the topic."""
    words = re.findall(r"[a-z0-9]+", topic.lower())[:6]
    return "-".join(words) or "run"


# Where cost.csv puts each session's spend, in the order money is spent. Writing is every
# text model (research, plan, script, fact check, storyboard, critic); checks are Jev and
# the vision model describing renders.
COST_STAGES = ("writing", "checks", "narration", "pictures", "morphs", "music")
# calls.csv's columns: a call's logged field, then its heading.
CALL_COLUMNS = {
    "operation": "made",
    "model": "model",
    "seconds": "seconds",
    "input_tokens": "input tokens",
    "output_tokens": "output tokens",
    "cost_usd": "cost usd",
}
# cost.csv's columns after the session number: the logged field, then its heading.
COST_COLUMNS = {
    "finished": "finished",
    "stopped_at": "stopped at",
    "calls": "calls",
    **{stage: f"{stage} usd" for stage in COST_STAGES},
    "priced": "total priced usd",
    "unpriced_calls": "unpriced calls",
    "narration_estimate": "unpriced narration estimate usd",
}


@dataclass(frozen=True)
class RunFolder:
    root: Path

    @property
    def work(self) -> Path:
        return self.root / ".work"

    @property
    def reviews(self) -> Path:
        return self.work / "reviews"

    @property
    def resume_file(self) -> Path:
        """The saved state the next session resumes from."""
        return self.work / "resume.json"

    @property
    def steps(self) -> Path:
        """Every step of the run so far, so it can carry on after its process ends."""
        return self.work / "steps.jsonl"

    @property
    def blocks(self) -> Path:
        """What each stage made, readable and exact: written at every save."""
        return self.root / "building-blocks"

    def write_building_blocks(self, made: ReviewHandoff | FinalContentPackage) -> None:
        """Each stage's output so far as `<block>.md` (to read) and `<block>.json` (exact,
        to start another video from). Paid for once; kept with the run, and with it in the
        bucket."""
        if isinstance(made, ReviewHandoff):
            script, storyboard = made.script_package, made.visual_package
        else:
            script, storyboard = made.approved_script, made.visual_plan
        blocks: dict[str, tuple[Any, Callable[[Any], list[str]]]] = {
            "research": (made.research_pack, render_research),
            "plan": (made.editorial_brief, render_plan),
            "script": (script, render_script),
            "fact-check": (made.fact_check_report, render_fact_check),
            "storyboard": (storyboard, render_visuals),
        }
        self.blocks.mkdir(parents=True, exist_ok=True)
        for name, (block, render) in blocks.items():
            if block is None:
                continue
            (self.blocks / f"{name}.json").write_text(
                block.model_dump_json(indent=2) + "\n", encoding="utf-8"
            )
            (self.blocks / f"{name}.md").write_text(
                "\n".join(render(block)) + "\n", encoding="utf-8"
            )

    @property
    def choices_file(self) -> Path:
        """This video's format, length, scenes and cap, kept for every resume."""
        return self.work / "choices.json"

    def load_choices(self) -> RunChoices:
        if not self.choices_file.is_file():
            return RunChoices()
        return RunChoices.model_validate_json(self.choices_file.read_text(encoding="utf-8"))

    def save_choices(self, choices: RunChoices) -> None:
        self.work.mkdir(parents=True, exist_ok=True)
        self.choices_file.write_text(choices.model_dump_json(indent=2), encoding="utf-8")

    @property
    def page(self) -> Path:
        return self.root / "review.html"

    @property
    def scenes(self) -> Path:
        return self.root / "3-scenes"

    def create(self, topic: str, brief: str | None) -> None:
        self.work.mkdir(parents=True, exist_ok=True)
        lines = [f"# {topic}", "", brief or "No brief given: the topic alone."]
        (self.root / "brief.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def publish(self, request: ReviewRequest) -> None:
        """Copy what this review decides on to its plain name in the folder."""
        files = [Path(path) for path in request.attachments]
        if request.stage == "fact_check":
            (self.root / "1-script.md").write_text(request.snapshot + "\n", encoding="utf-8")
        elif request.stage == "listen" and files:
            shutil.copyfile(files[0], self.root / "2-narration.m4a")
        elif request.stage == "storyboard":
            if self.scenes.is_dir():
                shutil.rmtree(self.scenes)
            self.scenes.mkdir()
            for path in files:
                if path.parent.name == "animatic":
                    shutil.copyfile(path, self.scenes / "animatic.mp4")
                elif path.name == "index.html":
                    shutil.copytree(path.parent, self.scenes / "story-sheet")
            if not request.items:
                # A review saved before items existed: keyframes come in scene order.
                keyframes = [path for path in files if path.parent.name == "keyframe"]
                for number, path in enumerate(keyframes, start=1):
                    shutil.copyfile(path, self.scenes / f"S{number}{path.suffix}")
        elif request.stage == "final_cut" and files:
            shutil.copyfile(files[0], self.root / "4-final.mp4")
        # Each card's picture under its own name: S4's keyframe is always 3-scenes/S4.png.
        for item in request.items:
            source = Path(item.media)
            if item.media and source.is_file():
                self.scenes.mkdir(exist_ok=True)
                shutil.copyfile(source, self.scenes / f"{item.item_id}{source.suffix}")

    def record(self, request: ReviewRequest, response: ReviewResponse) -> None:
        """Add the decision to decisions.md."""
        log = self.root / "decisions.md"
        if not log.is_file():
            log.write_text("# Decisions\n", encoding="utf-8")
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        title = review_title(request)
        lines = ["", f"## {stamp} · {title} · {response.action} ({response.decided_by})"]
        if response.feedback:
            lines += ["", response.feedback]
        with log.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")

    def record_cost(self, summary: dict[str, Any], stage: str) -> None:
        """Add one session's spend to cost.csv: a row per session, its spend split by
        stage, and the run's total at the bottom."""
        sessions = self.work / "costs.jsonl"
        calls = summary.get("calls", [])
        stages = dict.fromkeys(COST_STAGES, 0.0)
        for call in calls:
            stages[cost_stage(call["operation"])] += call["cost_usd"] or 0.0
        unpriced_takes = sum(
            1 for call in calls if call["operation"] == "narration" and call["cost_usd"] is None
        )
        entry = {
            "finished": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "stopped_at": stage,
            "calls": len(calls),
            **{name: round(value, 4) for name, value in stages.items()},
            "priced": round(sum(stages.values()), 4),
            "unpriced_calls": sum(1 for call in calls if call["cost_usd"] is None),
            "narration_estimate": round(unpriced_takes * NARRATION_TAKE_USD, 2),
        }
        with sessions.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
        entries = [json.loads(line) for line in sessions.read_text(encoding="utf-8").splitlines()]
        self._record_calls(len(entries), calls)
        summed = list(COST_COLUMNS)[2:]
        with (self.root / "cost.csv").open("w", encoding="utf-8", newline="") as handle:
            table = csv.writer(handle)
            table.writerow(["session", *COST_COLUMNS.values()])
            for number, logged in enumerate(entries, start=1):
                table.writerow([number, *(logged.get(field, "") for field in COST_COLUMNS)])
            totals = [round(sum(e.get(field) or 0 for e in entries), 2) for field in summed]
            table.writerow(["total", "", "", *totals])

    def _record_calls(self, session: int, calls: list[dict[str, Any]]) -> None:
        """Add one session's calls to calls.csv, a row each, with the stage it counts under."""
        path = self.root / "calls.csv"
        new = not path.is_file()
        with path.open("a", encoding="utf-8", newline="") as handle:
            table = csv.writer(handle)
            if new:
                table.writerow(["session", "stage", *CALL_COLUMNS.values()])
            for call in calls:
                stage = cost_stage(call["operation"])
                table.writerow([session, stage, *(call.get(field, "") for field in CALL_COLUMNS)])

    def write_page(
        self,
        request: ReviewRequest,
        *,
        number: int = 0,
        decided: ReviewResponse | None = None,
    ) -> None:
        changed = self._changed(request) if decided is None else set()
        self.page.write_text(
            review_page(self.root, request, decided, changed, number), encoding="utf-8"
        )

    def _changed(self, request: ReviewRequest) -> set[str]:
        """Items that differ from the last time this sign-off was shown, so a second look
        goes straight to what moved."""
        seen_file = self.work / "seen.json"
        seen = json.loads(seen_file.read_text(encoding="utf-8")) if seen_file.is_file() else {}
        now = {item.item_id: _fingerprint(item) for item in request.items}
        before = seen.get(request.stage)
        seen[request.stage] = now
        self.work.mkdir(parents=True, exist_ok=True)
        seen_file.write_text(json.dumps(seen, indent=2), encoding="utf-8")
        if before is None:
            return set()
        return {item_id for item_id, value in now.items() if before.get(item_id) != value}


def _fingerprint(item: ReviewItem) -> str:
    media = Path(item.media)
    return item.text + ("|" + str(media.stat().st_size) if item.media and media.is_file() else "")


# The review page
