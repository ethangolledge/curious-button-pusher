"""`content staging`: 3D shots built in Blender. See what a shot can be made of, find and add
models, check a shot and preview it, and start a new block from its template."""

import argparse
import hashlib
import json
import re
from dataclasses import replace
from pathlib import Path

from content.blender.job import Job
from content.blender.materials import ROLES
from content.blender.registry import ENGINE
from content.config import load_config
from content.production.assemble import contact_sheet
from content.providers import ffmpeg
from content.providers.assets import ALLOWED, SOURCES, AssetSource, Candidate, ready_sources
from content.providers.blender import LocalBlender
from content.schemas.staging import StagePlan
from content.staging import sourcing
from content.staging.backlog import most_wanted
from content.staging.catalogue import Catalogue, check, describe, load_catalogue, with_models
from content.staging.plan import StagingError, job_for, themed
from content.staging.store import Store
from content.staging.templates import TEMPLATES, render
from content.theme import Theme, load_theme

# The starter kit's theme draws a shot when no channel is named; a plan's shot runs this long.
STARTER = Path(__file__).parents[3] / "themes" / "starter"
PREVIEW_SECONDS = 5.0


def _staging(arguments: list[str]) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--config", type=Path, help="A channel's config.json (its own blocks and models)"
    )
    parser = argparse.ArgumentParser(prog="content staging", description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser(
        "catalogue", parents=[common], help="Every block and model, with their settings"
    )
    models = actions.add_parser(
        "models", parents=[common], help="The models, or those matching some words"
    )
    models.add_argument("words", nargs="*")
    find = actions.add_parser(
        "find",
        parents=[common],
        help="Search every free source for a model the library lacks, and draw the best",
    )
    find.add_argument("words")
    find.add_argument("--source", choices=[s.name for s in SOURCES], help="Only this source")
    find.add_argument("--take", type=int, help="Add shortlisted model number N")
    find.add_argument("--as", dest="model_id", help="Its id in the library (with --take)")
    find.add_argument("--about", default="", help="What it is, in a sentence (with --take)")
    _model_options(find)
    add = actions.add_parser(
        "add", parents=[common], help="Add a model file or picture you downloaded yourself"
    )
    add.add_argument("file", type=Path)
    add.add_argument("--as", dest="model_id", required=True)
    add.add_argument("--about", required=True, help="What it is, in a sentence")
    add.add_argument("--licence", required=True, help=f"One of: {', '.join(sorted(ALLOWED))}")
    add.add_argument("--source", required=True, help="Where it came from, e.g. Poly Haven")
    add.add_argument("--page", default="", help="The page it came from")
    add.add_argument("--author", default="", help="Its maker (credited if its licence asks)")
    _model_options(add)
    vary = actions.add_parser(
        "vary",
        parents=[common],
        help="A version of a model, repainted or resized, under its own name (no new file)",
    )
    vary.add_argument("model_id", help="The new version's id")
    vary.add_argument("--from", dest="base", required=True, help="The model it is a version of")
    vary.add_argument("--about", required=True, help="What it is, in a sentence")
    vary.add_argument(
        "--paint",
        default="",
        help=f"part=role, comma separated (part, material or role; roles: {', '.join(ROLES)})",
    )
    vary.add_argument("--names", default="", help="Other words for it, comma separated")
    vary.add_argument("--height", type=float, help="Its height in metres")
    for verb, about in (
        ("keep", "Keep a model that was taken automatically"),
        ("veto", "Turn a model down: it is never used again"),
        ("history", "Where a model came from and every step that made it"),
    ):
        command = actions.add_parser(verb, parents=[common], help=about)
        command.add_argument("model_id")
        if verb == "veto":
            command.add_argument("--why", default="", help="What is wrong with it")
    name = actions.add_parser("name", parents=[common], help="Another word for a library model")
    name.add_argument("model_id")
    name.add_argument("words")
    for verb, about in (
        ("check", "Check a shot without rendering it"),
        ("preview", "Render a shot's stills"),
    ):
        shot = actions.add_parser(verb, parents=[common], help=about)
        shot.add_argument(
            "job", type=Path, help="A shot: a job file, or a staged scene's plan (JSON)"
        )
        if verb == "preview":
            shot.add_argument(
                "--frames", default="", help="Frames to render, e.g. 1,60,120 (default: four)"
            )
            shot.add_argument("--quality", choices=("still", "draft", "final"), default="still")
            shot.add_argument(
                "--scene", action="store_true", help="Also save the scene to open in Blender"
            )
    backlog = actions.add_parser(
        "backlog", parents=[common], help="What scenes could not be staged for, most wanted first"
    )
    backlog.add_argument(
        "--find", action="store_true", help="Search the free sources for every model wanted"
    )
    new = actions.add_parser("new", parents=[common], help="Start a new block from its template")
    new.add_argument("kind", choices=sorted(TEMPLATES))
    new.add_argument("name", help="lower_case_with_underscores")
    new.add_argument("--channel", action="store_true", help="In the channel's own folder (private)")
    args = parser.parse_args(arguments)
    theme = load_config(args.config).theme if args.config else None
    catalogue = load_catalogue(theme.root if theme else None)
    if args.action == "catalogue":
        print(describe(catalogue))
    elif args.action == "models":
        _models(catalogue, " ".join(args.words))
    elif args.action == "name":
        catalogue.library.name(args.model_id, args.words)
        print(f"{args.model_id} is also found as '{args.words}'.")
    elif args.action in ("keep", "veto", "history"):
        if theme is None:
            parser.error("models are a channel's: pass --config themes/<name>/config.json")
        return _review(catalogue, args)
    elif args.action in ("find", "add", "vary"):
        if theme is None:
            parser.error("models are added to a channel: pass --config themes/<name>/config.json")
        try:
            if args.action == "find":
                return _find(catalogue, theme, args)
            if args.action == "add":
                return _add(catalogue, theme, args)
            return _vary(catalogue, args)
        except ValueError as exc:
            print(exc)
            return 1
    elif args.action in ("check", "preview"):
        try:
            job, catalogue = _shot(args.job, theme, catalogue)
        except StagingError as exc:
            print("\n".join(f"✗ {missing}" for missing in exc.missing))
            return 1
        return _check(job, catalogue) if args.action == "check" else _preview(job, catalogue, args)
    elif args.action == "backlog":
        if theme is None:
            parser.error("the backlog is a channel's: pass --config themes/<name>/config.json")
        wanted = most_wanted(theme.root)
        if not wanted:
            print("Nothing yet: every scene the Visual Director wanted to stage could be.")
        for missing, times in wanted:
            print(f"{times:3}× {missing}")
        if args.find:
            for missing, _ in wanted:
                if missing.startswith("model:"):
                    print(f"\n— {missing}")
                    _shortlist(catalogue, theme, missing.removeprefix("model:").strip(), None)
    elif args.action == "new":
        return _new(args.kind, args.name, theme.root if theme and args.channel else None, parser)
    return 0


def _model_options(command: argparse.ArgumentParser) -> None:
    """What every way of adding a model asks: other words for it, what it can do, and how to
    correct a file whose size or facing is off."""
    command.add_argument("--names", default="", help="Other words for it, comma separated")
    command.add_argument(
        "--can", default="", help="What it can do, comma separated: vehicle, humanoid, seat, light…"
    )
    command.add_argument(
        "--height", type=float, help="Its real height in metres (a picture: its width)"
    )
    command.add_argument(
        "--turn", type=float, default=0.0, help="Degrees to turn it so its front faces the camera"
    )
    command.add_argument(
        "--alongside", action="store_true", help="Add it although a similar model exists"
    )


def _listed(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def _review(catalogue: Catalogue, args: argparse.Namespace) -> int:
    library = catalogue.library
    if args.action == "keep":
        library.keep(args.model_id)
        print(f"✓ {args.model_id} kept.")
    elif args.action == "veto":
        library.veto(args.model_id, args.why)
        print(f"✓ {args.model_id} turned down: it will not be used or offered again.")
    else:
        assert library.folder is not None
        store = Store(library.folder)
        for at, step, detail in store.lineage(args.model_id):
            print(f"{at}  {step:9} {json.dumps(detail)}")
        used = store.usage(args.model_id)
        print(f"Used in: {', '.join(used) if used else 'no video yet'}")
    return 0


def _models(catalogue: Catalogue, words: str) -> None:
    library = catalogue.library
    found = (
        [f.model for f in library.search(words)]
        if words
        else sorted(library.models.values(), key=lambda m: m.model_id)
    )
    if not found:
        print(
            f"Nothing in the library for '{words}'. "
            f'Search the free sources: content staging find "{words}"'
        )
    for model in found:
        w, d, h = model.size
        origin = model.source + (f", {model.licence}" if model.licence else "")
        if model.status != "kept":
            origin += f", {model.status}"
        print(f"{model.model_id:20} {w:.2f}×{d:.2f}×{h:.2f} m  ({origin})  {model.describe}")


def _shot(path: Path, theme: Theme | None, catalogue: Catalogue) -> tuple[Job, Catalogue]:
    """A shot from its file: a job, or a staged scene's plan (as the Visual Director writes
    it), composed. A channel's shots are drawn its way: its look, and its camera moves."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if "shot_id" in data:
        job = Job.loads(json.dumps(data))
        return (themed(job, theme) if theme else job), catalogue
    if theme is None:  # drawn the starter kit's way, with its own blocks
        theme, catalogue = load_theme(STARTER), load_catalogue(STARTER)
    plan = StagePlan.model_validate(data)
    job = job_for(path.stem, plan, theme, catalogue, seconds=PREVIEW_SECONDS, quality="still")
    return job, catalogue


def _check(job: Job, catalogue: Catalogue) -> int:
    issues = check(job, catalogue)
    for issue in issues:
        print(f"✗ {issue}")
    if not issues:
        print(f"✓ {job.shot_id}: every block, model and name is in place.")
    return 1 if issues else 0


def _preview(job: Job, catalogue: Catalogue, args: argparse.Namespace) -> int:
    if _check(job, catalogue):
        return 1
    frames = tuple(int(f) for f in args.frames.split(",") if f) or _four(job.frame_count)
    job = replace(
        with_models(job, catalogue), frames=frames, quality=args.quality, save_scene=args.scene
    )
    out = (
        Path(".cache/staging")
        / f"{job.shot_id}-{hashlib.sha256(job.dumps().encode()).hexdigest()[:10]}"
    )
    report = LocalBlender().render(job, out)
    for issue in report.issues:
        print(f"✗ {issue}")
    if not report.frames:
        print("Not rendered: fix the problems above (or render anyway from Blender).")
        return 1
    sheet = out / "sheet.png"
    _strip([Path(f) for f in report.frames], sheet)
    print(f"✓ {len(report.frames)} frames in {report.seconds_rendering:.0f} s: {sheet}")
    if report.blend:
        print(f"  The scene, to open in Blender: {report.blend}")
    return 0


def _four(frames: int) -> tuple[int, ...]:
    return tuple(sorted({1, max(1, frames // 3), max(1, 2 * frames // 3), frames}))


def _strip(frames: list[Path], sheet: Path) -> None:
    """Frames side by side, in order."""
    inputs = [arg for frame in frames for arg in ("-i", frame)]
    stack = f"hstack=inputs={len(frames)}" if len(frames) > 1 else "null"
    ffmpeg.run(*inputs, "-filter_complex", f"{stack},scale=1600:-2", sheet)


def _find(catalogue: Catalogue, theme: Theme, args: argparse.Namespace) -> int:
    folder = sourcing.folder_for(args.words)
    if args.take is None:
        known = catalogue.library.search(args.words)
        if known:
            print("Already in the library (a version of one may do: content staging vary):")
            _models(catalogue, args.words)
            print()
        sources = [s for s in ready_sources() if not args.source or s.name == args.source]
        return _shortlist(catalogue, theme, args.words, sources)
    entries = sourcing.shortlisted(folder)
    if not 1 <= args.take <= len(entries) or not args.model_id:
        print(f'--take needs a number from the shortlist (content staging find "{args.words}") '
              "and --as an id.")  # fmt: skip
        return 1
    entry = entries[args.take - 1]
    if not entry.download:
        print(f"Number {args.take} could not be prepared: {entry.problem}")
        return 1
    model = sourcing.add_file(
        catalogue, Path(entry.download), entry.candidate, model_id=args.model_id,
        describe=args.about or entry.candidate.title, names=_listed(args.names),
        height=args.height, turn=args.turn, capabilities=_listed(args.can),
        alongside=args.alongside,
    )  # fmt: skip
    return _added(catalogue, theme, model.model_id)


def _shortlist(
    catalogue: Catalogue, theme: Theme, words: str, sources: list[AssetSource] | None
) -> int:
    entries, failed = sourcing.shortlist(
        words,
        ready_sources() if sources is None else sources,
        sourcing.folder_for(words),
        catalogue,
        theme,
    )
    for problem in failed:
        print(f"  (skipped {problem})")
    missing = [s.name for s in SOURCES if not s.ready()]
    if missing:
        print(f"  (not searched, no key in .env: {', '.join(missing)}; docs/staging.md)")
    if not entries:
        print(f"No free model for '{words}': build it in code (content staging new props …).")
        return 0
    for index, entry in enumerate(entries, 1):
        c = entry.candidate
        made = f", {entry.size[2]:.2f} m tall as made" if entry.model else ""
        state = f"  ✗ {entry.problem}" if entry.problem else ""
        print(
            f"{index}. {c.title} — {c.author} ({c.source}, {c.licence}{made}){state}\n   {c.page}"
        )
    stills = [Path(entry.still) for entry in entries if entry.still]
    if stills:
        sheet = sourcing.folder_for(words) / "sheet.png"
        contact_sheet(stills, sheet, columns=3)
        print(f"\nThe candidates in the channel's look, in order: {sheet}")
    print(f'Take one: content staging find "{words}" --take N --as <id> --about "…"')
    return 0


def _add(catalogue: Catalogue, theme: Theme, args: argparse.Namespace) -> int:
    candidate = Candidate(
        args.source, args.about, args.page, str(args.file), args.file.suffix.lstrip("."),
        args.licence, args.author,
    )  # fmt: skip
    model = sourcing.add_file(
        catalogue, args.file, candidate, model_id=args.model_id, describe=args.about,
        names=_listed(args.names), height=args.height, turn=args.turn,
        capabilities=_listed(args.can), alongside=args.alongside,
    )  # fmt: skip
    return _added(catalogue, theme, model.model_id)


def _vary(catalogue: Catalogue, args: argparse.Namespace) -> int:
    paint = dict(pair.split("=", 1) for pair in _listed(args.paint))
    model = catalogue.library.vary(
        args.model_id, args.base, describe=args.about, names=_listed(args.names),
        paint={k.strip(): v.strip() for k, v in paint.items()}, height=args.height,
    )  # fmt: skip
    w, d, h = model.size
    print(f"✓ {model.model_id}: a version of {args.base} ({w:.2f}×{d:.2f}×{h:.2f} m).")
    return 0


def _added(catalogue: Catalogue, theme: Theme, model_id: str) -> int:
    model = catalogue.library.get(model_id)
    w, d, h = model.size
    print(f"✓ {model_id} added ({w:.2f}×{d:.2f}×{h:.2f} m, {model.licence}).")
    if not model.file.endswith(".glb"):
        print("  A picture: stand it in a shot with the picture actor.")
        return 0
    out = Path(".cache/staging") / f"model-{model_id}"
    frames = sourcing.turntable(catalogue, model_id, theme, out)
    if frames:
        _strip(frames, out / "sheet.png")
        print(f"  Four views of it in the channel's look: {out / 'sheet.png'}")
    return 0


def _new(kind: str, name: str, channel: Path | None, parser: argparse.ArgumentParser) -> int:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        parser.error("names are lower case with underscores, e.g. pour_drink")
    folder = (channel / "blender" if channel else ENGINE) / kind
    target = folder / f"{name}.py"
    if target.exists():
        parser.error(f"{target} already exists")
    folder.mkdir(parents=True, exist_ok=True)
    target.write_text(render(kind, name), encoding="utf-8")
    print(f"Started {target}. Fill in its TODOs, then: pytest -k {name}")
    return 0


COMMANDS = {"staging": _staging}
