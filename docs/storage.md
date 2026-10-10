# Storage: What Is Kept for Good, and Where

Last reviewed: 2026-10-10

Two places hold files, with different jobs:

| Place | Job | Holds |
|---|---|---|
| `.cache/` (this machine) | the workbench | every paid generation (pictures, voices, video, and the text: research, plan, script, fact check, storyboard) and every render, keyed by its request, so nothing is paid for twice; `INDEX.csv` lists what each paid file is |
| `runs/<topic>/` (this machine) | the run | what each sign-off approved, and `building-blocks/`: each stage's output, readable (`.md`) and exact (`.json`) |
| your archive: a folder or a Google Cloud bucket | the archive | runs in progress and finished, and your channel's folder |

The archive is not a cache: the working cache (every keyframe drawn, every take spoken, every
render) never reaches it. Clearing the local cache after a final sign-off is a separate step
(not built yet).

## A folder or a bucket

The archive works the same either way (`storage.LocalStore`, `storage.GcsStore`): the same
layout, the same versions, the same commands. Choose by what you want to survive:

| | A folder | A Google Cloud bucket |
|---|---|---|
| setting up | none: `"storage": {"folder": "archive"}` in the channel's `config.json`, or `content new-channel <name> --folder archive` | about 20 minutes, once ([google-cloud.md](google-cloud.md)) |
| cost | nothing | free up to 5 GB, then $0.02 per GB a month |
| survives the computer dying | only if the folder is on another drive, or one that syncs (an external disk, Dropbox, iCloud Drive, OneDrive) | yes |
| another computer | copy or sync the folder there, then `storage pull --folder <it> --channel <name>` | `storage pull --bucket <it> --channel <name>` |

`archive/` in the project is gitignored, so it is never published; any folder outside the
project is safe too. A relative folder is found from the project root, and `~` means your home
folder: `"folder": "~/Dropbox/my-channel-archive"`. Moving from one to the other later: change
the `storage` section, then `content storage save-theme` and `content storage archive
runs/<topic>` for each run you want there.

## What a run keeps

At every sign-off the run folder gets only what was approved (`RunFolder.publish`): a run may
draw dozens of keyframes and its folder holds only the ones it used. So a run folder is what is
kept, minus what was only there to decide (`storage.RUN_FILES`, `RUN_PATTERNS`):

| Kept | Left out |
|---|---|
| `building-blocks/`: research, plan, script, fact check, storyboard, as `.md` and `.json` (a few hundred KB) | `3-scenes/animatic.mp4` and `story-sheet/`: previews |
| `3-scenes/S*`: each scene's signed-off keyframe (or clip) | `review.html`: the review page |
| `2-narration.m4a`, `1-script.md`, `brief.md`, and `4-final.mp4` once there is one | `.work/` except the files beside, and all of `.cache/` |
| `decisions.md`, `cost.csv`: how it was made and what it cost | |
| `.work/resume.json`, `.work/choices.json`: the approved state, so a re-cut can start from it | |
| `.work/steps.jsonl` while the run is unfinished: what `--resume` carries on from, on any machine | |

**In progress and finished, never both.** An unfinished run is kept in
`runs/in-progress/<topic>/`, updated at every sign-off (only the files that changed are
uploaded). When it passes the Final cut it moves to `runs/finished/<topic>/`: what the
in-progress copy already holds is copied inside the archive rather than uploaded again, the
finished copy is checked, and only then is the in-progress copy deleted. It held nothing the
finished copy lacks but the step log, which a finished run no longer needs. If the finished copy
is not whole, the in-progress copy stays and the run says so.

**Research is the expensive block, so it is kept three ways:** in the run's
`building-blocks/research.json`, in the text cache (the same request is never paid twice, across
runs too), and in the archive. A new video can start from it:
`content "<topic>" --research runs/<earlier>/building-blocks/research.json`
([runs-and-review.md](runs-and-review.md)).

## Your channel is private

The engine and the starter kit are open source; what makes a channel yours is not. Git holds
only `themes/starter/`. Every other folder in `themes/` is a channel: gitignored, and kept whole
in the archive (`storage.save_theme`, `THEME_SKIPPED`):

| Kept | Left out |
|---|---|
| `theme.json`, `SKILL.md`, `README.md`, `references/`, `fonts/`: the recipe | `learning/embedder/`: a published model, downloaded again on first use |
| `config.json`: the channel's configuration, `storage` included | |
| `spend.sqlite`: everything spent, and what is left ([spending.md](spending.md)) | |
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

**One machine at a time.** A save replaces what the archive holds with this machine's theme. On
another machine, `storage pull` first, or its older copy would replace your newer labels.

Measured sizes: about **190 MB** a long video (a 2:48 final is about 156 MB); a short should be
well under 100 MB.

## Layout

One folder or bucket (`storage.folder` or `storage.bucket` in your channel's `config.json`):

```
runs/in-progress/<topic>/...   an unfinished run, under its own file names, and manifest.json
runs/finished/<topic>/...      a finished run, the same way
blobs/<sha256>                 the channel's files, named by their hash
themes/<name>.json             the channel's manifest: each file's path, hash, size and type
themes/<name>/versions/<saved>.json
                               every earlier state of the channel, never deleted
```

- **Runs are browsable.** Their files keep their names, so the folder (or the Google Cloud
  console) shows `building-blocks/research.md`, not a hash. `content storage show runs/finished/<topic>` lists
  one by file.
- **The channel is stored by hash** so that every version shares the files that did not change:
  a hundred versions cost little more than one. `content storage show themes/<name>` lists it.
- **Nothing is left behind.** Keeping a run again uploads what changed and deletes what the run
  no longer has; replacing a channel file deletes the blob nothing uses any more.
- **What comes back is what went in.** Restoring checks every file against its hash; Google's
  client checks every upload against its CRC32C checksum, and a folder writes each file whole
  or not at all.

## When it happens

| When | What | Command to do it by hand |
|---|---|---|
| every sign-off of an unfinished run | the run so far is kept in progress | `content storage archive runs/<topic> --config themes/<name>/config.json` |
| the run finishes after the Final cut sign-off | the run moves to finished | the same command |
| anything that changes the theme: `voice-lock`, `music-lock`, `music-map`, `harvest`, `label`, `verdict`, `train`, and the learning after each run | the theme is kept | `content storage save-theme --config …` (also after editing `theme.json` or `SKILL.md` by hand) |
| a fresh clone, or a new machine | the channel comes back, its configuration included | `content storage pull --bucket <bucket> --channel <name>` (or `--folder <folder>`) |
| a theme edit you regret | an earlier version comes back | `content storage versions --config …`, then `pull --version <saved> --config …` |
| you want a run back (to watch it, re-cut it, or carry it on) | its kept files return to `runs/<topic>/`: the finished copy, or the run in progress | `content storage restore <topic> --config …` |
| | what the archive holds; one run or channel by file | `content storage list --config …`, `content storage show <name> --config …` |

Keeping never fails the command it follows: if the archive cannot be reached, the files are still
complete on this machine and the message gives the command to keep them later. Without a
`storage` section in the configuration nothing leaves the machine.

## Starting again on a fresh clone

Everything to re-run is in git, the archive, or your password manager:

| What | Where |
|---|---|
| the engine, prompts, the starter kit | GitHub |
| your channel: settings, configuration, voice, music, taste data, notes | the archive |
| finished runs | the archive |
| the OpenRouter key (`.env`) | this machine only: keep a copy in your password manager |
| `.cache/`: every paid generation | this machine only: rebuilding it costs money |

```bash
git clone <repo> && cd <repo>
python -m venv .venv && .venv/bin/pip install -e '.[live,learn,cloud,dev]'
gcloud auth application-default login           # a bucket only: your Google sign-in, no key file
.venv/bin/content storage pull --bucket <bucket> --channel <name>   # or --folder <folder>
cp .env.example .env                            # paste the OpenRouter key
```

Then every command takes `--config themes/<name>/config.json`.

A restored run brings back the video and what was signed off, not the working cache: re-cutting
it rebuilds from those files, and anything that was not signed off is paid for again.

## Cost of a bucket

A folder costs nothing. The bucket is Standard storage in `us-east1`, inside Google Cloud's Always Free tier (checked
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

## Setting up a bucket (once)

Step by step, for someone who has never used Google Cloud, with what each option means and
what to do when something goes wrong: [google-cloud.md](google-cloud.md). In short: a Google
Cloud project with billing on (the free tier needs a card) and a budget alert, the gcloud tool,
two sign-ins (`gcloud auth login`, `gcloud auth application-default login`), a Standard bucket
in `us-east1` with public access prevented and soft delete off, the `cloud` extra, and a
`storage` section in the channel's `config.json`. After the sign-ins, `content cloud setup
--bucket <name> --config …` does the rest and is safe to run again; `content check --config …`
confirms it.

There are no key files: only your own sign-in, saved under `~/.config/gcloud/`, outside the
project. Bucket versioning and Autoclass stay off: the channel's versions are kept by
`storage.py`, sharing unchanged files.
