---
name: new-channel
description: Set someone up from nothing and build their channel with them, as a conversation in stages - their computer, their OpenRouter key, optional safe keeping (a folder or Google Cloud), then every part of the channel (its storytelling voice, look, movement, feeling, narrator, music, subtitles, formats) - through to their first video. Use when the repository has no channel yet (themes/ holds only starter), when someone new arrives ("help me get started", "set me up", "I want my own channel"), when someone forks it, or wants to change what makes an existing channel distinctive.
---

# Setting someone up, and building their channel

You are guiding a person who may have never used a terminal. They bring taste and decisions;
you do everything technical. By the end they have a working setup, a channel that is
unmistakably theirs, and a first video.

A channel is one private folder, `themes/<name>/`: its `theme.json` (every exact setting,
explained one by one in `docs/theme-settings.md`), its `SKILL.md` (the channel in words, read by
every creative agent), its `config.json` (which models it uses, its spending cap, where it is kept),
its voice and music once locked, its taste data, and `notes/`. It is gitignored and never
committed; only `themes/starter/` is shared. The engine in `src/` never changes for a channel.

## How to run the conversation

- **One stage at a time.** Say where you are and what comes next ("Stage 3 of 12: your
  narrator. Next: the music."). Never dump the whole plan on them.
- **Explain why, in one plain sentence,** before asking anything. Translate every term the
  first time ("a bucket: a private folder in Google's cloud").
- **Do it for them.** Run the commands and edit the files yourself. Ask the person only for:
  decisions of taste; what only they can do (accounts, payment, passwords, browser sign-ins);
  and a yes before anything that costs money.
- **What they must do themselves, and how:**
  - Websites (OpenRouter, Google Cloud): give the exact link and the clicks, one at a time.
  - Commands that need their password (`sudo apt …`) or open a browser sign-in
    (`gcloud auth …`): ask them to run them in a terminal window of their own, not inside
    Claude Code, which cannot type a password or paste a code back for them. Give the exact
    line to copy.
  - A short non-interactive command they want to see run in this session: they can type it
    after `!` in Claude Code.
- **Secrets never go through the chat.** Never ask them to paste an API key here; they put it
  in `.env` themselves (stage 2). Never print it, commit it, or write it anywhere else.
- **Offer, don't interrogate.** For taste, give two or three concrete options with your
  recommendation first ("Ink and watercolour (recommended for history: warm and human), flat
  paper cut-outs, or bold comic panels"). `AskUserQuestion` with at most four questions a
  round, each with a one-line reason.
- **Say the cost before anything paid,** in money: "about 30 cents for five voices".
  Everything in stages 0–7 and 10–11 is free.
- **Check after every stage** (`content check`, the theme tests) and say plainly what now
  works ("Your key works and has $9.80 on it.").
- **Write down progress** in `themes/<name>/notes/setup.md` after each stage: what was
  decided and why, what is done, what is next. A later session (yours or another assistant's)
  reads it and carries on. With a folder or bucket, `content storage save-theme` after each stage too.
- **If something fails,** read the error, fix what you can, and explain the rest in plain
  words. `docs/getting-started.md` and `docs/google-cloud.md` list the usual problems.

All commands below run in the project folder, as `.venv/bin/content …` (written `content`).
Channel commands take `--config themes/<name>/config.json` (written `--config <channel>`).

## Stage 0: Where are we? (free)

Find out before saying anything about steps:

- `ls themes` and `ls themes/*/notes/setup.md`: is there a channel, and how far did setup get?
  If `setup.md` exists, read it and carry on from where it stopped.
- Is the project installed? (`.venv/bin/content check` runs, or `.venv` is missing.)
- Ask, in one go: their computer (macOS, Windows, Linux), and what they want to make, in a
  sentence. That sentence guides every later suggestion.

## Stage 1: The computer (free, about 15 minutes)

Check what is installed: `python3 --version` (3.11 or newer), `ffmpeg -version`,
`git --version`. For anything missing, give them the exact lines for their system, to run in
their own terminal (they need their password):

- macOS: Homebrew if missing (`/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`),
  then `brew install python@3.12 ffmpeg git`.
- Ubuntu, Debian, or Windows with WSL: `sudo apt update && sudo apt install -y python3
  python3-venv python3-pip ffmpeg git`. On Windows, WSL itself first:
  https://learn.microsoft.com/windows/wsl/install.

Then install the project yourself:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[live,learn,dev]'
```

**Check:** `content check` shows Python, ffmpeg, ffprobe and the `live` extra ready (the key
comes next). Optionally show them a free practice run with stand-in models, so they see what
a run looks like: `content "The Great Stink" --sources fixtures/example_input.json --config
config/config.json` (a sign-off page opens; they approve it).

## Stage 2: The OpenRouter key (they add credit, about 5 minutes)

Why: one key pays for every model the videos use (writing, voices, pictures, video).

1. They sign up at https://openrouter.ai, then **Settings → Credits**: add credit. Suggest $10
   to start: a short video is capped at $5.
2. **Settings → Keys → Create key.** Give it a spending limit (the pipeline never spends more
   than the key allows, and lowers a run's cap to fit).
3. In their own terminal, in the project folder: `cp .env.example .env && nano .env`, paste
   the key after `OPENROUTER_API_KEY=`, then Ctrl+O, Enter, Ctrl+X. (Or any text editor:
   the file is `.env` in the project folder.)

4. Ask whether they want a budget for this project (optional: some only want to see what each
   project spends and what is left in total, which is always shown). If they do, record it once
   the channel exists (stage 4): `content spend budget openrouter <amount> --config <channel>`.

Tell them what is tracked: every paid call goes into their channel's spending ledger, with
OpenRouter's own figures read before every run, and `content spend` (or "how much have I got
left?") shows it all (`docs/spending.md`). Their Claude subscription is not tracked here.

**Check:** `content check` shows "OpenRouter key: works; $… left".

## Stage 3: Keeping it safe: a folder or Google Cloud (optional)

Why, in their terms: without it, the channel and videos live only in the project folder. With
it, every change to the channel is kept with its history, every video is kept at each sign-off
and when it finishes (never twice), and another computer can get everything back. Offer the
two ways, with your recommendation (`docs/storage.md`, "A folder or a bucket"):

- **A folder** (free, nothing to set up). Recommend it for anyone who wants to start quickly,
  and suggest a folder that survives the computer: on an external disk, or in Dropbox, iCloud
  Drive or OneDrive if they use one (`~/Dropbox/<channel>-archive`). `archive` inside the
  project also works and is never committed, but dies with the computer: say so plainly.
  Nothing to do now: stage 4 adds `--folder <it>`.
- **Google Cloud** (free tier, about 20 minutes). Recommend it when they want it safe without
  thinking about drives. Google asks for a card even so. Follow `docs/google-cloud.md`:
  - They do steps 1–6: account, terms, project (note the project ID), billing with a $1 budget
    alert, installing gcloud, and the two sign-ins in their own terminal.
  - You do step 7, once the channel exists (stage 4): install the `cloud` extra, then
    `content cloud setup --bucket <name> --config <channel>` (suggest a unique name like
    `<channel>-videos-2026`). It checks their part (gcloud, both sign-ins, the project,
    billing) and stops with the exact fix if one is missing; run it again once they have done
    it. Then it turns on Cloud Storage, makes or corrects the bucket, connects the channel and
    saves it.
  - If any gcloud command hangs, it is the network quirk at the end of `docs/google-cloud.md`.
  - Ask the amount of the budget alert they set, and record it after stage 4:
    `content spend budget google-cloud <amount> --kind monthly --config <channel>`.

Later is fine too: either can be added to the channel's `config.json` at any time.

**Check (after stage 4):** `content check --config <channel>` shows "Storage: the folder …" or
"Storage: the bucket … reachable".

## Stage 4: Name and create the channel (free)

Ask for the channel's name (the folder becomes lower case with hyphens: "Odd History" →
`odd-history`). Then:

```bash
content new-channel <name> [--folder <their-folder>]   # a bucket is connected by cloud setup
```

It copies the starter to `themes/<name>/` and writes `themes/<name>/config.json`. Tell them
the folder is theirs and private. Start `themes/<name>/notes/setup.md` with the date, their
one-sentence idea, and the stages ahead.

Record what they told you in stages 2 and 3 (`content spend budget …`), then show them
`content spend --config <channel>`: what they have, what is left, and that it starts at zero.

**Check:** `content check --config <channel>` shows the channel loading.

## Stage 5: The channel in words (free)

This is the most important stage: every creative agent reads the channel's `SKILL.md`. Talk
it through, in one or two rounds of questions, offering examples:

- **What stories?** True stories of what kind (history, science, crime, business, the
  everyday), and what makes one right for this channel.
- **Who is watching,** and what should they feel and think when it ends?
- **The storyteller:** who is speaking (a dry historian, a curious friend, a wry detective),
  the humour (none, dry, warm), how serious.
- **The shape** their stories usually take, and **what is off-limits** (clichés, tones,
  subjects).
- **Channels or narrators they admire,** for technique only: never copy words or style
  wholesale.

Write `themes/<name>/SKILL.md` in the starter's section order: the feeling, the visual
language, the voice, the story shape, a good and a bad example. Examples must be neutral
subjects, never a story they plan to make: examples steer every story toward themselves.
Then set `writing.voice` (one sentence; every script is judged against it),
`writing.max_weighty_lines`, and, for a slower or brisker channel, `writing.weights.role_seconds`
(`docs/theme-settings.md`, Writing). If they have a recording of a narrator they admire:
`content analyse-narration <audio> --apply --config <channel>` sets the rhythm from numbers
only.

Read the result back to them in a few lines and get a yes.

## Stage 6: The look (free to edit)

Ask about, with options:

- **The medium**, one, concretely: flat illustration, ink and watercolour, paper cut-outs,
  woodcut print, bold comic panels, painterly gouache, chalk on a blackboard… Never
  photorealistic: the models draw real people and places better, and more safely, as
  illustration.
- **The palette:** three to six colours; suggest some from their feeling.
- **Light and texture:** bright and even, moody and low, grainy print…
- **How real people are drawn** (recognisable but stylised) and what is never shown.

Then edit `palette`, `visual.style`, `visual.texture`, `visual.lighting`, `visual.figure`,
`visual.silhouette` (keep their slots), `visual.avoid` (keep photorealism and text out), and
`visual.morph` and `visual.morph_avoid`: describe the change between pictures they want to see
("ink bleeds into the next scene"); effect words ("kaleidoscope") come out literally. Style
images in `references/` are optional (2–4 images, no text or real people); they can add them
after the first video. Keep the frame out of the prompt templates' wording: they say
`{frame}` and `{orientation}`. Every setting: `docs/theme-settings.md`, "The look in words".

Tell them honestly: they will first see pictures at the first video's Pictures sign-off,
before any of the expensive moving parts are made.

## Stage 7: Movement and feeling (free)

- **How much movement:** calm (the starter), medium, or strong. Strong values for the local
  effects are in `docs/visuals.md`; set `visual.motion` from their choice. Every effect costs
  nothing: it is rendered on their computer.
- **Camera moves:** the starter's six suit most channels; add one only for a reason.
- **The emotional field:** each scene's space, light and camera follow how its lines make a
  listener react (curious, tense, repelled, at rest). Rewrite each reaction's `frame`, `light`
  and `motion` wordings in their visual language, three strengths each
  (`docs/theme-settings.md`, "The emotional field"). Only space, light, colour and motion:
  never emotion words.
- **Tone** (brightness and colourfulness targets): leave the starter's numbers until their
  first video's pictures are approved, then refit them from those (`docs/machine-learning.md`,
  colour).

Then run `.venv/bin/python -m pytest -q tests/test_theme.py`: it validates their theme.

## Stage 8: The narrator (cents; ask first)

Options, recommended first:

1. **A stock voice:** `content voice-audition --config <channel>` renders the theme's
   `voice.audition_text` in every `voice.candidates` voice, with and without direction, into
   `runs/_theme/voice-audition/` (a few cents each). They listen and pick; set `voice.model`,
   `voice.voice` and `voice.direction_style` from the one they chose.
2. **A designed voice no one else uses:** write two or three `voice.designs` (who is speaking:
   age, accent, warmth, pace), then `content voice-design --config <channel>`. Lock the chosen
   clip with `content voice-lock <clip> --model bytedance-seed/seed-audio-1-0
   --direction-style inline --config <channel>`.
3. **A real person's recording** (theirs, or a friend's): only with that person's consent.
   `content voice-lock <clip> --model … --transcript "<exactly what the clip says>" --config
   <channel>`.

Then `voice.direction` (how every passage is spoken), `voice.words_per_minute` (160 is a
brisk explainer; slower for a contemplative channel), and `voice.lexicon` for words the voice
gets wrong. `docs/narration.md` explains pace.

## Stage 9: The music (cents; ask first)

Two ways:

- **Generated for each video** from `music.prompt`: nothing more to do. Write the prompt with
  them (instruments, mood, what it must never do: vocals, a big melody that fights the voice).
- **One locked bed for every video,** like a signature: `content music-audition --config
  <channel>` renders one candidate per `music.variations`; they pick one; `content music-lock
  <track> --config <channel>` locks it and maps its beats, so stories are cut to its bars. This
  needs the `music` extra, which needs PyTorch first: `.venv/bin/pip install torch torchaudio
  --index-url https://download.pytorch.org/whl/cpu` then `.venv/bin/pip install -e '.[music]'`.

## Stage 10: Subtitles and formats (free)

- **Subtitles:** a font in `fonts/` licensed for video (the starter's is under the OFL), colours
  from their palette, size and position (`docs/theme-settings.md`, Subtitles).
- **Formats:** where they will publish. `short` (9:16, up to 3 minutes: TikTok, Reels, Shorts)
  and `long` (16:9, YouTube, with a Story plan sign-off) are ready. Remove one they will never
  make; set `format` to the usual one.

## Stage 11: Check and keep (free)

- `.venv/bin/python -m pytest -q tests/test_theme.py tests/test_rehearsal.py`: the theme is
  valid, and their channel carries a story from research to a finished package with stand-in
  models, every prompt and setting included.
- `content check --config <channel>`: everything ready.
- With a folder or bucket: `content storage save-theme --config <channel>`.
- Update `notes/setup.md`: setup done; what the channel is, in their words; what to revisit
  after the first video (tone, references, motion).

## Stage 12: The first video

Follow the `make-video` skill: one round of questions (format, length, scenes, angle, with
costs), then the sign-offs. On the first video, read every sign-off with them for the
channel's taste as well as the story's, and fold what they say about the channel into its
`SKILL.md` or `theme.json`, never into the run. A note about one story stays in that run.
After the Pictures sign-off is approved, refit `visual.tone` from the approved pictures.

Afterwards, tell them how to carry on: open Claude Code in the project folder and say what
they want ("make a video about…", "change the narrator's pace", "set up a new computer").

## Done when

- `content check --config <channel>` says ready, and the theme and rehearsal tests pass.
- `SKILL.md` describes their channel and has no real story from their plans in it.
- The voice and music are locked, or deliberately left to presets and generation.
- `themes/<name>/notes/setup.md` records what was decided and why.
- With a folder or bucket, the channel is saved (`content storage show themes/<name> --config …`).
- They know how to start the next video, and that the folder is private and never committed.
