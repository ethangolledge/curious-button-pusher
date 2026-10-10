# Repository Guidance

## Start here

This repository is an engine (`src/content/`) and a starter kit (`themes/starter/`). A person's
channel lives in its own folder, `themes/<name>/`, which is private: gitignored, and kept in their
cloud bucket if they use one. First work out which case you are in:

1. **No channel yet** (`themes/` holds only `starter`): help the person build one. Follow
   `.claude/skills/new-channel/SKILL.md`; it starts with `content new-channel <name>`.
2. **A channel is named but missing** (a fresh clone): ask for their bucket and channel name and
   run `content storage pull --bucket <bucket> --channel <name>` (`docs/storage.md`).
3. **A channel is present** (`themes/<name>/config.json`): read `PROJECT_CONTEXT.md`, then the
   channel's own notes if it has them (`themes/<name>/notes/`). To run or review a video, follow
   `.claude/skills/make-video/SKILL.md`, passing `--config themes/<name>/config.json`.

## Rules

- At the start of a new session, read `PROJECT_CONTEXT.md` before making changes.
- The person is the director and signs off before money is spent; the assistant handles the details.
- Keep `PROJECT_CONTEXT.md` current after material architectural or product decisions; never add
  secrets. A channel's own state and decisions go in its `notes/`, not here.
- Never commit a channel folder (only `themes/starter` is shared). After editing a channel's
  `theme.json` or `SKILL.md` by hand, run `content storage save-theme` if it has a bucket.
- This is a learning project.
- Readability is more important than theoretical scalability.
- Do not add integrations unless explicitly requested.
- Keep the five agent responsibilities separate.
- Keep graph topology centralised.
- Keep runtime instructions in each agent's prompt files (`prompt.md`, `<job>_prompt.md`).
- Keep dependencies pointing one way down the layers in `tests/test_architecture.py`; a part that
  needs something from a higher layer is in the wrong place.
- Do not add production infrastructure.
- Do not convert configuration into executable architecture.
- Tests must be deterministic.
- Significant architectural changes must be explained first.
- Do not leave dead code or speculative extension points.
- Prefer deleting unnecessary code over preserving it.
- Keep the engine, the starter kit, prompts, tests and `docs/` free of any specific story or
  channel: describe what a setting could be, with neutral examples. Examples and evidence from a
  channel's real runs belong in that channel's folder (`themes/<name>/examples/`, `notes/`).
