# Themes: Everything That Makes a Channel Yours

A theme is a style pack. It decides how stories are told, drawn, spoken and scored, never what is
shown: everything in frame comes from the story and its reference photographs. Code holds no
style; swap the theme and the same pipeline makes a different channel.

- `themes/starter/`: a neutral, complete theme to build from. `content new-channel <name>`
  copies it to `themes/<name>/` and writes the channel's own configuration beside it,
  `themes/<name>/config.json`. Its `README.md` is the step-by-step guide.
- `themes/<your channel>/`: private. Git holds only the starter; every other theme folder is
  gitignored, and kept whole in your cloud bucket if you use one (settings, voice, music, taste
  data, configuration, notes), so the engine can be open source while your channel stays yours.
  `content storage pull` brings it back on a fresh clone ([storage.md](storage.md)).

Every theme present in `themes/` is loaded and validated by the tests (`tests/test_theme.py`).
Every single setting, with its starter value, what it does and what changing it costs, is in
[theme-settings.md](theme-settings.md); this page explains how a theme fits together.

Last reviewed: 2026-10-09.

## What a Theme Holds

```text
themes/<name>/
├── theme.json        exact values for code (below)
├── SKILL.md          the channel in words, read by every creative agent
├── README.md         optional notes for people; never read by the pipeline
├── fonts/            the subtitle font
├── voice/master.*    the locked narrator, when cloning (voice-lock writes it)
├── music/bed.*       the locked music bed and its beat map (music-lock writes them)
├── references/       optional style images for the image model
├── learning/         optional: this channel's taste data (examples, labels, models)
├── config.json       the channel's configuration (new-channel writes it; never in the starter)
├── examples/         rejected (and approved) scripts for `content eval`; the starter has a sample
└── notes/            optional: the channel's decisions and plans, for people and later sessions
```

## `SKILL.md`

Prose every creative agent receives with its own instructions: the channel's feeling, visual
language, how real people are drawn, palette, camera, pacing, and **voice** (the storyteller, its
humour, the shape its stories usually take, what counts as cliché), with good and bad examples.
Agents' own `SKILL.md` files hold only the job and the craft; everything that makes the channel
distinctive belongs here.

**Use neutral examples.** Every story is written and drawn with these examples in view: a real
story you are about to make, used as an example, steers every other story toward it.

## `theme.json`

| Key | What it sets | Read by |
|---|---|---|
| `name` | the theme's name (its folder name) | — |
| `formats` | the shapes of video the channel makes, by name (`short`, `long`): `platforms` (in words), frame size, frame rate, aspect, `frame` and `orientation` (how prompts name it: "Vertical 9:16", "vertical"), shortest and longest video (seconds), `review_plan` (a Story plan sign-off), and subtitle sizes for that frame (`subtitle_font_size`, `subtitle_max_words`, `subtitle_margin_bottom`) | everything; each video picks one (`--format`) |
| `format` | the name of the default format | |
| `palette` | named hex colours (documentation for prompts and people) | — |
| `visual.style`, `texture`, `lighting` | how pictures are drawn, in words for the image and video models | keyframes, morphs |
| `visual.morph` | what happens during a morph, in words for the video model | morphs |
| `visual.camera_moves` | each move: `describe` (for the video model) and its glide (`start`, `end`: zoom, how far toward the frame's centre, x/y offset) | storyboard, stills, morphs |
| `visual.motion` | the free local effects: `breath` (swell, seconds, ripples, and `tint`: how strongly the ripples take the scene's emotional colour), `morph` (warp, trails, mirror, plate shift, hue, saturation), `texture` (fractal, vignette swing, fringe, grain, flicker), `dissolve_seconds`; 0 switches a layer off | assembly |
| `visual.figure`, `visual.silhouette` | how a public figure is drawn, and as a silhouette when a portrait is refused | keyframes, morphs |
| `visual.avoid`, `morph_avoid` | what stills and morphs must never contain | keyframes, morphs |
| `visual.tone` | brightness and saturation the pictures aim for (`neutral`, `per_unit`, `tolerance`), ceilings, and the redraw notes (darker, lighter, richer) | keyframe checks |
| `visual.field` | how each emotional reaction (lean in, brace, recoil, settle) frames, lights and moves a scene at three strengths, its circumplex point, its `ripple_colour`, and which camera moves suit it; transition and speed phrases | keyframes, morphs, storyboard |
| `visual.reference_note` | how reference photographs may be used | keyframes |
| `visual.keyframe_template`, `segment_template`, `final_segment_template` | the prompt templates (slots are validated at load; `{frame}` and `{orientation}` come from the video's format, so one template serves every shape) | keyframes, morphs |
| `references` | style images sent with every keyframe | keyframes |
| `writing.voice` | one sentence: how the narration should sound; scripts are judged against it | Jev |
| `writing.max_weighty_lines` | how many solemn lines a script may carry | script checks |
| `writing.rhythm` | sentence-length profile to aim for (from `analyse-narration`) | writer |
| `writing.weights` | the open story weights, and the seconds each story role may take (`role_seconds`, `transition_seconds`, `beat_floor_seconds`) | plan, time per beat |
| `voice` | the narrator: model, preset voice or cloned `reference_audio`, a fallback `direction` (each script directs its own passages), pace (`words_per_minute` the target, `hook_pace`, `tempo_range`, `retakes`), breaths, tail, length tolerance, lexicon, audition candidates and voice designs. Scripts are sized at the pace the voice is measured to deliver, from `learning/narration.jsonl` | narration ([narration.md](narration.md)) |
| `subtitles` | font, size, colours, outline, phrase length, case, position | finish |
| `music` | locked `track` (or none: generated per video from `prompt`), audition `variations`, level under the voice, ducking, loudness target | mix |

The theme guidance every agent receives is built from `SKILL.md`, the camera moves, which moves
suit each reaction, and the rhythm (`theme.theme_guidance`).

## Tools

| Command | Does | Costs |
|---|---|---|
| `content new-channel <name>` | copies the starter to `themes/<name>` | free |
| `content voice-audition` | renders the audition passage with every candidate voice, with and without direction | cents |
| `content voice-design` | renders each `voice.designs` description as a candidate narrator | cents |
| `content voice-lock <clip> --model … --direction-style …` | saves the chosen clip as `voice/master.*` and points narration at a cloning model; a real person's voice only with consent (`--transcript`) | free |
| `content music-audition` | renders one bed per `music.variations` prompt | cents |
| `content music-lock <track>` | copies the track in, maps beats and four-bar phrases with Beat This!, lists every possible edit length, renders a voice-over preview | free (needs the `music` extra) |
| `content music-map` | re-maps the locked track | free |
| `content analyse-narration <audio> --apply` | measures a narrator you admire (rate, pauses, sentence lengths, questions) and sets `writing.rhythm`; numbers only, never their words | free |

All take `--config`; theme tool output goes to `runs/_theme/<tool>/`.

## A Theme's Taste Data

`learning.directory` in the configuration says where a channel's examples, labels and trained
taste models live; keeping it inside the theme (`themes/<name>/learning`) means a fork of the
code starts with no one's taste, and a channel's taste travels with its theme.
