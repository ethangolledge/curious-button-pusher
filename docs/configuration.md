# Configuration: Every Key

A configuration file chooses the models, the theme, the limits and the review points for a run.
It never holds style (that is the theme, [themes.md](themes.md)) or secrets (the OpenRouter key is
in `.env`). Loaded by `config.py`; pass one with `--config`.

Last reviewed: 2026-10-12.

## The Four Files

| File | Theme | Providers | Use |
|---|---|---|---|
| `config/config.json` | starter | fake text and Jev, no `production` | the offline demo, text only; the default |
| `config/config.fake-video.json` | starter | fake text, Jev and media (local ffmpeg) | the whole pipeline offline |
| `config/config.example.json` | starter | OpenRouter | the template a new channel's configuration is made from |
| `themes/<name>/config.json` | your channel | OpenRouter | your channel's real runs (private, with the channel) |

The offline files skip the Script sign-off and accept provisional research, so demos and tests
run unattended. `content new-channel <name>` writes `themes/<name>/config.json` from
`config.example.json`, pointing `theme` and `learning.directory` at the new theme (and adding
`storage` with `--folder` or `--bucket`). Paths in a configuration are relative to the project root, wherever
the file lives.

Required sections are checked on load, and so are the question names in `decisions.blocking`
and `learning.local_questions`; any other unknown key is ignored. Paths resolve from the project
root.

## `application`, `theme`, `content`

| Key | Meaning |
|---|---|
| `application.name` | the application's name in logs |
| `application.output_directory` | where run folders go (`runs`); theme tools write to `runs/_theme/<tool>/` |
| `application.logging_level` | Python logging level (`INFO`) |
| `theme` | the theme folder, e.g. `themes/starter` |
| `content.default_duration_seconds` | the length preference when `--seconds` is not given, kept within the video's format; the story's own size wins ([narration.md](narration.md#1-planning-the-length)). Format, length, scenes and cap per video are run choices, not configuration ([runs-and-review.md](runs-and-review.md#one-channel-several-shapes-of-video)) |

## `models` and `agents`

`models` defines aliases; agents and other settings refer to aliases, never to models.

| Key | Meaning |
|---|---|
| `models.<alias>.provider` | `openrouter`, or `fake` for the deterministic demo |
| `models.<alias>.model` | the OpenRouter model ID |
| `models.<alias>.effort` | reasoning effort: `none`, `minimal`, `low`, `medium`, `high`, `xhigh` |
| `models.<alias>.max_output_tokens` | a ceiling, not a target (32k on the real config: script revisions have used 27k) |
| `agents.<agent>.model` | the alias each of the five agents uses (all five must be present) |
| `agents.<agent>.prompt` | its `prompt.md` (its other jobs' prompts sit beside it: `critic_prompt.md`, `listener_prompt.md`, `line_edit_prompt.md`) |
| `agents.editorial_director.listener_model` | the alias of the cold viewer, the first-time listener; a different model family from the writer (`listener`: `google/gemini-3.8-flash`). Unset (the offline configs), the Editorial Director's own model listens. Must use the same provider as the agent |
| `agents.script_writer.edit_model` | the alias for line edits, a revision confined to a few named lines (`editor`: `anthropic/claude-haiku-4.5`, effort low). Unset (the offline configs), the writer's own model edits lines. A line it edited that comes back from the next check is edited by the writer's model |
| `agents.editorial_director.critic_model` | the alias the critic and director-note sorting run on (`writer`, Sonnet, in the real config): findings on a finished piece, not authorship. Unset, the agent's own model critiques |
| `agents.fact_checker.light_model` | the alias for auditing three or fewer changed lines (`auditor_light`: the auditor at medium effort). Any finding it returns is audited again on the agent's own model. Unset, every audit is full |

The real configuration's aliases: `architect` (the plan, the critic and story decisions),
`writer` (script, storyboard, the learning teacher), `auditor` (research and the fact check, a
different model family from the writer), `listener` (the cold viewer, a third family). Current models and prices: [models.md](models.md).

## `workflow`

| Key | Meaning |
|---|---|
| `allow_provisional_research` | `true`: research resting partly on allegation or weak sourcing continues; `false` (real): it stops at a research review |
| `review_plan` | stop for a person at the creative plan (off; Jev and the critic judge it) |
| `review_script` | the Script sign-off before narration is paid for (on in real runs) |
| `workflow.max_revisions.research`, `workflow.max_revisions.script`, `workflow.max_revisions.visuals` | automatic revisions each stage may make before the run asks a person; the script's also covers oral revisions after the listener test |

## `decisions` (Jev)

| Key | Meaning |
|---|---|
| `provider`, `model` | `openrouter` and `typesafe/jev-1.13` (pinned) |
| `decisions.thresholds.yes_min` | a yes/no answer passes at or above this probability of yes (0.6 real) |
| `decisions.thresholds.no_max` | and fails at or below it (0.2) |
| `decisions.thresholds.act_min` | choices and scores below this confidence are unsure (0.5) |
| `blocking` | the questions whose failures route the graph; the rest are advice ([architecture.md](architecture.md#how-judgements-become-routes)) |

## `production` (omit it to stop at the prompt package)

| Key | Meaning |
|---|---|
| `provider` | `openrouter`, or `fake` (colour stills and tones by ffmpeg, at the theme's neutral tone) |
| `pictures` | how scenes are pictured: `keyframes` (each scene an image model's still, moved by ffmpeg; the starter's default), `staged` (each scene the toolkit can show is a 3D shot built and rendered in Blender, free; the rest stay keyframes) or `animated` (each keyframe drawn and judged as usual, then lifted into depth and moved in Blender as itself: a real camera move with parallax, its people breathing; free, needs the `vision` extra: [picture-shots.md](picture-shots.md)). Morphs, breathing, the feeling's colour and the texture are the same either way ([staging.md](staging.md)). Staged needs Blender 5.2 (`BLENDER`, or on the path) |
| `joins` | how one scene turns into the next: `ai` (the video model morphs between the two pictures, about $0.17 a join; the default) or `rendered` (a transition drawn in Blender from the two pictures, free: flowing, rushing through, spiralling in… chosen per join by the storyboard or by the theme's `staging.joins`). Works with either `pictures`; needs Blender ([staging.md](staging.md#transitions-morphs-drawn-in-blender)) |
| `cache_directory` | the paid-asset cache (`.cache`); deleting it means paying again |
| `image_model`, `image_resolution` | keyframes |
| `video_model`, `video_resolution`, `video_durations`, `transition_seconds` | morphs: lengths the model accepts, and the one used |
| `max_usd` | the run's cap; lowered to the key's remaining credit |
| `image_usd`, `video_usd_per_second` | the prices the budget projects with |
| `transcription_model` | word timestamps for timing, subtitles and listen checks |
| `music_model` | music generated per video when the theme has no locked bed (`null`: none) |
| `vision_model` | describes renders and reference candidates for Jev |
| `seed` | the image and video seed; each retry adds its attempt number |
| `keyframe_attempts`, `segment_attempts` | renders allowed per keyframe or morph, the first included |
| `hard_cut_threshold` | ffmpeg scene-change score above which a morph frame counts as a jump |
| `reference_candidates`, `references_per_request`, `min_reference_side` | reference photos judged per request, used per keyframe, and the smallest usable side in pixels |

## `learning` (omit it to send every judgement to Jev)

| Key | Meaning |
|---|---|
| `directory` | the channel's taste data; keep it inside the theme |
| `embedder` | the sentence-embedding model (`BAAI/bge-small-en-v1.5`, local) |
| `local_questions` | questions a trained local model may take over; factual ones stay with Jev |
| `teacher` | the alias that labels examples during `train --budget` |
| `min_labels` | labels of at least two kinds a question needs before a model is trained |
| `min_gold` | a person's labels needed before a model can be compared with Jev |
| `nli_model` | the local contradiction check before the fact check (`null`: skipped) |

Details: [machine-learning.md](machine-learning.md).

## `storage` (omit it to keep everything on this machine)

Exactly one of:

| Key | Meaning |
|---|---|
| `folder` | a folder that keeps runs and the channel's theme: relative to the project root (`archive`, gitignored), or anywhere (`~/Dropbox/my-channel-archive`) |
| `bucket` | a Google Cloud Storage bucket that keeps them |

Only a channel's own configuration has it. Details, costs and setup: [storage.md](storage.md).
