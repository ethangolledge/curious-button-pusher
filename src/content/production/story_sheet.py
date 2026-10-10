"""The story sheet: the whole piece as a story with its pictures, for a person to read
before any video is paid for.

One folder holds `index.html` and copies of every image and clip it shows, so it opens
anywhere and can be shared. Standard library only.
"""

import html
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path

from content.schemas.media import Budget, RenderedAsset, SceneTiming, Timeline
from content.schemas.plan import EditorialBrief
from content.schemas.references import ReferenceSet
from content.schemas.script import ScriptPackage
from content.schemas.story import Feeling
from content.schemas.visuals import VisualPackage

# How the emotional line colours each reaction on the sheet (not in the video).
REACTION_COLOURS = {
    "lean_in": "#c9a45a",
    "brace": "#8a2a36",
    "recoil": "#5f7482",
    "settle": "#b8b1a2",
}

# How the music line colours each section of the bed.
SCORE_COLOURS = {
    "intro": "#26262d",
    "build": "#3a3140",
    "peak": "#5e1a22",
    "outro": "#2f3a3c",
}

# The sheet's style, inlined so the sheet is one self-contained file.
STYLE = Path(__file__).with_name("story_sheet.css").read_text(encoding="utf-8")


def budget_line(budget: Budget) -> str:
    return (
        f"Projected cost ${budget.projected:.2f} of ${budget.cap:.2f}: "
        f"${budget.spent:.2f} spent, ${budget.keyframes:.2f} for keyframes, "
        f"${budget.transitions:.2f} for {budget.morphs} AI morphs between them."
    )


def write_story_sheet(
    folder: Path,
    *,
    brief: EditorialBrief,
    script: ScriptPackage,
    visuals: VisualPackage,
    timeline: Timeline,
    keyframes: Mapping[str, RenderedAsset],
    references: Mapping[str, ReferenceSet],
    animatic: Path | None,
    notes: Sequence[str],
    fields: Mapping[str, Feeling],
    budget: Budget | None,
) -> Path:
    """Write the sheet and its assets into `folder`; return the page."""
    folder.mkdir(parents=True, exist_ok=True)
    units = {unit.unit_id: unit for unit in script.script_units}
    timings = {timing.scene_id: timing for timing in timeline.scenes}
    parts = [
        "<!doctype html><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        f"<title>{_text(script.title)}</title><style>\n{STYLE}</style><main>",
        f"<h1>{_text(script.title)}</h1>",
        f"<p class='question'>{_text(brief.central_question)}</p>",
        f"<p class='meta'>{timeline.total_seconds:.0f} seconds · {len(visuals.scenes)} scenes · "
        f"{_text(brief.promise)}</p>",
        *([f"<p class='meta'>{_text(budget_line(budget))}</p>"] if budget else []),
    ]
    parts.append(_emotional_line(visuals, timings, fields))
    parts.append(_score_line(timeline))
    if animatic is not None:
        parts.append(f"<video controls preload='metadata' src='{_copy(animatic, folder)}'></video>")
    for scene in visuals.scenes:
        timing = timings.get(scene.scene_id)
        when = f" · {timing.start:.1f}–{timing.end:.1f} s" if timing else ""
        keyframe = keyframes.get(scene.scene_id)
        picture = (
            f"<img class='keyframe' src='{_copy(Path(keyframe.path), folder)}' alt=''>"
            if keyframe is not None and keyframe.rendered
            else "<p class='id'>No keyframe</p>"
        )
        lines = "".join(
            f"<p class='line'><span class='id'>{unit_id}</span> "
            f"{_opening_badge(units[unit_id].narrative_function)}"
            f"{_text(units[unit_id].text)}</p>"
            for unit_id in scene.script_unit_ids
            if unit_id in units
        )
        anchor = scene.anchor
        figure = f" · {_text(anchor.figure.name)}" if anchor.figure else ""
        parts.append(
            f"<section class='beat'><div>{picture}</div><div>"
            f"<div class='id'>{scene.scene_id}{when}{_badge(fields.get(scene.scene_id))}</div>"
            f"{lines}"
            f"<p class='shows'>Shows: {_text(anchor.subject)}, in {_text(anchor.setting)}"
            f"{figure}</p>"
            f"{_references(scene.reference_ids, references, folder)}</div></section>"
        )
    if notes:
        items = "".join(f"<li>{_text(note)}</li>" for note in notes)
        parts.append(
            f"<details><summary>What automation flagged</summary><ul>{items}</ul></details>"
        )
    parts.append(
        "<details><summary>How to give notes</summary><p>Start a note with what it is about: "
        "<b>U3:</b> narration, <b>S4:</b> a scene, <b>R2:</b> a reference image (rejects its "
        "picks and searches again). Notes without an ID are sorted for you.</p></details>"
    )
    page = folder / "index.html"
    page.write_text("".join(parts) + "</main>\n", encoding="utf-8")
    return page


def _emotional_line(
    visuals: VisualPackage, timings: Mapping[str, SceneTiming], fields: Mapping[str, Feeling]
) -> str:
    """The piece's emotional arc at a glance: one band per scene, as long as the scene,
    coloured by how its lines land and as tall as how strongly."""
    bands = []
    for scene in visuals.scenes:
        timing = timings.get(scene.scene_id)
        feeling = fields.get(scene.scene_id)
        width = (timing.end - timing.start) if timing else 1.0
        colour = REACTION_COLOURS[feeling.dominant] if feeling else "#3a3a42"
        height = 8 + 8 * (feeling.level if feeling else 0)
        title = f"{scene.scene_id}: {feeling.label()}" if feeling else scene.scene_id
        bands.append(
            f"<span title='{html.escape(title)}' style='flex:{width:.2f};height:{height}px;"
            f"background:{colour}'></span>"
        )
    return f"<div class='arc'>{''.join(bands)}</div>"


def _opening_badge(function: str) -> str:
    """The first eight seconds, marked: they decide whether anyone watches the rest."""
    labels = {"hook": "hook · first 3 s", "orient": "orientation · by 8 s"}
    return f"<span class='opening'>{labels[function]}</span> " if function in labels else ""


def _score_line(timeline: Timeline) -> str:
    """The music under the story: where it builds, peaks and plays out, on the same scale
    as the emotional line above it."""
    if not timeline.score:
        return ""
    bands = "".join(
        f"<span title='{span.label} {span.start:.1f}–{span.end:.1f} s' "
        f"style='flex:{span.end - span.start:.2f};background:{SCORE_COLOURS[span.label]}'>"
        f"{span.label}</span>"
        for span in timeline.score
    )
    return f"<div class='score'>{bands}</div>"


def _badge(feeling: Feeling | None) -> str:
    return f" · <span class='feel {feeling.dominant}'>{feeling.label()}</span>" if feeling else ""


def _references(
    ref_ids: Sequence[str], references: Mapping[str, ReferenceSet], folder: Path
) -> str:
    cards = []
    for ref_id in ref_ids:
        found = references.get(ref_id)
        if found is None:
            continue
        if not found.relevant:
            cards.append(f"<div class='ref'>{ref_id}: dropped as unrelated</div>")
            continue
        for candidate in found.candidates:
            image = candidate.found
            chosen = " chosen" if candidate.path in found.chosen else ""
            rights = " · ".join(part for part in (image.licence, image.author) if part)
            cards.append(
                f"<div class='ref{chosen}'><img src='{_copy(Path(candidate.path), folder)}' "
                f"alt=''><b>{ref_id}</b> {_text(image.title)}<br>{_text(rights)} · "
                f"<a href='{html.escape(image.page_url)}'>source</a></div>"
            )
    return f"<div class='refs'>{''.join(cards)}</div>" if cards else ""


def _copy(source: Path, folder: Path) -> str:
    """Copy an asset beside the page under its cache name, and return its relative path."""
    target = folder / "assets" / source.name
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return f"assets/{source.name}"


def _text(value: str) -> str:
    return html.escape(value, quote=False)
