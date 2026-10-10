---
name: update-docs
description: Keep the documentation true to the code. Use whenever you change the pipeline's behaviour, constants, models, prompts, the theme, configuration, the review flow, or the cache, and before committing such a change.
---

# Keeping the docs current

The docs exist so the person can optimise the pipeline later without reading the code. A doc that
is wrong is worse than none. Update the docs **in the same change** as the code.

## Which doc to update

| You changed… | Update |
|---|---|
| anything on the narration path: `story/pace.py`, `production/stages/narration.py`, `score.py`, `timing.py`, `subtitles.py`, `checks.listen_issues`, `assemble.spoken_clip`/`narration_track`/`mix_audio`, theme `voice`, `music`, `subtitles` | `docs/narration.md` (the numbers table, "What Changes What", quirks, levers) |
| the pictures: storyboard, references, keyframes, `focus.py`, `assemble.glide`/`motion_clip`/`conform_segment`/`texture`/`dissolve_join`, theme `visual` | `docs/visuals.md` (and bump `producer.LOOK` when the rendering code changes) |
| the theme schema (`theme.py`), the starter kit (`themes/starter/`), `new-channel`, a theme tool, or where taste data lives | `docs/themes.md` (the key table), `themes/starter/README.md`, `.claude/skills/new-channel/SKILL.md` |
| the pipeline's shape: agents, graph edges, judging, the authority structure, the story ledger, the listener test, the package | `docs/architecture.md` (and its diagram), and the drafting chain in `docs/narration.md` |
| a story-quality fixture or `story/regression.py` | `docs/narration.md` (Regression), `themes/starter/examples/` (the sample and its README) |
| a model, its alias, price, prompt shape, thresholds, or a Jev question | `docs/models.md` register; local or learned models also `docs/machine-learning.md` |
| the review flow, sign-offs, run folder, review page, CLI, resume, cost logging, the video's choices (`choices.py`, formats, `estimate`), or the intake questions | `docs/runs-and-review.md`, `.claude/skills/make-video/SKILL.md` |
| installing, the quick start, the docs map | `README.md` (kept short: it links out) |
| module structure, a new module or package, a design trade-off, a new quirk, a fixed quirk | `docs/codebase.md` (and `LAYERS` in `tests/test_architecture.py` for a new package) |
| a decision made after a run, or a failure that cost money | the channel's `themes/<name>/notes/` (private: the run, the problem, the fix), the general lesson in the area's doc with neutral wording, and `PROJECT_CONTEXT.md` if it changes the engine's current state |
| configuration keys or defaults (`config.py`, `config/*.json`) | `docs/configuration.md`, the doc for that area, and `config/config.example.json` |

## How to write it

- **State things once.** Each fact has one home (the table above); other docs link to it rather
  than repeat it.
- **Keep style out of the code.** How a channel looks or sounds is theme data; docs quote the
  starter's values, or say what a setting could be, never a particular channel's.
- **Keep stories out of the code.** Code comments, docstrings, agent prompts and tests
  state behaviour and the reason, with neutral examples; which run taught it goes in that
  channel's private `notes/` or `examples/`; `docs/` keeps the lesson and its numbers in neutral
  words ("a first production: predicted 167.5 s, recorded 174 s"), never the story or channel. Story examples
  in prompts bias every future story toward that one.
- State current behaviour with the real number and where it lives (file, constant, theme key).
- Every quirk gets the evidence in the docs: what was measured ("predicted 167.5 s, recorded
  174 s"), without naming the story.
- Say what a change costs (free, or the paid assets it re-makes).
- Remove what is no longer true; never leave old and new side by side. History goes in a
  channel's `notes/`, not in the current docs.
- Update the "Last reviewed" line at the top of each doc you touched.
- Plain British English, short sentences, tables for numbers. Follow the voice of the existing docs.

## Before you commit

1. `git diff --stat`: for every source file changed, is the matching doc in the list?
2. Grep the docs for any constant or name you renamed or removed.
3. Check links still resolve (`docs/README.md` lists every doc).
