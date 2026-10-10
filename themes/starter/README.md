# The Starter Theme

A complete, neutral theme to build your own channel from. It runs as it is: a clean modern
illustration look, a stock voice (no cloning needed), and generated music (no locked track).

Every value here is a neutral example of what a setting could be; your answers decide what it
is. This file is for people. The pipeline reads only `theme.json` and `SKILL.md` (and
`examples/` for `content eval`).

**The easy way:** open Claude Code in the project folder and say "help me build my channel".
It follows `.claude/skills/new-channel/SKILL.md`: the same steps as below, as a conversation,
doing the editing for you. New to all of it? Start at `docs/getting-started.md`.

Every setting in `theme.json`, with its value here, what it does, and what changing it costs:
`docs/theme-settings.md`.

## Make it yours

```bash
.venv/bin/content new-channel my-channel     # copies this folder to themes/my-channel,
                                             # with its own config.json
```

Pass `--config themes/my-channel/config.json` to every command (the theme tools need its
OpenRouter models); `docs/configuration.md` explains every key. Your channel folder is private:
gitignored, never committed. Then edit, in this order:

1. **`SKILL.md`: your channel in words.** Every agent reads it. Describe the feeling, the visual
   language, the voice, and the shape your stories usually take, with a good and a bad example.
   Use neutral examples, not a real story you are about to make: examples steer every story.
2. **`theme.json` → `writing.voice`:** one sentence on how the narration should sound. Scripts
   are judged against it. `writing.weights.role_seconds` sets how long the story's central claims,
   context, evidence and colour may take (`docs/narration.md`, "Time by story role").
3. **`theme.json` → `visual`:** the look the image and video models are told (`style`,
   `texture`, `lighting`, `morph`, the prompt templates, `figure` and `silhouette` for how
   people are drawn, and the `avoid` lists), the camera moves with their glides, and `motion`
   for the free local effects (breathing stills, the morph layer, the texture pass; set a value
   to 0 to switch it off). `docs/visuals.md` explains every setting.
4. **`theme.json` → `visual.tone` and `visual.field`:** the brightness and colour the pictures
   aim for, and how each emotional reaction frames, lights and moves a scene.
5. **The voice.** Audition the candidate voices with `voice-audition`, or design your own with
   `voice-design`, then lock one with `voice-lock` (it saves `voice/master.wav` here and points
   the theme at it). `docs/narration.md` explains pace and delivery.
6. **The music.** Generate candidate beds with `music-audition`, then `music-lock` one (it saves
   `music/bed.mp3` and maps its beats). Without a locked bed, music is generated per video.
7. **`subtitles`:** font, size, colours and position. Fonts live in `fonts/`.
8. **`formats`:** the shapes of video you make. `short` (9:16, up to 3 minutes) and `long`
   (16:9, with a Story plan sign-off) are ready; each video picks one with `--format`, and each
   format sets its own subtitle sizes. `format` names the default. Remove one you never make.
9. **`examples/`:** a made-up sample of a rejected script for `content eval`; replace it with
   your own channel's once a director has rejected one (`examples/README.md`).
10. **Notes and safe keeping.** Write your channel's decisions in `notes/` so a later session can
    pick them up. To keep the whole folder safe beyond this machine, with every earlier version,
    and every video at each sign-off, give it a Google Cloud bucket (`docs/google-cloud.md`):
    make a project with billing and sign in twice (`gcloud auth login`,
    `gcloud auth application-default login`), then one command does the rest, safe to run
    again:

    ```bash
    .venv/bin/pip install -e '.[cloud]'
    .venv/bin/content cloud setup --bucket my-channel-videos-2026 --config themes/my-channel/config.json
    ```

    From then on the channel is saved after every change, and
    `content storage pull --bucket <bucket> --channel my-channel` brings it back on a fresh
    clone.
11. **What you have and what you spend.** Every paid call is recorded in your channel's
    `spend.sqlite`; `content spend --config themes/my-channel/config.json` shows what this
    channel has spent (by video and stage), what is left on your OpenRouter account, Google
    Cloud storage against its free 5 GB, and warnings before a balance or key runs out
    (`docs/spending.md`).

Check it is all ready: `content check --config themes/my-channel/config.json` lists what is
set up and what to do about anything that is not. Check the theme itself: run the offline demo
with it (a copy of `config/config.fake-video.json` in your channel folder, with `"theme"` set
to it), and the theme tests (`pytest tests/test_theme.py`), which validate every theme in
`themes/`.
