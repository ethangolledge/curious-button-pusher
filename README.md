# content

`content` turns a true story into a narrated video: short and vertical (TikTok, Reels, Shorts)
or long and widescreen (YouTube). It researches the story, plans one angle, writes and
fact-checks a connected narration, storyboards it, then produces it: a narrator, illustrated
keyframes that glide and breathe, an AI morph from each picture into the next, word-timed
subtitles and a music bed, assembled by ffmpeg into a finished MP4.

You direct. Bring a rough idea; the assistant comes back once with recommendations (format,
length, how many scenes, the angle, with costs), and then the run takes off. It stops for your
sign-off only before money is spent on the next step, in a review window that opens by itself.
Everything in between is judged and corrected automatically.

This repository is the engine and a starter kit. **Your channel** (how it looks, sounds and
writes, its voice, music and taste) is yours: you build it from the starter, and it stays
private. It is a learning project: readable over clever, deterministic tests, no production
infrastructure. Publishing is out of scope.

## Start Here

**New to all of this?** Follow [docs/getting-started.md](docs/getting-started.md): install four
tools, download the project, open Claude Code and say "help me get set up". The assistant
takes you through the rest as a conversation, from your accounts to your channel to your first
video. No coding needed.

| You are… | Do this |
|---|---|
| new, with no channel yet | [Make your channel](#make-your-channel) |
| coming back to a channel kept in your bucket | [Bring your channel back](#bring-your-channel-back) |
| an AI assistant opening this repository | read [AGENTS.md](AGENTS.md): it says which of the two applies and which skill to follow |

## How It Works

```text
Research → Plan → Narration → Fact check → Listener test → Storyboard → Recording → Keyframes → Morphs → Edit
```

- **Five agents** (language models) do the reasoning: Fact Researcher, Editorial Director, Script
  Writer, Fact-Checking Editor, Visual Director. The fact checker sets what may be said, the
  Editorial Director decides what matters, and the Script Writer owns every word.
- **A first-time listener**, a separate model given only the narration, says what it understood;
  the gap between that and the plan is what gets revised before you are asked to sign off.
- **Jev**, a fast typed judge, answers dozens of small questions about every line, scene and join;
  confident failures go back to their owner with a targeted correction.
- **Code** does everything exact: references, timing, colour, budgets, caching.
- **A channel** decides how it all looks and sounds: the style, camera moves, motion effects,
  voice, music, subtitles and writing voice. The code holds no style and no story; swap the
  channel and the same pipeline makes a different show.

The full picture: [docs/architecture.md](docs/architecture.md).

## Try It (Offline, No Key)

Needs Python 3.11+ and ffmpeg.

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/content "The Great Stink" --sources fixtures/example_input.json \
  --config config/config.fake-video.json
```

The fake providers stand in for every model: they show the pipeline, the sign-offs and the run
folder (`runs/<topic>/`), not the quality of real research or writing. `config/config.json` does
the same without the video.

## Make Your Channel

```bash
.venv/bin/content new-channel my-channel
```

This creates `themes/my-channel/`: a complete, neutral theme copied from `themes/starter` and the
channel's own configuration, `themes/my-channel/config.json`. Then make it yours, step by step,
with `themes/my-channel/README.md` (the look, the writing voice, the narrator, the music, the
subtitles, the formats), or ask the assistant: it follows the `new-channel` skill and walks you
through the same steps. Every setting, with what it does and what changing it costs:
[docs/theme-settings.md](docs/theme-settings.md). `content check --config
themes/my-channel/config.json` says what is ready.

Your channel folder is gitignored, so nothing of it reaches a public repository. To keep it safe,
with its full history, give it a folder (`content new-channel my-channel --folder
~/Dropbox/my-channel-archive`, free) or your own Google Cloud bucket
([docs/google-cloud.md](docs/google-cloud.md)); [docs/storage.md](docs/storage.md) compares them.

## A Real Run

Every model is reached through [OpenRouter](https://openrouter.ai) with one key.

```bash
.venv/bin/pip install -e '.[live]'
cp .env.example .env            # paste your key after OPENROUTER_API_KEY=
.venv/bin/content "The story, or the whole idea in plain words" \
  --brief my-brief.md --config themes/my-channel/config.json
```

A run is capped at `production.max_usd` and never pays twice for anything unchanged. Briefs,
sources, resuming, the sign-offs and the run folder: [docs/runs-and-review.md](docs/runs-and-review.md).
Every model, its cost and how to swap it: [docs/models.md](docs/models.md).

Optional extras: `learn` (local taste models), `music` (beat mapping when locking a music bed),
`vision` (finding each picture's focal point for the camera), `cloud` (keeping your channel and
finished videos in a bucket).

## Bring Your Channel Back

On a fresh clone or another machine, with your channel kept in a bucket (with a folder: skip
the sign-in and pull with `--folder <folder>`):

```bash
.venv/bin/pip install -e '.[live,learn,cloud,dev]'
gcloud auth application-default login       # your own Google sign-in; no key files
.venv/bin/content storage pull --bucket <your-bucket> --channel my-channel
cp .env.example .env                        # paste your OpenRouter key
```

The whole channel comes back, its configuration included. Earlier versions of it:
`content storage versions --config themes/my-channel/config.json`
([docs/storage.md](docs/storage.md)).

## Documentation

| I want to… | Read |
|---|---|
| understand the pipeline | [docs/architecture.md](docs/architecture.md) |
| make a channel | [docs/themes.md](docs/themes.md) |
| run a video and review it | [docs/runs-and-review.md](docs/runs-and-review.md) |
| tune the narration, timing and music | [docs/narration.md](docs/narration.md) |
| tune the pictures and motion | [docs/visuals.md](docs/visuals.md) |
| know the models | [docs/models.md](docs/models.md), [docs/machine-learning.md](docs/machine-learning.md) |
| keep my channel and videos safe, and get them back | [docs/storage.md](docs/storage.md) |
| change the code | [docs/codebase.md](docs/codebase.md), [AGENTS.md](AGENTS.md) |

The full index: [docs/README.md](docs/README.md).

## Layout

```text
src/content/   the engine: graph, agents, judging, production (no style, no story)
themes/        starter: the kit every channel starts from. Every other folder is a channel:
               its theme, configuration, examples and notes, private and gitignored
config/        the offline demos and config.example.json, the template a channel copies
fixtures/      the demo story's brief and sources
tests/         deterministic tests; no credentials or network
docs/          how it works and how to tune it
runs/          one folder per story (gitignored)
```

## Validation

```bash
.venv/bin/python -m pytest          # about 20 s: behaviour, the free rehearsal, the architecture
.venv/bin/python -m pytest -m video # the 12 whole-video renders, after changing production code
.venv/bin/ruff check src tests
.venv/bin/mypy src tests
```

Tests use deterministic provider responses and the local ffmpeg, never a key or the network.
`tests/test_rehearsal.py` is the check to run before spending money: it carries every
configuration (your channel's included) through the whole pipeline with stand-in models.
