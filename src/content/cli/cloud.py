"""`content cloud setup`: the Google Cloud side of `docs/google-cloud.md` in one command, safe to
run again. It checks what only the person can do (gcloud installed, signed in, a project with
billing), then does the rest: turns on Cloud Storage, makes the bucket with the right settings
or corrects an existing one, connects the channel, and keeps it for the first time.

gcloud runs through `Gcloud`, so the steps can be tested without Google."""

import argparse
import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from content.cli.check import GOOGLE_SIGN_IN, MARKS, Check
from content.config import load_config
from content.errors import ConfigurationError

# The free tier covers Standard storage in a few US regions only (docs/google-cloud.md).
FREE_LOCATIONS = ("us-east1", "us-west1", "us-central1")
SAM3D_UNSET = (
    "set SAM3D_PROJECT, SAM3D_REGION and SAM3D_BUCKET in .env (cloud/sam3d/setup.sh prints them)"
)
# A gcloud command that takes longer than this is waiting on the network quirk.
GCLOUD_SECONDS = 90


@dataclass(frozen=True)
class Result:
    ok: bool
    out: str
    error: str


Gcloud = Callable[..., Result]


def run_gcloud(*arguments: str) -> Result:
    """One gcloud command; a hang is reported, not waited on forever."""
    try:
        done = subprocess.run(
            ["gcloud", *arguments], capture_output=True, text=True, timeout=GCLOUD_SECONDS
        )
    except subprocess.TimeoutExpired:
        return Result(False, "", f"no answer in {GCLOUD_SECONDS} s")
    return Result(done.returncode == 0, done.stdout.strip(), done.stderr.strip())


def setup(
    bucket: str,
    config_path: Path,
    *,
    project: str | None = None,
    location: str = FREE_LOCATIONS[0],
    gcloud: Gcloud = run_gcloud,
    keep: Callable[[Path], str] | None = None,
) -> list[Check]:
    """Every step, in order; it stops at the first one the person has to do."""
    done: list[Check] = []

    def step(check: Check) -> bool:
        done.append(check)
        return check.status != "missing"

    if not step(_installed()):
        return done
    if not step(_signed_in(gcloud)):
        return done
    if not step(_python_signed_in()):
        return done
    chosen = _project(gcloud, project)
    if not step(chosen) or not step(_billing(gcloud, chosen.detail)):
        return done
    if not step(_storage_on(gcloud, chosen.detail)):
        return done
    if not step(_bucket(gcloud, bucket, chosen.detail, location)):
        return done
    if not step(_connect(config_path, bucket)):
        return done
    try:
        kept = (keep or _keep_first)(config_path)
    except Exception as exc:
        step(Check("First save", "missing", f"{type(exc).__name__}: {exc}", _hint(str(exc))))
        return done
    step(Check("First save", "ready", f"kept {kept}"))
    return done


def _installed() -> Check:
    if shutil.which("gcloud"):
        return Check("gcloud", "ready", "installed")
    return Check(
        "gcloud",
        "missing",
        "not installed",
        "Install it (docs/google-cloud.md, step 5): on macOS `brew install --cask "
        "google-cloud-sdk`; on Linux or WSL `curl https://sdk.cloud.google.com | bash`.",
    )


def _signed_in(gcloud: Gcloud) -> Check:
    signed = gcloud("auth", "list", "--filter=status:ACTIVE", "--format=value(account)")
    if signed.ok and signed.out:
        return Check("Signed in", "ready", signed.out.splitlines()[0])
    return Check(
        "Signed in",
        "missing",
        signed.error or "no account",
        "In a terminal of your own (not inside Claude Code): `gcloud auth login`.",
    )


def _python_signed_in() -> Check:
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or GOOGLE_SIGN_IN.is_file():
        return Check("Signed in for the pipeline", "ready", "yes")
    return Check(
        "Signed in for the pipeline",
        "missing",
        "not yet",
        "In a terminal of your own: `gcloud auth application-default login`.",
    )


def _project(gcloud: Gcloud, project: str | None) -> Check:
    if project:
        chosen = gcloud("config", "set", "project", project)
        if not chosen.ok:
            return Check("Project", "missing", chosen.error, "Check the project ID in the console.")
        return Check("Project", "ready", project)
    current = gcloud("config", "get-value", "project")
    if current.ok and current.out and current.out != "(unset)":
        return Check("Project", "ready", current.out)
    return Check(
        "Project",
        "missing",
        "none chosen",
        "Make one in the console (docs/google-cloud.md, step 3) and pass --project <its ID>.",
    )


def _billing(gcloud: Gcloud, project: str) -> Check:
    billing = gcloud("billing", "projects", "describe", project, "--format=value(billingEnabled)")
    if billing.ok and billing.out.lower() == "false":
        return Check(
            "Billing",
            "missing",
            "off: the free tier needs it on",
            "Console → Billing: link a billing account (docs/google-cloud.md, step 4).",
        )
    detail = "on" if billing.ok else "not readable here; the bucket step will tell"
    return Check("Billing", "ready", detail)


def _storage_on(gcloud: Gcloud, project: str) -> Check:
    enabled = gcloud("services", "enable", "storage.googleapis.com", "--project", project)
    if enabled.ok:
        return Check("Cloud Storage", "ready", "turned on")
    return Check("Cloud Storage", "missing", enabled.error, _hint(enabled.error))


def _bucket(gcloud: Gcloud, bucket: str, project: str, location: str) -> Check:
    url = f"gs://{bucket}"
    found = gcloud("storage", "buckets", "describe", url, "--format=json")
    if not found.ok:
        if "404" not in found.error and "not found" not in found.error.lower():
            return Check("Bucket", "missing", found.error, _hint(found.error))
        made = gcloud(
            "storage", "buckets", "create", url, f"--project={project}", f"--location={location}",
            "--default-storage-class=STANDARD", "--uniform-bucket-level-access",
            "--public-access-prevention", "--soft-delete-duration=0",
        )  # fmt: skip
        if not made.ok:
            return Check("Bucket", "missing", made.error, _hint(made.error))
        return Check("Bucket", "ready", f"{bucket}: made in {location}, private, no soft delete")
    settings = json.loads(found.out)
    wrong = []
    if not settings.get("uniform_bucket_level_access"):
        wrong.append("--uniform-bucket-level-access")
    if settings.get("public_access_prevention") != "enforced":
        wrong.append("--public-access-prevention")
    if str(settings.get("soft_delete_policy", {}).get("retentionDurationSeconds", "0")) != "0":
        wrong.append("--soft-delete-duration=0")
    if wrong:
        fixed = gcloud("storage", "buckets", "update", url, *wrong)
        if not fixed.ok:
            return Check("Bucket", "missing", fixed.error, _hint(fixed.error))
    notes = [f"{bucket}: already there" + (", settings corrected" if wrong else ", settings right")]
    if settings.get("default_storage_class") != "STANDARD" or (
        str(settings.get("location", "")).lower() not in FREE_LOCATIONS
    ):
        notes.append(
            f"(it is {settings.get('default_storage_class')} in {settings.get('location')}: "
            "outside the free tier, and a bucket's place cannot change)"
        )
    return Check("Bucket", "ready", " ".join(notes))


def _connect(config_path: Path, bucket: str) -> Check:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if data.get("storage", {}).get("bucket") == bucket:
        return Check("Channel", "ready", f"{config_path} already keeps to {bucket}")
    data["storage"] = {"bucket": bucket}
    config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return Check("Channel", "ready", f"{config_path} now keeps to {bucket}")


def _keep_first(config_path: Path) -> str:
    from content.storage import describe, open_store, save_theme

    config = load_config(config_path)
    assert config.storage is not None
    return describe(save_theme(open_store(config.storage), config.theme.root))


def _hint(error: str) -> str:
    """What to do about a gcloud error, in plain words."""
    lowered = error.lower()
    if "billing" in lowered:
        return "Billing is off for this project: docs/google-cloud.md, step 4."
    if "not available" in lowered or "already exists" in lowered or "409" in lowered:
        return "That bucket name is taken (names are shared by everyone): pick another."
    if "403" in lowered or "permission" in lowered:
        return (
            "Your account cannot do this here: sign in with the account that owns the project "
            "(`gcloud auth login`, `gcloud auth application-default login`)."
        )
    if "no answer" in lowered:
        return "Your network may block Google's metadata lookup: the quirk in docs/google-cloud.md."
    return "See docs/google-cloud.md, 'When something goes wrong'."


def _cloud(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="content cloud",
        description="Google Cloud: keeping the channel and its videos (docs/google-cloud.md), "
        "and the SAM 3D GPU job (cloud/sam3d/README.md)",
    )
    actions = parser.add_subparsers(dest="action", required=True)
    sam3d = actions.add_parser("sam3d", help="Make 3D from one picture on the cloud GPU (paid)")
    sam3d.add_argument("model", choices=("objects", "body"))
    sam3d.add_argument("image", type=Path)
    sam3d.add_argument(
        "--mask", type=Path, action="append", default=[], help="objects: one per thing"
    )
    sam3d.add_argument("--box", type=float, nargs=4, action="append", default=[],
                       metavar=("X0", "Y0", "X1", "Y1"), help="body: one per person")  # fmt: skip
    sam3d.add_argument("--focal", type=float, help="body: the focal length in pixels")
    sam3d.add_argument("--out", type=Path, required=True)
    make = actions.add_parser("setup", help="Everything after the sign-ins, safe to run again")
    make.add_argument("--bucket", required=True, help="A unique name, e.g. my-channel-videos-2026")
    make.add_argument("--project", help="The project ID (default: gcloud's current project)")
    make.add_argument("--location", default=FREE_LOCATIONS[0], choices=FREE_LOCATIONS)
    make.add_argument("--config", type=Path, required=True, help="The channel's config.json")
    args = parser.parse_args(arguments)
    if args.action == "sam3d":
        return _sam3d(args, parser)
    try:
        load_config(args.config)
    except ConfigurationError as exc:
        parser.error(str(exc))
    done = setup(args.bucket, args.config, project=args.project, location=args.location)
    for check in done:
        print(f"{MARKS[check.status]} {check.name}: {check.detail}")
        if check.fix and check.status == "missing":
            print(f"    {check.fix}")
    if done[-1].status == "missing":
        print("Do that, then run this again: it carries on where it stopped.")
        return 1
    print(f"Google Cloud is set up: the channel is kept in {args.bucket}.")
    return 0


def _sam3d(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from content.providers import sam3d
    from content.storage import GcsStore

    target = sam3d.from_environment()
    if target is None:
        parser.error(SAM3D_UNSET)
    if args.model == "objects" and not args.mask:
        parser.error("objects needs a --mask for each thing to make")
    picture = sam3d.Picture(
        name=re.sub(r"[^A-Za-z0-9_-]", "-", args.image.stem)[:64] or "picture",
        image=args.image,
        masks=tuple(args.mask),
        boxes=tuple(tuple(box) for box in args.box),
        focal=args.focal,
    )
    result = sam3d.make(
        args.model,
        [picture],
        args.out,
        bucket=GcsStore(target[1]),
        place=target[0],
    )
    print(json.dumps(result, indent=2))
    return 1 if "error" in result else 0


COMMANDS = {"cloud": _cloud}
