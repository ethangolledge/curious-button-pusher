# Storage: What Is Kept for Good, and Where

Last reviewed: 2026-10-09

Two places hold files, with different jobs:

| Place | Job | Holds |
|---|---|---|
| `.cache/` (this machine) | the workbench | every paid generation and every render, keyed by its request, so nothing is paid for twice while a video is being made |
| your cloud bucket | the archive | only what a finished video was made of, and your channel's folder |

The bucket is not a cache and never holds work in progress. A run that is abandoned, or is still
being made, never reaches it. Clearing the local cache after a final sign-off is a separate step
(not built yet).

## What a finished run keeps

At every sign-off the run folder gets only what was approved (`RunFolder.publish`): a run may
draw dozens of keyframes and its folder holds only the ones it used. So a finished run's folder is what is
kept, minus what was only there to decide (`storage.RUN_FILES`, `RUN_SCENES`):

| Kept | Left out |
|---|---|
| `4-final.mp4`, the video | `3-scenes/animatic.mp4` and `story-sheet/`: previews, superseded by the final |
| `3-scenes/S*`: each scene's signed-off keyframe (or clip) | `review.html`: the review page |
| `2-narration.m4a`, `1-script.md`, `brief.md` | `.work/` except the two files beside, and all of `.cache/` |
| `decisions.md`, `cost.csv`: how it was made and what it cost | |
| `.work/resume.json`, `.work/choices.json`: the approved state (a few KB), so a re-cut can start from it | |

## Your channel is private

The engine and the starter kit are open source; what makes a channel yours is not. Git holds
only `themes/starter/`. Every other folder in `themes/` is a channel: gitignored, and kept whole
in the bucket (`storage.save_theme`, `THEME_SKIPPED`):

| Kept | Left out |
|---|---|
| `theme.json`, `SKILL.md`, `README.md`, `references/`, `fonts/`: the recipe | `learning/embedder/`: a published model, downloaded again on first use |
| `config.json`: the channel's configuration, bucket included | |
| `examples/`, `notes/`: your regression examples, decisions and plans | |
| `voice/master.*`: the locked narrator (a real person's voice stays private) | `music/candidates/`: auditions |
| `music/bed.*` and its beat map `bed.map.json` | |
| `learning/*.jsonl`: your labels and the harvested examples (they hold story text) | |
| `learning/models/`: the promoted taste models (`ModelRegistry`) | |

A channel is a few MB. Saving it uploads only the files that changed.

**Versions: the theme's full history.** Every save that changes anything keeps the theme as it
was before, for good (`themes/<name>/versions/`, never deleted). A version costs only the files
that changed: a new `SKILL.md` is a few KB, new taste data a few MB. `storage versions` lists
them by date; `storage pull --version <date>` makes the theme exactly that version, removing
files added since. Going back saves the current theme first, so it is a version too and nothing
is lost either way.

**One machine at a time.** A save replaces what the bucket holds with this machine's theme. On
another machine, `storage pull` first, or its older copy would replace your newer labels.

Measured sizes: about **190 MB** a long video (a 2:48 final is about 156 MB); a short should be
well under 100 MB.

## Layout

One bucket (`storage.bucket` in your channel's `config.json`):

```
blobs/<sha256>        the bytes of every kept file, named by their hash
runs/<slug>.json      a finished run's manifest: each file's path, hash, size and type
themes/<name>.json    a channel's theme folder, the same way
themes/<name>/versions/<saved>.json
                      every earlier state of the theme, never deleted
```

- **Nothing is stored twice.** A file's name is its hash, and a hash already in the bucket is not
  uploaded again: a re-cut that keeps the keyframes adds only its new files.
- **Nothing is left behind.** Keeping a run again (after a re-cut) replaces its manifest and
  deletes the blobs no manifest uses any more.
- **What comes back is what went in.** Restoring checks every file against its hash, and the
  client checks every upload against its CRC32C checksum.

## When it happens

| When | What | Command to do it by hand |
|---|---|---|
| the run finishes after the Final cut sign-off | the run is kept | `content storage archive runs/<topic> --config themes/<name>/config.json` |
| anything that changes the theme: `voice-lock`, `music-lock`, `music-map`, `harvest`, `label`, `verdict`, `train`, and the learning after each run | the theme is kept | `content storage save-theme --config …` (also after editing `theme.json` or `SKILL.md` by hand) |
| a fresh clone, or a new machine | the channel comes back, its configuration included | `content storage pull --bucket <bucket> --channel <name>` |
| a theme edit you regret | an earlier version comes back | `content storage versions --config …`, then `pull --version <saved> --config …` |
| you want an old run back | its kept files return to `runs/<slug>/` | `content storage restore <slug> --config …` |
| | what the bucket holds | `content storage list --config …` |

Keeping never fails the command it follows: if the bucket cannot be reached, the files are still
complete on this machine and the message gives the command to keep them later. Without a
`storage` section in the configuration nothing leaves the machine.

## Starting again on a fresh clone

Everything to re-run is in git, the bucket, or your password manager:

| What | Where |
|---|---|
| the engine, prompts, the starter kit | GitHub |
| your channel: settings, configuration, voice, music, taste data, notes | the bucket |
| finished runs | the bucket |
| the OpenRouter key (`.env`) | this machine only: keep a copy in your password manager |
| `.cache/`: every paid generation | this machine only: rebuilding it costs money |

```bash
git clone <repo> && cd <repo>
python -m venv .venv && .venv/bin/pip install -e '.[live,learn,cloud,dev]'
gcloud auth application-default login           # your Google sign-in; there is no key file
.venv/bin/content storage pull --bucket <bucket> --channel <name>
cp .env.example .env                            # paste the OpenRouter key
```

Then every command takes `--config themes/<name>/config.json`.

A restored run brings back the video and what was signed off, not the working cache: re-cutting
it rebuilds from those files, and anything that was not signed off is paid for again.

## Cost

The bucket is Standard storage in `us-east1`, inside Google Cloud's Always Free tier (checked
2026-10-09, [free tier](https://docs.cloud.google.com/free/docs/free-cloud-features)):

| | Free each month | Beyond |
|---|---|---|
| Storage (Standard, US regions only) | 5 GB | $0.020 per GB a month |
| Writes and lists (Class A) | 5,000 | a fraction of a cent per thousand |
| Reads (Class B) | 50,000 | less still |
| Downloads | 100 GB | per GB |

Keeping a run costs about a dozen writes; 5 GB holds about 25 long videos. Past that, 10 GB in total
would cost about $0.10 a month. The colder classes (Nearline $0.010, Coldline $0.004, Archive
$0.0012 per GB a month) are not covered by the free tier, keep each file for 30, 90 or 365 days
at least and charge to read; they only start to pay past about 50 GB, by a lifecycle rule.

Set a small budget on the project (Billing → Budgets) so an email warns you long before it costs
anything.

## Setting it up (once)

Make a Google Cloud project (the free tier needs billing enabled, but stays free within its
limits), install the [gcloud CLI](https://cloud.google.com/sdk/docs/install), then:

```bash
gcloud auth login                                  # the gcloud tool
gcloud auth application-default login              # the Python client (storage.GcsStore)
gcloud config set project <your-project>
gcloud storage buckets create gs://<your-bucket> --location=us-east1 \
  --default-storage-class=STANDARD --uniform-bucket-level-access \
  --public-access-prevention --soft-delete-duration=0
pip install -e '.[cloud]'
```

Then give your channel the bucket: `content new-channel <name> --bucket <your-bucket>`, or add
`"storage": {"bucket": "<your-bucket>"}` to its `config.json`, and run `content storage
save-theme --config themes/<name>/config.json` once.

- **Soft delete is off on purpose.** New buckets keep deleted files for 7 days and bill for them;
  replacing a re-cut's final would be paid for twice for a week.
- Bucket versioning and Autoclass stay off (their defaults): the theme's versions are kept by
  `storage.py`, sharing unchanged files. Public access is blocked; there are no key files,
  only your own sign-in (`gcloud auth application-default login` saves a token under
  `~/.config/gcloud/`, outside the repo).

**Quirk: gcloud hangs on some networks.** gcloud and Google's Python client both look up
`metadata.google.internal` to see whether they run on a Google Cloud VM. On a network that never
answers that lookup (`getent hosts metadata.google.internal` hangs), every command waits
forever. Fix it in your shell profile by pointing the check at a port that refuses at once
(`GCE_METADATA_ROOT`, `GCE_METADATA_IP`, `GCE_METADATA_HOST` = `127.0.0.1:1`,
`NO_GCE_CHECK=True`), plus `gcloud config set core/check_gce_metadata false`.
