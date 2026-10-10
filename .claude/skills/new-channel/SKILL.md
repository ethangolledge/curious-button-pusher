---
name: new-channel
description: Build a new channel (its theme and configuration) from the starter kit with the person, from a fresh clone to a first finished video. Use when the repository has no channel yet (themes/ holds only starter), when someone forks it, wants their own look, voice, music or storytelling voice, asks to "start from scratch", or wants to change what makes an existing channel distinctive.
---

# Building a channel from the starter

A channel is a folder: `themes/<name>/` holds its look, motion, narrator, music, writing voice,
taste data and its own configuration (`config.json`). The engine in `src/` never changes for a
new channel. Every setting is listed in `docs/themes.md`; configuration keys in
`docs/configuration.md`. The starter (`themes/starter/`) describes what each setting could be;
the person's answers decide what it is.

The person decides taste; you do the editing. Ask what they want the channel to feel like, show
them options, write the theme from their answers, and get a yes before anything that costs money
(auditions and the first run).

## 0. Where the channel lives

The channel folder is private to the person: gitignored, never committed (only `themes/starter`
is shared). If they want it safe beyond this machine, with every earlier version restorable,
they keep it in their own Google Cloud Storage bucket (`docs/storage.md`, "Setting it up"); ask
whether they have one before step 1.

## 1. Set up (free)

```bash
python -m venv .venv && .venv/bin/pip install -e '.[dev,live]'   # needs ffmpeg
cp .env.example .env                                              # the person pastes their OpenRouter key
.venv/bin/content new-channel <name> [--bucket <their-bucket>]    # the theme and its config.json
```

`new-channel` copies `themes/starter` to `themes/<name>/` and writes `themes/<name>/config.json`
from `config/config.example.json`, pointed at the theme and its taste data (and the bucket).
Use `--config themes/<name>/config.json` for every command below. To try the theme offline while
editing, copy `config/config.fake-video.json` into the channel folder and set its `"theme"`.

## 2. The channel in words (free)

Talk it through with the person, then write `themes/<name>/SKILL.md`. Every creative agent
reads it. Cover, in the starter's section order:

- **The feeling** the viewer should leave with.
- **Visual language:** the medium (one, concretely: "flat paper cut-outs", "ink and watercolour"),
  the palette, how real people are drawn, what is never shown.
- **The theme is a way of drawing, never a subject;** every scene's anchor comes from the story.
- **Pacing** and **voice**: who the storyteller is, the humour, the shape stories usually take,
  what counts as cliché.
- **Good and bad examples** in neutral subjects. Never use a story they plan to make: examples
  steer every story toward themselves.

Then `theme.json` → `writing.voice`: one sentence; Jev judges every script against it. The
starter's `writing.weights.role_seconds` (how long a spine claim, context, evidence, or colour
may take) suit most channels; slow them for a contemplative channel, quicken them for a brisk
one.

## 3. The look (free to edit; pictures cost only in a run)

In `theme.json` → `visual` (meanings in `docs/themes.md` and `docs/visuals.md`):

1. `style`, `texture`, `lighting`: the medium in words an image model follows, technique names
   only (never artists or franchises). `avoid` and `morph_avoid` keep photorealism and text out.
2. `figure` and `silhouette`: how a public figure is drawn, and the fallback when a portrait is
   refused. Keep their slots (`{subject}`, `{name}`, `{likeness}`, `{silhouette}`).
3. `morph`: describe the change you want to see between pictures (melting, one shape becoming
   another). Video models follow it literally; effect words ("kaleidoscope", "hallucinatory")
   give exactly that.
4. `camera_moves` and `motion`: glides, breathing, the morph layer and the texture pass. 0
   switches an effect off; the starter is calm, and `docs/visuals.md` gives strong values for
   comparison.
5. `tone`: how bright and saturated pictures should be. Leave the starter's numbers until a first
   run's keyframes have been approved, then refit them (`docs/machine-learning.md`, colour).
6. `palette` and `subtitles` (font in `fonts/`, colours, position).
7. `formats`: the shapes of video the channel makes (the starter has `short`, 9:16, and `long`,
   16:9 with a Story plan sign-off), each with its size, shortest and longest video, how
   prompts name the frame (`frame`, `orientation`), and subtitle sizes for that frame; `format`
   names the default. Ask the person which platforms they make for; a format they never use can
   go. Keep the frame out of the prompt templates' wording: they say `{frame}` and
   `{orientation}`.

Check it loads after every edit: `.venv/bin/python -m pytest -q tests/test_theme.py`.

## 4. The narrator (cents; ask first)

- `voice-audition` renders the theme's `audition_text` in every `voice.candidates` voice, with and
  without direction, into `runs/_theme/voice-audition/`. The person listens and picks.
- Or `voice-design` renders each description in `voice.designs` as a new voice.
- A stock voice: set `voice.model`, `voice.voice` and `direction_style`. A designed or recorded
  voice: `voice-lock <clip> --model <cloning model> --direction-style …` saves `voice/master.*` and
  points the theme at it. A real person's voice only with their consent (`--transcript`).
- Pace is set, not predicted (`words_per_minute`, `docs/narration.md`). To match a narrator they
  admire, `analyse-narration <audio> --apply` sets `writing.rhythm` from numbers only.

## 5. The music (cents; ask first)

- `music-audition` renders one bed per `music.variations` prompt. The person picks one.
- `music-lock <track>` copies it into the theme and maps its beats and phrases (needs the `music`
  extra), so stories are cut to its bars. Without a locked bed, music is generated per video
  from `music.prompt`.

## 6. The first run

Follow the `make-video` skill: the intake questions, then the sign-offs. On the first video, read every
sign-off with them for the channel's taste as well as the story's, and fold what they say into
the theme's `SKILL.md` or `theme.json`, not into the run. A note on one story stays in that run.

## Done when

- `tests/test_theme.py` passes, and the offline demo runs on the theme.
- `SKILL.md` has no real story from their plans in it.
- The voice and music are locked, or deliberately left to presets and generation.
- The channel's decisions so far are in `themes/<name>/notes/` (what it is, why it looks and
  sounds that way), so a later session can pick it up; a rejected script with its failures
  named goes in `themes/<name>/examples/` (format: `themes/starter/examples/README.md`).
- The theme folder is private: gitignored, never committed. With a `storage` section it is
  saved to the bucket after every change; run `storage save-theme` after editing `theme.json`
  or `SKILL.md` by hand (`docs/storage.md`).
