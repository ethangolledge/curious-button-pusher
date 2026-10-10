# Getting Started: From Nothing to Your First Video

Last reviewed: 2026-10-10

This guide is for anyone, technical or not. You install four free tools and download the
project (about 15 minutes, copying and pasting a few lines). Then you open an AI assistant,
Claude Code, and say "help me get set up": from there it is a conversation. The assistant takes
you through the rest one step at a time, does the technical parts itself, and asks you only for
decisions, for things only you can do (like adding credit to an account), and for a yes before
anything costs money.

## What you need

| | What it is | Cost |
|---|---|---|
| A computer | macOS or Linux. On Windows, install [WSL](https://learn.microsoft.com/windows/wsl/install) first (it gives Windows a Linux terminal) and follow the Linux lines inside it | |
| Python, ffmpeg and git | free tools the project runs on; step 1 installs them | free |
| [Claude Code](https://claude.com/claude-code) | the assistant you talk to | a Claude subscription (Pro or Max) or an Anthropic API account |
| An [OpenRouter](https://openrouter.ai) account with credit | one key pays for every model the videos use: writing, voices, pictures, video | pay as you go: $10 is a good start; a short video is capped at $5, and you are told every cost before you pay |
| A Google Cloud bucket (optional) | keeps your channel and videos safe, with every earlier version | free up to 5 GB (about 25 long videos) ([google-cloud.md](google-cloud.md)) |

## Never used a terminal?

A terminal is a window where you type commands instead of clicking. On macOS, open **Terminal**
(press Cmd+Space, type "Terminal", press Enter). On Linux, open your terminal app; on Windows,
open **Ubuntu** after installing WSL. To run a line from this guide: copy it, paste it into the
terminal, press Enter, and wait until it finishes (you can type again). If it asks for your
password, type your computer's password: nothing appears as you type, that is normal.

## 1. Install the tools

Paste the lines for your system, one at a time.

**macOS** (the first line installs [Homebrew](https://brew.sh), which installs the rest; skip it
if you have it):

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

Check everything is there; each part should print a version, not an error:

```bash
python3 --version && ffmpeg -version | head -1 && git --version && claude --version
```

## 2. Download the project and open the assistant

```bash
git clone https://github.com/ethangolledge/curious-button-pusher.git
cd curious-button-pusher
claude
```

The first time, Claude Code asks you to sign in to your Claude account. Then say:

> Help me get set up. I'd like a channel about the strange history of everyday objects, told
> with dry humour, that looks like old woodcut prints.

(Your own idea, in your own words. A sentence is enough.)

## 3. The conversation

The assistant follows the project's own instructions (`AGENTS.md` and its `new-channel` skill),
so it knows every step. It tells you where you are as it goes ("Stage 3 of 12"). Expect:

| Stage | What happens | Your part | Cost |
|---|---|---|---|
| 0. Where are we? | it looks at what is already set up | say which computer you have | free |
| 1. The computer | it installs the project, and offers a free practice video with stand-in models | run a line in your own terminal if it needs your password | free |
| 2. Your key | you create an OpenRouter account and key; you put the key in a file called `.env` | sign up, add credit, paste the key into `.env` (never into the chat) | your credit |
| 3. Google Cloud (optional) | it explains, and does most of it | make an account and a project, add a card, sign in twice in your own terminal ([google-cloud.md](google-cloud.md)) | free tier |
| 4. Your channel | it creates your channel's folder | choose a name | free |
| 5. The channel in words | it asks what stories, for whom, what feeling, what storyteller, then writes it up | answer, and approve what it wrote | free |
| 6. The look | it offers styles, colours, light, and how real people are drawn | choose | free |
| 7. Movement and feeling | how much the pictures move, and how each scene's mood is drawn | choose | free |
| 8. The narrator | it plays you voices to choose from, or designs one | listen and pick | a few cents |
| 9. The music | generated for each video, or one signature track you choose | listen and pick | a few cents |
| 10. Subtitles and formats | fonts, colours, and where you publish (TikTok, YouTube…) | choose | free |
| 11. Check and keep | it tests everything and saves your channel | nothing | free |
| 12. Your first video | it hands over to making a video (below) | tell it a story | up to $5 for a short |

You can stop at any point: it writes down where you got to (in your channel's
`notes/setup.md`), and next time it carries on from there. At any time, `content check` (or
asking "is everything set up?") lists what is ready and what is not, with the fix.

## 4. Making a video

Tell the assistant the story, in a sentence or a paragraph:

> Make a video about why London's Parliament once hung curtains soaked in lime.

It sizes the story, then asks you **one round of questions** with its recommendations and the
costs: short or long, how many scenes, which angle. After that the pipeline runs by itself and
stops only for your **sign-offs**, each before money is spent on the next step:

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
YouTube. Everything that went into it is beside it in `building-blocks/`: the research, the
plan, the script, the fact check and the storyboard, each as a readable `.md` file. Research is
the expensive part, so it is never paid for twice: ask for "another video from the research in
<your-topic>", and it starts there. `.cache/INDEX.csv` lists everything you have ever paid for,
with its cost.

## Changing things later

Just say it: "make the narrator slower", "darker colours", "try a new music track", "save my
channel". The assistant edits your channel and tells you what a change will cost (most are
free). Every setting, with what it does: [theme-settings.md](theme-settings.md).

## When something goes wrong

| You see | Do this |
|---|---|
| `command not found` for python3, ffmpeg or git | step 1, then open a new terminal |
| `claude: command not found` | the Claude Code line in step 1, then open a new terminal |
| `Set OPENROUTER_API_KEY in .env` | stage 2: the key goes in the `.env` file in the project folder |
| "The OpenRouter key has $… left" | add credit, or raise the key's limit, at openrouter.ai |
| A run stopped part-way | in Claude Code: "carry on with my video"; nothing already paid for is paid again |
| Anything with Google Cloud | [google-cloud.md](google-cloud.md), "When something goes wrong" |
| You are not sure what is set up | `.venv/bin/content check` in the project folder |
| You want to know what you have spent and what is left | ask "how much have I got left?", or `content spend --config themes/<name>/config.json` ([spending.md](spending.md)) |

## Words you will meet

- **Channel:** everything that makes your videos yours: the look, voice, music and way of
  telling stories. It lives in `themes/<name>/`, private to you.
- **Sign-off:** a stop where you approve or comment, always before money is spent.
- **Run folder:** `runs/<topic>/`, everything one video made, with plain names
  (`1-script.md`, `2-narration.m4a`, `4-final.mp4`, `building-blocks/`).
- **Bucket:** a private folder in Google's cloud that keeps your channel and videos safe.
- **Jev:** a fast, cheap judge that checks every line and picture against dozens of questions,
  so you only see what needs a person.

More: how it works ([architecture.md](architecture.md)), the sign-offs in detail
([runs-and-review.md](runs-and-review.md)), how a channel fits together ([themes.md](themes.md)).
