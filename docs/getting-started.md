# Getting Started: From Nothing to Your First Video

Last reviewed: 2026-10-10

This guide is for anyone, technical or not. You will install a few free tools, copy and paste
some commands, and then talk to an AI assistant (Claude Code) in plain English. The assistant
builds your channel with you and makes the videos; you decide what they look and sound like,
and you sign off before anything costs money.

Allow about an hour for the setup, most of it waiting for installs.

## What you need

| | What it is | Cost |
|---|---|---|
| A computer | macOS or Linux. On Windows, install [WSL](https://learn.microsoft.com/windows/wsl/install) first and follow the Linux steps inside it | |
| Python 3.11 or newer | runs the pipeline | free |
| ffmpeg | puts the video together | free |
| git | downloads the code | free |
| [Claude Code](https://claude.com/claude-code) | the assistant you talk to | needs a Claude subscription or an Anthropic API account |
| An [OpenRouter](https://openrouter.ai) account with credit | one key reaches every model the videos use (writing, voices, pictures, video) | pay as you go: a short video is capped at $5 by default; a long one costs more, and you are told before you pay |
| A Google Cloud bucket (optional) | keeps your channel and finished videos safe, with every earlier version | free up to 5 GB, a few pence a month beyond ([storage.md](storage.md)) |

## 1. Install the tools

Open a terminal (on macOS: the Terminal app; on Linux: your usual terminal) and paste the block
for your system, one line at a time.

**macOS** (installs [Homebrew](https://brew.sh) first if you do not have it):

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python@3.12 ffmpeg git
```

**Ubuntu, Debian, or Windows with WSL:**

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ffmpeg git
```

**Claude Code** (any system):

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

Check everything is there; each line should print a version, not an error:

```bash
python3 --version && ffmpeg -version | head -1 && git --version && claude --version
```

## 2. Get the code and try it for free

```bash
git clone https://github.com/ethangolledge/curious-button-pusher.git
cd curious-button-pusher
python3 -m venv .venv
.venv/bin/pip install -e '.[live,learn,dev]'
```

Now a complete practice run, with stand-in models, so nothing is paid for and no key is needed:

```bash
.venv/bin/content "The Great Stink" --sources fixtures/example_input.json --config config/config.json
```

A page opens in your browser asking you to sign off the start: that is how every real video
works too. Approve it, and the run carries on to the end. Everything it made is in
`runs/the-great-stink/`. (The words are placeholders: the stand-ins show the steps, not the
quality.)

## 3. Add your OpenRouter key

1. Sign up at [openrouter.ai](https://openrouter.ai), add some credit (Settings → Credits), and
   create a key (Settings → Keys). Give the key a spending limit you are comfortable with: the
   pipeline never spends more than the key allows.
2. Put the key where the pipeline will find it:

```bash
cp .env.example .env
nano .env        # paste your key after OPENROUTER_API_KEY=, then Ctrl+O, Enter, Ctrl+X
```

The `.env` file stays on your computer; it is never uploaded anywhere.

## 4. Make your channel, with Claude Code

Start the assistant in the project folder:

```bash
claude
```

Then just say what you want, for example:

> I'd like to make my own channel. It's about the strange history of everyday objects, told
> with dry humour, and I'd like it to look like old woodcut prints.

The assistant follows the repository's own instructions (`AGENTS.md` and the `new-channel`
skill). It will:

1. Create your channel folder, `themes/<your-channel>/`, from the starter kit, with its own
   settings file. This folder is yours: it is never uploaded to GitHub.
2. Talk through how the channel should feel, look and sound, and write it up.
3. Let you **audition narrator voices** and **music** (a few cents each; it asks first). You
   listen and pick; the choice is locked into your channel.
4. Check the channel loads, and offer to set up your Google Cloud bucket so it is backed up.

You can change anything later by telling the assistant ("make the narrator slower", "darker
colours"), and it edits the channel for you.

## 5. Make a video

In Claude Code, describe the story you want, in a sentence or a paragraph:

> Make a video about why London's Parliament once hung curtains soaked in lime.

The assistant researches the size of the story, then asks you **one round of questions** with
its recommendations and the costs: short or long, how many scenes, which angle. After that the
pipeline runs by itself and stops only for your **sign-offs**, each before money is spent on the
next step:

| Sign-off | You see | Approving pays for |
|---|---|---|
| Start | the plan for this video and its estimated cost | research and writing |
| Story plan (long videos) | the story, beat by beat | the script |
| Script | the narration, what a first-time listener understood, and the fact checks | the narration |
| Narration | every passage, to listen to | the pictures |
| Pictures | the animatic and every scene's picture | the moving transitions |
| Final cut | the finished video | nothing: it is done |

Each sign-off opens as a page in your browser. Approve it, or write notes (on the whole thing or
on a line, `U3: say the year first`), and the pipeline revises only what you named. You can
close the terminal; tell Claude Code "carry on with my video" later and it picks up where it
stopped, without paying again for anything already made.

The finished video is `runs/<your-topic>/4-final.mp4`, ready for TikTok, Reels, Shorts or
YouTube.

## 6. Keep your channel safe (optional)

Your channel lives only on your computer unless you give it a bucket. With one, every change is
saved with its history, and a new computer gets everything back with one command. Ask Claude
Code: "set up Google Cloud storage for my channel", or follow
[storage.md](storage.md#setting-it-up-once).

## When something goes wrong

| You see | Do this |
|---|---|
| `ffmpeg: command not found` | install it (step 1) and open a new terminal |
| `Set OPENROUTER_API_KEY in .env` | step 3 |
| "The OpenRouter key has $… left" | add credit or raise the key's limit at openrouter.ai |
| A run stopped part-way | in Claude Code: "carry on with my video"; nothing already paid for is paid again |
| `gcloud` commands hang | [storage.md](storage.md), the quirk at the end |

## Words you will meet

- **Channel:** everything that makes your videos yours (look, voice, music, writing voice).
  Lives in `themes/<name>/`.
- **Sign-off:** a stop where you approve or comment, always before money is spent.
- **Run folder:** `runs/<topic>/`, everything one video made, with plain names
  (`1-script.md`, `2-narration.m4a`, `4-final.mp4`).
- **Jev:** a fast, cheap judge that checks every line and picture against dozens of questions,
  so you only see what needs a person.

More: how it works ([architecture.md](architecture.md)), the sign-offs in detail
([runs-and-review.md](runs-and-review.md)), every channel setting ([themes.md](themes.md)).
