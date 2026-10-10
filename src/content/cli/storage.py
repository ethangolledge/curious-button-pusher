"""`content storage`: keep finished runs and the channel in the cloud bucket, and bring them
back; and keeping the channel after any command that changes it."""

import argparse
from collections.abc import Callable
from pathlib import Path

from content.config import (
    ContentConfig,
    load_storage,
)
from content.errors import ConfigurationError
from content.storage import (
    GcsStore,
    Manifest,
    StorageError,
    archive_run,
    describe,
    kept,
    kept_versions,
    pull_theme,
    restore_run,
    save_theme,
)
from content.theme import load_theme


def _storage(arguments: list[str]) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", type=Path, help="Runtime configuration JSON")
    parser = argparse.ArgumentParser(
        prog="content storage",
        description="Keep finished runs and the channel's theme in the cloud bucket, and bring "
        "them back. Only signed-off files are kept; work in progress stays in .cache/.",
    )
    actions = parser.add_subparsers(dest="action", required=True)
    archive = actions.add_parser(
        "archive", parents=[common], help="Keep a finished run's signed-off files"
    )
    archive.add_argument("run", type=Path, help="The run folder, e.g. runs/<topic>")
    restore = actions.add_parser("restore", parents=[common], help="Bring a kept run back")
    restore.add_argument("slug", help="The run's folder name")
    restore.add_argument("--into", type=Path, default=Path("runs"), help="Where runs live")
    actions.add_parser(
        "save-theme",
        parents=[common],
        help="Keep the channel's theme: settings, voice, music, taste data",
    )
    pull = actions.add_parser(
        "pull",
        parents=[common],
        help="Bring the channel's theme back (a fresh clone, another machine)",
    )
    pull.add_argument("--version", help="An earlier version instead (see: storage versions)")
    pull.add_argument(
        "--bucket", help="On a fresh clone, with --channel: no configuration needed (it comes back)"
    )
    pull.add_argument("--channel", help="The channel's folder name in themes/")
    actions.add_parser("versions", parents=[common], help="The theme's earlier versions")
    actions.add_parser("list", parents=[common], help="What the bucket keeps")
    args = parser.parse_args(arguments)
    try:
        if args.action == "pull" and args.bucket and args.channel:
            theme_root = Path("themes") / args.channel
            print(f"Restored: {describe(pull_theme(GcsStore(args.bucket), theme_root))}")
            return 0
        storage, theme_root = load_storage(args.config)
        store = GcsStore(storage.bucket)
        if args.action == "archive":
            print(f"Kept: {describe(archive_run(store, args.run))}")
        elif args.action == "restore":
            print(f"Restored: {describe(restore_run(store, args.slug, args.into / args.slug))}")
        elif args.action == "save-theme":
            print(f"Kept: {describe(save_theme(store, load_theme(theme_root).root))}")
        elif args.action == "pull":
            print(f"Restored: {describe(pull_theme(store, theme_root, args.version))}")
        elif args.action == "versions":
            print("\n".join(kept_versions(store, theme_root.name)) or "No earlier versions yet.")
        else:
            print("\n".join(kept(store)) or "Nothing kept yet.")
    except (ConfigurationError, StorageError) as exc:
        parser.error(str(exc))
    return 0


def keep(save: Callable[[], Manifest], retry: str) -> None:
    """Keeping a copy in the bucket never fails the command it follows: the files are
    complete on this machine, so `retry` keeps them later."""
    try:
        print(f"Kept in the bucket: {describe(save())}")
    except Exception as exc:
        print(f"Not kept in the bucket ({type(exc).__name__}: {exc}). Later: {retry}")


def keep_theme(config: ContentConfig) -> None:
    """After anything that changes the channel's theme: a lock, a beat map, taste data."""
    if config.storage is not None:
        bucket, root = config.storage.bucket, config.theme.root
        keep(lambda: save_theme(GcsStore(bucket), root), "content storage save-theme")


COMMANDS = {"storage": _storage}
