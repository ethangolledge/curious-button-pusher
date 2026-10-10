"""What the toolkit lacked: one line for each scene the Visual Director could not stage, so the
block or model most often wanted is the next one built (`content staging backlog`). Kept in the
channel's folder, `blender/backlog.jsonl`, private like the rest of it."""

import json
from collections import Counter
from pathlib import Path

BACKLOG = Path("blender") / "backlog.jsonl"


def record_gap(theme_root: Path, video: str, scene_id: str, missing: str) -> None:
    """Note a gap once per video and scene."""
    path = theme_root / BACKLOG
    entry = {"video": video, "scene": scene_id, "missing": missing.strip()}
    if entry in gaps(theme_root):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry) + "\n")


def gaps(theme_root: Path) -> list[dict[str, str]]:
    path = theme_root / BACKLOG
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def most_wanted(theme_root: Path) -> list[tuple[str, int]]:
    """What was missing, most often first."""
    return Counter(gap["missing"].lower() for gap in gaps(theme_root)).most_common()
