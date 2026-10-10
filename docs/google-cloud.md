# Google Cloud: Keeping Your Channel and Videos Safe

Last reviewed: 2026-10-10

This is optional. Without it, everything works, but your channel and your videos live only on
your computer: lose the computer and they are gone. With it, they are also kept in a "bucket"
(a private folder in Google's cloud) that only you can open:

- **Your channel**, after every change, with every earlier version kept: a change you regret
  can always be undone.
- **Every video you are making**, at each sign-off: the research, plan and script, and what you
  approved. Research is the most expensive step, and this way it is never lost.
- **Every finished video**, for good, in one place. When a video finishes, its in-progress copy
  is removed: nothing is kept twice.
- **A new computer gets everything back** with one command.

It takes about 20 minutes, once. An assistant (Claude Code) can do most of it for you: you do
the parts that need you (signing in, adding a card), and it runs the rest.

## What it costs

| | |
|---|---|
| Storage | free up to 5 GB a month, then $0.02 per GB a month |
| A finished long video | about 190 MB; a short one well under 100 MB |
| An unfinished video | 20–50 MB until it finishes |
| Your channel | a few MB, with all its versions |

5 GB holds about 25 long videos. Google asks for a card even for the free tier; you will not
be charged within it, and step 4 sets an email alert long before anything costs money.

## The steps

### 1. A Google account

Any Google account works (Gmail, or your work's Google account if it allows Cloud). Use the one
you want to own the videos.

### 2. Open Google Cloud and accept the terms

Go to [console.cloud.google.com](https://console.cloud.google.com), sign in, and accept the
terms of service.

### 3. Make a project

A project is the box your bucket lives in. At the top of the page, click the project picker →
**New project**. Name it after your channel (for example `my-channel-videos`). Google gives it a
**project ID** (shown under the name, often with numbers added): write it down, you need it in
step 6.

### 4. Turn on billing, and set an alert

1. Menu (☰) → **Billing** → link a billing account to your project, adding a card. This is what
   unlocks the free tier.
2. **Billing → Budgets & alerts → Create budget.** Set an amount of $1 (or £1), with alerts at
   50% and 100%. Google emails you if spending ever approaches it. You should never see one.

### 5. Install the gcloud tool

This is how your computer talks to Google Cloud. In a terminal:

**macOS:**

```bash
brew install --cask google-cloud-sdk
```

**Ubuntu, Debian, or Windows with WSL:**

```bash
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
```

(Accept the defaults it offers.) Check it worked: `gcloud --version` prints a version.

### 6. Sign in, twice, in your own terminal

Open a terminal window of your own (not inside Claude Code: these sign-ins open a browser and
may ask you to paste a code back, which Claude Code cannot do for you). Run each line, follow
the browser, and come back:

```bash
gcloud auth login                       # lets the gcloud tool use your account
gcloud auth application-default login   # lets the video pipeline use your account
gcloud config set project YOUR-PROJECT-ID
```

The sign-in is saved on your computer (in `~/.config/gcloud/`), never in the project folder,
and there are no key files to keep safe.

### 7. Make the bucket and connect your channel: one command

Bucket names are shared by everyone on Google Cloud, so yours must be unique: use your channel's
name with something added (for example `my-channel-videos-2026`). Lower case, numbers and
hyphens only. The assistant runs this for you, in the project folder:

```bash
.venv/bin/pip install -e '.[cloud]'
.venv/bin/content cloud setup --bucket YOUR-BUCKET --config themes/<name>/config.json
```

It checks each step and does the rest, and is safe to run again:

| Step | What it does |
|---|---|
| gcloud, the two sign-ins, the project, billing | checks them; if one is missing it stops and says exactly what to do (steps 3–6), then you run it again |
| Cloud Storage | turns it on for the project |
| the bucket | makes it, or, if it is already there, checks its settings and corrects them |
| your channel | adds `"storage": {"bucket": "YOUR-BUCKET"}` to its `config.json` |
| first save | keeps your channel in the bucket for the first time |

The settings it gives the bucket, and why:

- `us-east1` and Standard storage: the free tier only covers Standard storage in a few US
  regions (`--location us-west1` or `us-central1` also work). Your videos are no less private
  there.
- Public access prevented: nothing in it can ever be made public by accident.
- Soft delete off: by default Google keeps deleted files for 7 days and bills for them;
  replacing a re-cut video would then be paid for twice for a week.
- One way of controlling access (uniform): only your account's permissions apply.

A bucket's region and class cannot change after it is made; the command says so if an existing
one is outside the free tier. `content check --config themes/<name>/config.json` confirms
everything ("Storage: the bucket … reachable").

From now on it happens by itself.

## What happens from now on

| When | What is kept |
|---|---|
| any change to your channel (a voice or music locked, labels, training, every run's learning) | the channel, with the earlier state as a version |
| you edit the channel's words by hand | ask the assistant to "save my channel" (`content storage save-theme`) |
| each sign-off of a video | that video so far, in `runs/in-progress/<topic>/` |
| a video finishes | it moves to `runs/finished/<topic>/`, and the in-progress copy is removed |

To look inside: [console.cloud.google.com/storage](https://console.cloud.google.com/storage) →
your bucket. Runs keep their own file names (open `building-blocks/research.md` to read a
video's research). Your channel is kept as files named by codes, so that every version shares
what did not change: `content storage show themes/<name>` lists it by name.

| You want to | Say to the assistant, or run |
|---|---|
| see what is kept | `content storage list --config …` |
| see one video or the channel, file by file | `content storage show runs/finished/<topic> --config …` |
| get a video back | `content storage restore <topic> --config …` |
| undo a change to your channel | `content storage versions --config …`, then `content storage pull --version <date> --config …` |
| set up a new computer | after the steps above (5, 6, and installing the project): `content storage pull --bucket YOUR-BUCKET --channel <name>` |

Details of the layout and what is kept: [storage.md](storage.md).

## When something goes wrong

| You see | Do this |
|---|---|
| `content check` says "not signed in to Google" | step 6, in your own terminal |
| "The billing account for the owning project is disabled" or "billing not enabled" | step 4 |
| "The requested bucket name is not available" | the name is taken: pick another (step 7) |
| "403" or "does not have storage.objects… access" | you signed in with a different Google account from the one that owns the bucket: `gcloud auth application-default login` again with the right one |
| every gcloud command hangs, or `content check` says "no answer" | the network quirk below |

**The network quirk.** gcloud and Google's Python library first check whether they are running
inside Google's own cloud, by looking up `metadata.google.internal`. Some home and office
networks never answer that lookup, so every command waits forever. Test it:
`getent hosts metadata.google.internal` hangs on an affected network. The fix tells them not to
check; add these lines to the end of your shell profile (`~/.bashrc`, or `~/.zshrc` on macOS),
then open a new terminal:

```bash
export GCE_METADATA_ROOT=127.0.0.1:1
export GCE_METADATA_IP=127.0.0.1:1
export GCE_METADATA_HOST=127.0.0.1:1
export NO_GCE_CHECK=True
```

and run `gcloud config set core/check_gce_metadata false` once.

## Stopping

To stop keeping things in the cloud, remove the `storage` section from your channel's
`config.json`. Nothing is deleted: what is in the bucket stays until you delete it in the
console. To close it all, delete the bucket, then the project, in the console.
