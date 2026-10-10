# Documentation

**New to the project (a person or an assistant)?** Read in this order: `../AGENTS.md` (the
rules), `../PROJECT_CONTEXT.md` (where things stand), [architecture.md](architecture.md) (how a
story becomes a video), [codebase.md](codebase.md) (every file, constant and quirk), then the
doc for the area you are changing. To build a channel, the `new-channel` skill; to run a video,
the `make-video` skill.

Otherwise, start with the one you need:

| I want to… | Read |
|---|---|
| set everything up from nothing and make my first video, without coding | [getting-started.md](getting-started.md) |
| understand how a story becomes a video: the pipeline, agents, judging, research standard | [architecture.md](architecture.md) |
| make my own channel: the look, voice, music and taste a theme holds | [themes.md](themes.md) |
| know exactly what one channel setting does, its starter value, and what changing it costs | [theme-settings.md](theme-settings.md) |
| set up Google Cloud from nothing, to keep my channel and videos safe | [google-cloud.md](google-cloud.md) |
| know what a configuration key does, or which config file to use | [configuration.md](configuration.md) |
| check that the pipeline still catches the narration failures a person found (`content eval`) | [narration.md](narration.md#regression-content-eval) |
| run a video, or understand the sign-offs and the run folder | [runs-and-review.md](runs-and-review.md) |
| keep my channel and finished videos in a cloud bucket, with their history, and get them back | [storage.md](storage.md) |
| understand or tune the narration (pace, takes, timing, music, mix) | [narration.md](narration.md) |
| understand or tune the pictures (storyboard, keyframes, focus, glide, morphs, texture) | [visuals.md](visuals.md) |
| know what any model does, costs, and how it fails (Jev, the LLMs, media models, local models) | [models.md](models.md) |
| go deep on the local and learned models (taste models, colour, NLI, beat tracking) | [machine-learning.md](machine-learning.md) |
| find my way around the code, its trade-offs and quirks, and where to optimise | [codebase.md](codebase.md) |

Also:

- `../PROJECT_CONTEXT.md`: the current state and open decisions, kept short.
- `../README.md`: what it is, installing, the first run.
- `../AGENTS.md`: the rules for changing the code.
- `../.claude/skills/make-video/SKILL.md`: how an assistant runs a video with the director.
- `../.claude/skills/new-channel/SKILL.md`: how an assistant builds a new channel from the
  starter with a person.
- `../.claude/skills/update-docs/SKILL.md`: which doc to update when the code changes.

Every doc says when it was last reviewed. If you change behaviour, update the doc in the same
change.
