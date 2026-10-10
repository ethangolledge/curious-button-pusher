"""`content staging`: 3D shots built in Blender. See what a shot can be made of, find and add
models, check a shot and preview it, and start a new block from its template."""

import argparse
import hashlib
import io
import re
import tempfile
import zipfile
from dataclasses import replace
from pathlib import Path

from content.blender.job import ActorCall, BlockCall, Job
from content.blender.registry import ENGINE
from content.config import load_config
from content.production import ffmpeg
from content.providers.assets import FREE, AssetSource, Candidate, Smithsonian
from content.providers.blender import LocalBlender
from content.staging.backlog import most_wanted
from content.staging.catalogue import Catalogue, check, describe, load_catalogue, with_models
from content.staging.library import Model
from content.staging.plan import themed
from content.staging.templates import TEMPLATES, render

MAX_FACES = 150_000
SOURCES: dict[str, type[AssetSource]] = {"smithsonian": Smithsonian}


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
        "find", parents=[common], help="Search free sources for a model the library lacks"
    )
    find.add_argument("words")
    find.add_argument("--source", choices=sorted(SOURCES), default="smithsonian")
    find.add_argument("--take", type=int, help="Download, prepare and add result number N")
    find.add_argument("--as", dest="model_id", help="Its id in the library (with --take)")
    find.add_argument("--names", default="", help="Other words for it, comma separated")
    find.add_argument(
        "--height", type=float, help="Its real height in metres, if the file's scale is off"
    )
    find.add_argument(
        "--alongside", action="store_true", help="Add it although a similar model exists"
    )
    find.add_argument(
        "--turn", type=float, default=0.0, help="Degrees to turn it so its front faces the camera"
    )
    add = actions.add_parser(
        "add", parents=[common], help="Add a model file you downloaded yourself"
    )
    add.add_argument("file", type=Path)
    add.add_argument("--as", dest="model_id", required=True)
    add.add_argument("--names", default="", help="Other words for it, comma separated")
    add.add_argument("--about", required=True, help="What it is, in a sentence")
    add.add_argument("--licence", required=True, help=f"One of: {', '.join(sorted(FREE))}")
    add.add_argument("--source", required=True, help="Where it came from, e.g. Poly Haven")
    add.add_argument("--page", default="", help="The page it came from")
    add.add_argument("--author", default="")
    add.add_argument(
        "--can", default="", help="What it can do, comma separated: vehicle, humanoid, seat, light…"
    )
    add.add_argument(
        "--height", type=float, help="Its real height in metres, if the file's scale is off"
    )
    add.add_argument(
        "--alongside", action="store_true", help="Add it although a similar model exists"
    )
    add.add_argument(
        "--turn", type=float, default=0.0, help="Degrees to turn it so its front faces the camera"
    )
    name = actions.add_parser("name", parents=[common], help="Another word for a library model")
    name.add_argument("model_id")
    name.add_argument("words")
    for verb, about in (
        ("check", "Check a shot without rendering it"),
        ("preview", "Render a shot's stills"),
    ):
        shot = actions.add_parser(verb, parents=[common], help=about)
        shot.add_argument("job", type=Path, help="A shot as a job file (JSON)")
        if verb == "preview":
            shot.add_argument(
                "--frames", default="", help="Frames to render, e.g. 1,60,120 (default: four)"
            )
            shot.add_argument("--quality", choices=("still", "draft", "final"), default="still")
            shot.add_argument(
                "--scene", action="store_true", help="Also save the scene to open in Blender"
            )
    actions.add_parser(
        "backlog", parents=[common], help="What scenes could not be staged for, most wanted first"
    )
    new = actions.add_parser("new", parents=[common], help="Start a new block from its template")
    new.add_argument("kind", choices=sorted(TEMPLATES))
    new.add_argument("name", help="lower_case_with_underscores")
    new.add_argument("--channel", action="store_true", help="In the channel's own folder (private)")
    args = parser.parse_args(arguments)
    theme = load_config(args.config).theme if args.config else None
    theme_root = theme.root if theme else None
    catalogue = load_catalogue(theme_root)
    if args.action == "catalogue":
        print(describe(catalogue))
    elif args.action == "models":
        _models(catalogue, " ".join(args.words))
    elif args.action == "name":
        catalogue.library.name(args.model_id, args.words)
        print(f"{args.model_id} is also found as '{args.words}'.")
    elif args.action in ("find", "add"):
        if theme_root is None:
            parser.error("models are added to a channel: pass --config themes/<name>/config.json")
        return _find(catalogue, args) if args.action == "find" else _add(catalogue, args)
    elif args.action == "check":
        job = Job.read(args.job)
        return _check(themed(job, theme) if theme else job, catalogue)
    elif args.action == "preview":
        job = Job.read(args.job)
        # A channel's shots are drawn its way: its look, and its camera moves.
        return _preview(themed(job, theme) if theme else job, catalogue, args)
    elif args.action == "backlog":
        if theme_root is None:
            parser.error("the backlog is a channel's: pass --config themes/<name>/config.json")
        wanted = most_wanted(theme_root)
        if not wanted:
            print("Nothing yet: every scene the Visual Director wanted to stage could be.")
        for missing, times in wanted:
            print(f"{times:3}× {missing}")
    elif args.action == "new":
        return _new(args.kind, args.name, theme_root if args.channel else None, parser)
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
            f'Search free sources: content staging find "{words}"'
        )
    for model in found:
        w, d, h = model.size
        origin = model.source + (f", {model.licence}" if model.licence else "")
        print(f"{model.model_id:20} {w:.2f}×{d:.2f}×{h:.2f} m  ({origin})  {model.describe}")


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
    _contact_sheet([Path(f) for f in report.frames], sheet)
    print(f"✓ {len(report.frames)} frames in {report.seconds_rendering:.0f} s: {sheet}")
    if report.blend:
        print(f"  The scene, to open in Blender: {report.blend}")
    return 0


def _four(frames: int) -> tuple[int, ...]:
    return tuple(sorted({1, max(1, frames // 3), max(1, 2 * frames // 3), frames}))


def _contact_sheet(frames: list[Path], sheet: Path) -> None:
    inputs = [arg for frame in frames for arg in ("-i", frame)]
    stack = f"hstack=inputs={len(frames)}" if len(frames) > 1 else "null"
    ffmpeg.run(*inputs, "-filter_complex", f"{stack},scale=1600:-2", sheet)


def _find(catalogue: Catalogue, args: argparse.Namespace) -> int:
    known = catalogue.library.search(args.words)
    if known and args.take is None:
        print("Already in the library:")
        _models(catalogue, args.words)
        print()
    source = SOURCES[args.source]()
    found = source.search(args.words, 8)
    if args.take is None:
        if not found:
            print(f"{source.name} has no free model for '{args.words}'.")
        for index, candidate in enumerate(found, 1):
            print(
                f"{index}. {candidate.title} ({candidate.licence}, {candidate.file_type})\n"
                f"   {candidate.page}"
            )
        if found:
            print('\nTake one: add --take N --as <id> (and --names "other, words").')
        return 0
    if not args.model_id or not 1 <= args.take <= len(found):
        print("--take needs a result number from the list, and --as an id.")
        return 1
    candidate = found[args.take - 1]
    with tempfile.TemporaryDirectory() as folder:
        downloaded = _unpack(source.download(candidate.file_url), Path(folder), candidate)
        return _ingest(catalogue, args, downloaded, candidate.title, candidate)


def _add(catalogue: Catalogue, args: argparse.Namespace) -> int:
    if args.licence not in FREE:
        print(
            f"Only free licences enter the library ({', '.join(sorted(FREE))}): "
            f"'{args.licence}' needs credit or forbids commercial use."
        )
        return 1
    candidate = Candidate(
        args.source,
        args.about,
        args.page,
        str(args.file),
        args.file.suffix.lstrip("."),
        args.licence,
        args.author,
    )
    return _ingest(catalogue, args, args.file, args.about, candidate)


def _ingest(
    catalogue: Catalogue, args: argparse.Namespace, file: Path, about: str, candidate: Candidate
) -> int:
    library = catalogue.library
    assert library.folder is not None
    model_id = re.sub(r"[^a-z0-9_]+", "_", args.model_id.lower()).strip("_")
    target = library.folder / f"{model_id}.glb"
    facts = LocalBlender().ingest(
        file, target, height=args.height, max_faces=MAX_FACES, turn=args.turn
    )
    model = Model(
        model_id=model_id,
        names=tuple(n.strip() for n in args.names.split(",") if n.strip()),
        describe=about,
        size=(facts["width"], facts["depth"], facts["height"]),
        source=candidate.source,
        licence=candidate.licence,
        page=candidate.page,
        author=candidate.author,
        file=target.name,
        parts=tuple(facts.get("parts", ())),
        motions=tuple(facts.get("motions", ())),
        capabilities=tuple(
            sorted(c.strip() for c in getattr(args, "can", "").split(",") if c.strip())
        ),
    )
    try:
        library.add(model, alongside=args.alongside)
    except ValueError as exc:
        target.unlink(missing_ok=True)
        print(exc)
        return 1
    print(
        f"✓ {model_id} added ({facts['width']:.2f}×{facts['depth']:.2f}×"
        f"{facts['height']:.2f} m, {int(facts['faces'])} faces)."
    )
    print(f"  Four views of it in the studio: {_turntable(catalogue, model_id)}")
    return 0


def _turntable(catalogue: Catalogue, model_id: str) -> Path:
    """Four views of a model in the studio, to judge it by."""
    job = Job(
        shot_id=f"model-{model_id}", seconds=4, width=540, height=540, quality="still",
        layout=BlockCall("studio"), look=BlockCall("plain"),
        actors=(ActorCall("model", "prop", model_id, {"at": "plinth_top"}),),
        lights=(BlockCall("studio", {"subject": "model"}),),
        camera=BlockCall("orbit", {
            "subject": "model", "degrees": "270", "start": "0", "framing": "close",
            "elevation": "20",
        }),
        frames=(1, 40, 80, 120),
    )  # fmt: skip
    out = Path(".cache/staging") / job.shot_id
    report = LocalBlender().render(with_models(job, catalogue), out)
    sheet = out / "sheet.png"
    _contact_sheet([Path(f) for f in report.frames], sheet)
    return sheet


def _unpack(data: bytes, folder: Path, candidate: Candidate) -> Path:
    """The model file in a download: the file itself, or the model inside a zip."""
    if data[:2] == b"PK":
        zipfile.ZipFile(io.BytesIO(data)).extractall(folder)
        for suffix in (".glb", ".gltf", ".obj", ".fbx"):
            found = sorted(folder.rglob(f"*{suffix}"))
            if found:
                return found[0]
        raise ValueError(f"no model file inside the download from {candidate.page}")
    path = folder / f"model.{candidate.file_type or 'glb'}"
    path.write_bytes(data)
    return path


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
