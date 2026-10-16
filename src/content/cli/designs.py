"""`content designs`: the channel's designs, each recurring person, place or object drawn once
and reused (docs/3d-reuse.md#designs). See them, turn one down so it is drawn again, and make 3D
models of them on the cloud GPU: checked for free first, every design in one job, paid only
with `--go`."""

import argparse
import tempfile
from pathlib import Path

from content.cli.cloud import SAM3D_UNSET
from content.config import load_config
from content.staging.designs import Designs, make_models, prepare, waiting_for_models


def _designs(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="content designs", description=__doc__)
    channel = argparse.ArgumentParser(add_help=False)
    channel.add_argument("--config", type=Path, required=True, help="The channel's config.json")
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("list", parents=[channel], help="Every design, and its 3D model")
    veto = actions.add_parser(
        "veto", parents=[channel], help="Turn a design down: drawn again when next needed"
    )
    veto.add_argument("design_id")
    model = actions.add_parser(
        "model",
        parents=[channel],
        help="3D models of the designs without one (a free dry run unless --go)",
    )
    model.add_argument("--go", action="store_true", help="Send them to the GPU (paid)")
    args = parser.parse_args(arguments)
    designs = Designs(load_config(args.config).theme.root)

    if args.action == "list":
        for design in designs.all():
            made = f", 3D: {design.model}" if design.model else ""
            print(f"{design.design_id} ({design.status}, first drawn for {design.made_for}{made})")
        return 0
    if args.action == "veto":
        print(f"{designs.veto(args.design_id).design_id}: turned down; drawn again when needed")
        return 0
    return _model(designs, go=args.go, parser=parser)


def _model(designs: Designs, *, go: bool, parser: argparse.ArgumentParser) -> int:
    from content.providers import sam3d

    waiting = waiting_for_models(designs)
    if not waiting:
        print("No person or object design is waiting for a 3D model.")
        return 0
    with tempfile.TemporaryDirectory() as scratch:
        ready = []
        for design in waiting:
            picture, problems = prepare(designs, design, Path(scratch))
            if problems:
                print(f"{design.design_id}: not sent: {'; '.join(problems)}")
            else:
                print(f"{design.design_id}: ready")
                ready.append((design, picture))
        if not ready or not go:
            if ready:
                print(f"{len(ready)} ready. Add --go to make them: one GPU job per model kind.")
            return 0
        target = sam3d.from_environment()
        if target is None:
            parser.error(SAM3D_UNSET)
        from content.storage import GcsStore

        place, bucket = target
        out = Path(scratch) / "made"
        for line in make_models(designs, ready, out, bucket=GcsStore(bucket), place=place):
            print(line)
    return 0


COMMANDS = {"designs": _designs}
