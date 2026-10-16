# The Codebase: Map, Trade-offs and Quirks

A guide for changing the code: where things live, why they are shaped as they are, what each
choice costs, and where to optimise. Rules for contributors are in `AGENTS.md`; the current
design is in [architecture.md](architecture.md); models are in [models.md](models.md).

Last reviewed: 2026-10-11. About 28,000 lines of Python in `src/content`, about 380 tests (`pytest`, 20 s) and 12 whole-video renders (`pytest -m video`).

**Code holds no style and no story.** Every look, voice, camera move, local effect, prompt
template and taste threshold is theme data ([themes.md](themes.md)); every story lives in a run
folder or in a channel's own `examples/`. A literal that describes how a particular channel looks or sounds
belongs in a theme, not in `src/`.

## The Shape of It

Packages are layers: each imports only from the ones above it in this list, never below
(`tests/test_architecture.py` enforces it, and that there are no import cycles).

```text
blender/      3D shots: what runs inside Blender (the Stage verbs, blocks, looks); imports nothing else
schemas/      the data every part passes around (research, plan, script, review, media…)
errors.py, models.py
providers/    the paid models and outside services (OpenRouter, Wikimedia, Blender), and their stand-ins
state.py      the run's state and the record of every call
judging/      Jev: the question bank, answer → outcome → verdict, the judge
theme.py, config.py
staging/      3D shots from the pipeline's side: the catalogue, the model library, the shot check
choices.py
story/        the story's maths and checks, in code (ledger, weights, pace, prose, field, notes)
agents/       the roles that write: one folder each, agent.py + prompt.md (+ <job>_prompt.md)
production/   from storyboard to finished cut: five stages on one shared studio
learning/     the taste models that learn from a person's decisions
review/       the person's side: the file reviewer, sign-off cards, the run folder, the page
storage.py    permanent storage: the person's folder or bucket
workflow/     the graph (the only topology), routing, gates, review requests, running a run
cli/          one module per command group
__main__.py   dispatch only
```

A change stays inside its layer: a new Jev question is `judging/questions.py`; a new prompt is
an agent's `.md`; a new production step is a stage in `production/stages/` wired in
`workflow/graph.py`.

## Modules, One Line Each

Every file in `src/content`.

### Data, configuration and state

| Module | Owns | Notes |
|---|---|---|
| `schemas/` | every record that crosses a boundary, one module per subject: `research`, `plan` (the story ledger), `script`, `fact_check`, `audience`, `judgement` (Jev's answers, the critic), `perception`, `visuals`, `references`, `media`, `package` (the final package and the resume file), `review`, `story` (the shared vocabulary), `staging` (a staged scene's 3D shot) | Frozen, `extra="forbid"`; depends on nothing else |
| `errors.py` | `ConfigurationError`, `InputError`: what is reported before any model is called | |
| `models.py` | `ModelConfig` and the alias registry | Agents name aliases, never models |
| `config.py` | `ContentConfig` from JSON: models, agents (each with its `prompt`), decisions, workflow, production, learning, theme, storage; `write_channel_config` for `new-channel` | Required sections are checked; question names in `decisions.blocking` and `learning.local_questions` must exist |
| `choices.py` | one video's format, length, scenes and cap (`RunChoices`, saved in `.work/choices.json`), and `configure_run` | The theme's look, voice and music never change per video |
| `theme.py` | `Theme` and its spec, prompt building, spoken text, `new_theme` | `themes/<name>/theme.json` is the data |
| `state.py` | the graph state (`ContentState`), its reducers, `CallRecord` and `call_record` | Judgements, decisions, calls and events append; assets merge per key; everything else replaces |
| `spend.py` | the channel's spending ledger (`spend.sqlite`): every paid call, what the person said they have, each provider's own figures, and the calibration between them | Plain SQL; calls no provider ([spending.md](spending.md)) |
| `storage.py` | the archive (a folder, `LocalStore`, or a bucket, `GcsStore`): runs in progress and finished under their own names (finishing moves a run, never keeping both), and the channel folder by hash, with every version | [storage.md](storage.md) |

### 3D shots (`blender/`, `staging/`)

[staging.md](staging.md) explains them. `blender/` runs inside Blender (its own Python), so it
imports nothing from the rest of `content`; only the files marked † use Blender's API.

| Module | Owns |
|---|---|
| `blender/job.py` | the job: everything one shot needs, as JSON; the whole contract between the two sides |
| `blender/api.py` | `Stage`: every verb a block may use, and `Box`, `Pose`, `Mark` |
| `blender/bookkeeping.py` | what every stage keeps alike: the shot's length and shape, seeded randomness, marks, paths and actors by name |
| `blender/materials.py` | each surface role's everyday colour, and the role an imported surface is nearest to |
| `blender/maths.py` | vectors, rotations, easing, curves (line, arc, spline, constant-speed), turn limits, drift |
| `blender/canvas_api.py`, `patterns.py` | `Canvas`: the verbs a transition's per-pixel program uses; the patterns transitions share (polar coordinates, turning, mirrored wedges, the Droste spiral) |
| `blender/canvas.py` † | `Canvas` built as a GPU shader on a plane filling an orthographic camera; moving pictures as image sequences |
| `blender/camera.py`, `motion.py`, `sets.py`, `shapes.py`, `shapes_figure.py`, `lighting.py` | what blocks share: framing and keeping inside the set; travel and finding things; room shells; legs, slabs and drawers; light sources and flicker |
| `blender/blocks/` | one block per file, a folder per kind (`base.py`: what a block is, reading settings) |
| `blender/registry.py`, `direct.py` | finding blocks by folder; building a shot in its one order |
| `blender/rehearsal.py` | a `Stage` and a `Canvas` without Blender: checks shots and tests blocks and transitions |
| `blender/stage.py` †, `worker.py` †, `audit.py` †, `ingest.py` †, `imports.py` † | the foundation (every surface drawn in its role; families made with settings; models stretched to fit); the runner of shot and join jobs; the checks before rendering (the camera, the view, things passing into each other); preparing a downloaded model or character; reading a model file the one way both use |
| `blender/person.py` †, `generate.py` † | scripts Blender (or Infinigen's Python) runs: a person made from one parametric body, posed and moving by code; one object from an Infinigen generator |
| `staging/catalogue.py` | the blocks and models, described; the shot check |
| `staging/library.py` | the model library: search by meaning, no duplicates, versions of a model, a model as Blender needs it, credits, keep and veto |
| `staging/store.py` | where the library is kept: SQLite (models, lineage, usage) and files by their hash |
| `staging/designs.py` | the channel's designs: each recurring person, place or object drawn once and reused ([3d-reuse.md](3d-reuse.md#designs)); the free checks before the GPU; their 3D models in one SAM 3D job per kind |
| `staging/compose.py` | a scene's description to a shot: the room built, every copy placed by its relation clear of everything, background detail, actions for every copy |
| `staging/resolve.py` | what each thing is drawn with: the library, families from its words, people made, then found online; its looks as paint, its size as a fit |
| `staging/people.py` | people made to a description, once, and kept |
| `staging/sourcing.py` | where models come from: every source searched, the best prepared and drawn, scored, one taken with its rights and lineage |
| `staging/scoring.py` | how sure a candidate is the thing, by eye: CLIP against everyday others |
| `staging/templates.py` | the starting file for a new block of each kind |
| `staging/plan.py` | a staged scene to a render job (composed, in the theme's look, moves and frame); the storyboard's shot check; drawing a scene instead |
| `staging/backlog.py` | what scenes could not be staged for, kept in the channel's folder |

### Providers (`providers/`)

| Module | Owns | Notes |
|---|---|---|
| `base.py` | `ModelProvider` (System 2), `DecisionProvider` (System 1), `Usage` | The only interfaces agents see |
| `openrouter.py` | chat models through the OpenAI SDK, Jev through the Decisions API, `key_credit_remaining` | The only provider-specific text code |
| `images.py` | `ImageSource`: Wikimedia Commons, and a fake source | Add a source here |
| `assets.py` | `AssetSource`: free 3D models from Sketchfab, Poly Pizza, Gazebo Fuel and the Smithsonian; which licences are allowed (CC0, public domain, own; CC BY with credit) | |
| `infinigen.py`, `objaverse.py` | objects made by Infinigen (in its own environment); Objaverse searched in a local index of its metadata and quality scores | |
| `sources.py` | every model source, in the order a missing thing is looked for | Add a model source here |
| `ffmpeg.py` | running ffmpeg and ffprobe | Used by production, the review and the 3D tools |
| `blender.py` | running Blender on a job (`LocalBlender`: render, ingest, make a person), installing what people need, and `FakeBlender` | Blender is found from `BLENDER` or the path |
| `sam3d.py` | `make`: pictures to the SAM 3D work bucket, one run of the `sam3d-run` Cloud Run GPU job over all of them, results back into a folder | The container is `cloud/sam3d/` (its README); `content cloud sam3d` runs one picture |
| `http.py` | the shared wait-and-retry for rate-limited outside services | |
| `fake.py` | deterministic providers that record every call | The rehearsal and tests use them |
| `cache.py` | `AssetCache.fetch`: request → file, refusals remembered, one `INDEX.csv` line per paid item | Media and text alike; keys are hashes of the full request |

### Judging (`judging/`)

| Module | Owns | Notes |
|---|---|---|
| `questions.py` | Jev's questions: target, fields read, answer kind, correction line | Code, not prose: IDs and answer types are contracts |
| `outcomes.py` | answer → outcome → verdict, correction lines, which judgements are current; `DecisionConfig` (the thresholds) | Pure |
| `judge.py` | `Judge`: one Jev batch per story node or connection; `JudgementTask` | Used by the graph and by production |

### Story (`story/`)

| Module | Owns | Notes |
|---|---|---|
| `ledger.py` | story-graph structure checks; one `JudgementTask` per node or edge; the listener's findings on their lines; applying story decisions | Each task sends only the fields its questions name |
| `weights.py` | claim weights (evidence × worth × connection), telling and stance advice, words per beat by story role | Bands in theme `writing.weights` |
| `pace.py` | passages, word-rate estimates, length issues, word budgets | [narration.md](narration.md) |
| `story/prose.py` | robotic-writing detectors (verbless lines, overload, set-up questions, repeated endings) | Free |
| `story/faithfulness.py` | the local NLI contradiction check of each line against its claims | Advisory; `learn` extra |
| `field.py` | the emotional field per scene, transitions, colour targets (Valdez and Mehrabian) | Wording in theme `visual.field` |
| `notes.py` | reading a person's notes by target (`U3:`, `S4:`, `R2:`, `P2 [kind]:`, `feel`) | Untargeted notes go to the critic |
| `revision_scope.py` | how far a revision reaches: the lines its notes name, the person's locked lines, which judgements stand | Pure |
| `regression.py` | story-quality regression on a channel's `examples/` (`content eval`, paid) | Scoring is pure and tested free |

### Agents (`agents/`)

Each folder: `agent.py` (the code), `prompt.md` (what its model is told, theme-neutral) and one
`<job>_prompt.md` per extra job.

| Folder | Owns |
|---|---|
| `base.py` | `Agent`: its prompt (plus the theme's guidance when it shapes the look), its model, and `generate()`, one timed, recorded and cached structured call (`.cache/text/<operation>/` when the run makes video); `load_prompt` |
| `fact_researcher/` | the research pack: sources, classified claims, timeline, cast; the only web search |
| `editorial_director/agent.py` | the plan (the story ledger) and story decisions after the listener test |
| `editorial_director/critic.py` | the critic: settles Jev's doubts on a whole script or storyboard; sorts untargeted notes (`critic_prompt.md`) |
| `editorial_director/listener.py` | the cold viewer: a first-time listener given only the narration (`listener_prompt.md`) |
| `script_writer/` | the narration, whole rewrites, and line edits (`line_edit_prompt.md`, on the `edit_model`) with the person's own words put in by code |
| `fact_checker/` | the per-unit audit, incremental across revisions |
| `visual_director/` | the storyboard: scenes, anchors, focus, camera, morph bridges, reference requests |

### Production (`production/`)

| Module | Owns | Notes |
|---|---|---|
| `producer.py` | `Producer`: the five stages, each sharing the configuration, media provider, judge and cache | 40 lines |
| `studio.py` | `Studio`, what the stages share: fetching through the cache, describing frames (`perception_prompt.md`), rendering a still, the music and mix; `LOOK` | |
| `stages/references.py` | finding, judging and keeping reference photographs | |
| `stages/narration.py` | each passage recorded and paced; the scenes timed around it | |
| `stages/keyframes.py` | how many pictures the budget affords; keyframes drawn and judged; the animatic and story sheet | |
| `stages/segments.py` | the morphs, judged from sampled frames | |
| `stages/assembly.py` | the final cut | |
| `media.py` | `MediaProvider`: OpenRouter speech, images, video, vision, transcription, music; the fake one | Retries 429/5xx for about 2 minutes |
| `assemble.py` | glide, breathing, morph layer, texture, joins, held ending, mix, finish | All ffmpeg; every look value from the theme |
| `timing.py`, `score.py`, `music_map.py`, `subtitles.py`, `checks.py`, `budget.py`, `focus.py` | scene windows; fitting the narration to the music; beats and phrases; subtitles; exact media checks; prices and the cap; focal points | |
| `story_sheet.py` (+ `story_sheet.css`) | the HTML story sheet at the Pictures sign-off | |
| `audition.py`, `voice_lock.py`, `narration_analysis.py` | the channel tools: auditions, locking a voice, measuring a narrator | |

### Learning (`learning/`)

| Module | Owns |
|---|---|
| `examples.py` | every Jev judgement rebuilt from traces as an example; labels, flags, records; `LearningStore` |
| `after_run.py` | the free step after every run: harvest, labels from reviews, retraining |
| `labelling.py` | the terminal `label` queue |
| `model.py` | sentence embeddings plus logistic regression, one model per question |
| `provider.py` | `RoutedDecisionProvider`: promoted local models answer their questions, Jev the rest |
| `train.py` (+ `teacher_prompt.md`) | the budgeted teacher, training, promotion and demotion |

### Review (`review/`)

| Module | Owns | Notes |
|---|---|---|
| `reviewer.py` | the reviewer interface and the file reviewer (`request-N.json` → `response-N.json`) | Only a person's response answers a sign-off |
| `items.py` | each sign-off's cards with plain-English flags and what approving costs | |
| `run_folder.py` | the run folder: publishing, `building-blocks/`, `decisions.md`, `cost.csv`, `calls.csv` | |
| `page.py` (+ `assets/review.js`, `review.css`) | the review page | Inlined, so it is one file |
| `server.py` | the local review server (`/respond`, `/draft`), `serve`, desktop notifications | Standard library only |
| `render.py` | plain-text renderings of each stage's output | |

### Workflow (`workflow/`)

| Module | Owns | Notes |
|---|---|---|
| `graph.py` | every node and edge, nothing else | The only topology |
| `routing.py` | every conditional edge | |
| `gates.py` | code-only nodes: plan sizing, script and visual checks, verdicts | Free |
| `review_requests.py` | what each stop shows; the Start request with its estimate | |
| `director_notes.py` | acting on a person's story-sheet notes | |
| `final_package.py` | the last node | |
| `run.py` | starting, resuming and driving a run | Resume rebuilds derived state and carries judgements |
| `providers.py` | which providers a run uses; the cap fitted to the key's credit | |
| `estimate.py` | prices and the scene-count table | |
| `records.py` | the final package, the resume file, the trace, the cost summary | |
| `checkpoint.py` | every step saved to `.work/steps.jsonl`, replayed to carry on | Only our record types are restored |
| `demo.py` | the deterministic demo story | Offline configs and tests |

### Command line (`cli/`)

| Module | Commands |
|---|---|
| `run.py` | a run: `content "<topic>"`, `--resume`, `--at`, `--detach`, `--format`, `--seconds`, `--scenes`, `--max-usd` |
| `channel.py` | `new-channel`, `voice-audition`, `voice-design`, `voice-lock`, `music-audition`, `music-lock`, `music-map`, `analyse-narration` |
| `learning.py` | `harvest`, `verdict`, `label`, `train`, `eval` |
| `review.py` | `review`, `estimate` |
| `storage.py` | `storage`, and keeping the channel after any command that changes it (`keep_theme`) |
| `spend.py` | `spend`, `spend budget`; recording every run's and tool's calls (`record_spend`), reading OpenRouter and the bucket |
| `designs.py` | `designs list`, `veto`, and `model` (a free dry run of the checks; `--go` makes the 3D models on the cloud GPU) |
| `cloud.py` | `cloud setup`: the Google Cloud steps after the sign-ins, checked and done in order, safe to run again (gcloud runs through a replaceable function, so it is tested without Google) |
| `check.py` | `check`: is this machine ready (Python, ffmpeg, extras, the key and its balance, the channel, the bucket, Blender), with the fix for anything missing |
| `staging.py` | `staging`: the catalogue, models (search, find, add, vary, name), check, preview, backlog, new |

## Tunable Constants

Engine constants: craft and measurement limits that hold for every channel. Anything about how a
channel looks or sounds is theme data instead ([themes.md](themes.md)). Each was measured or
chosen for a reason given in the doc in the last column.

| Constant | Value | File | What it decides | Doc |
|---|---|---|---|---|
| `LONG_FRAGMENT_WORDS`, `MAX_SHORT_FRAGMENTS`, `SETUP_QUESTION_WORDS` | 5, 2, 6 | `story/prose.py` | robotic-writing detectors | narration.md |
| `MAX_NEW_DETAILS` | 4 | `story/prose.py` | new names and figures one sentence may bring in | narration.md |
| `TRIM_ORDER` | colour, supporting evidence, essential context | `story/weights.py` | what shrinks first when the story runs long; the spine never | narration.md |
| `CONTRADICTION_MIN` | 0.8 | `story/faithfulness.py` | NLI score that flags a line | machine-learning.md |
| `CREDIT_MARGIN_USD`, `MIN_RUN_USD` | 0.25, 1.0 | `workflow/providers.py` | credit kept back; smallest run allowed | runs-and-review.md |
| `NOTICEABLE_TEMPO` | 1.15 | `review/items.py` | a stretch flagged at the Narration sign-off | narration.md |
| `WARMTH_MARGIN` | 4.0 | `production/checks.py` | warmth beyond which a frame reads warm or cool | visuals.md |
| `MAX_UNMARKED_PAUSE`, `FRAGMENT_PAUSE` | 0.45 s, 0.3 s | `production/checks.py` | listen checks on the transcript | narration.md |
| `WRITING_USD`, `STORYBOARD_USD`, `NARRATION_TAKE_USD` | $1.50–2.50, $0.30, $0.09 | `production/budget.py` | cost estimates at the sign-offs; takes a passage from `VoiceSpec.expected_takes` | runs-and-review.md |
| `MIN_MEASURED_TAKES` | 8 | `theme.py` | takes of a voice before its measured pace sizes scripts | narration.md |
| `KEYFRAME_DRAWS_PER_SCENE`, `TRANSITION_TAKES`, `MARGIN_PER_PICTURE` | 1.5, 1.3, $0.01 | `production/budget.py` | how many scenes the money allows | visuals.md |
| `PHRASE_BARS` | 4 | `production/music_map.py` | bars per music phrase | narration.md |
| `MAX_NUDGE_SECONDS`, `MIN_GAP_SECONDS`, `MAX_LANDING_SECONDS` | 0.25, 0.05, 1.5 | `production/score.py` | beat and peak alignment | narration.md |
| `MAX_EXTRA_BREATH_SECONDS`, `MAX_LEAD_SECONDS` | 0.4, 1.5 | `production/stages/narration.py` | where spare music time goes | narration.md |
| `MAX_NARRATION_WORD_ERROR` | 0.2 | `production/stages/narration.py` | transcript mismatch shown to the person | narration.md |
| `SEGMENT_SAMPLE_POINTS` | 10%, 50%, 90% | `production/stages/segments.py` | morph frames described for Jev | visuals.md |
| `MAX_STORY_REFERENCES` | 6 | `production/stages/keyframes.py` | reference images per keyframe, theme's first | visuals.md |
| `LOOK` | a version string | `production/studio.py` | bump when local rendering code changes | visuals.md |
| `MIN_SCORE`, `FACE_HEIGHT` | 0.2, ⅓ | `production/focus.py` | focal-point trust; aim at a face | visuals.md |
| `VOICE_COMPRESSION` | ffmpeg `acompressor` | `production/assemble.py` | the voice's broadcast compression | narration.md |
| `RETRY_WAITS`, `VIDEO_TIMEOUT_SECONDS` | about 2 min; 20 min | `providers/http.py`, `production/media.py` | provider retries; morph polling | models.md |
| `PAUSE_SECONDS`, `WINDOW_SECONDS` | 0.12 s, 10 s | `production/narration_analysis.py` | how a reference narrator is measured | themes.md |

## Design Choices: Pros and Cons

**One LangGraph, topology in `workflow/graph.py`.**
Pro: the whole flow is readable in one place; interrupts give resumable reviews. The graph file
holds only nodes and edges; what each stop shows is `workflow/review_requests.py`.
Con: a new stage touches three places (its node, its route in `routing.py`, its edges).

**System 1 (Jev) for judging, System 2 (the critic) only on doubt.**
Pro: dozens of cheap judgements per stage instead of costly LLM reviews; every answer is stored
and learnable.
Con: Jev judges text, so visual questions depend on Gemini's descriptions; thresholds are global
and hand-set; it is often unsure (see models.md).

**Content-addressed cache for every paid asset.**
Pro: nothing unchanged is paid for twice; resumes and re-cuts are free.
Con: any input that drifts silently changes a key and pays again. Every bug that cost money on
the first production was this: re-chosen reference photos, lost judgements (emotional fields), refused
attempts not remembered. When adding inputs to a prompt or signature, make sure resumes
reproduce them exactly.

**Two ways back into a run: saved steps, and a saved handoff.**
`--resume` carries on from the step file (`steps.jsonl`): the whole graph state, exactly, so
nothing is rebuilt and nothing finished runs again. `--at` reopens an earlier review from
`resume.json` (written before every review) and starts a new step file.
Pro: a stop anywhere (a review, a crash, a killed process) loses at most the step in progress;
the handoff stays readable JSON a person or assistant can edit (hand-edited scripts).
Con: the step file is opaque (base64 blobs) and grows with every step (about 0.3 MB for the
offline demo); a reopened handoff loses whatever `ReviewHandoff` lacks and rebuilds it
(`_rederive`): revision counts restart at 0, attempt state comes back from the cache, warnings
are plain strings.

**Narration as the clock.**
Pro: pictures and music fit the voice, never the other way round; length is decided by the story.
Con: the length is only known after paid recording; the 168 s ceiling is enforced after narration
(see narration.md, the measured rate).

**Files as the review interface.**
Pro: the person (a window that opens itself, with per-card comments), the assistant (writes
JSON) and tests (stub reviewers) answer the same way; everything is logged.
Con: without `--detach` the run blocks while waiting. With it, the run exits at each review and
a separate `content review` serves the page; if that server is gone too, the page keeps the
comments and offers them for chat.

**Everything visual is ffmpeg.**
Pro: free, deterministic, inspectable; tests run it with tiny frames.
Con: slow at 1080×1920 (the texture pass takes about 8 minutes for 2:48) and filter graphs are
long strings that are hard to debug; `ruff` cannot check them.

**Optional extras for heavy models** (`learn`, `music`, `vision`).
Pro: the core installs light; tests never download models.
Con: behaviour differs by install (no `vision` → centre framing). The run should say which
extras are missing; today it does not.

## Quirks That Bite

- **Bump `LOOK` (`production/studio.py`)** when changing the code that renders the local look (glide, breathing,
  morph layer, texture), or cached clips made the old way are reused. Theme motion settings are
  in the keys already, so changing them needs no bump.
- **A keyframe's digest is part of two morphs' signatures.** Redrawing one keyframe pays for two
  morphs.
- **`config/config.json` and `config.fake-video.json` skip the Script sign-off**
  (`review_script: false`) so offline demos and most graph tests run unattended. The real config
  stops.
- **`ReviewResponse.decided_by` defaults to `unknown`.** The page's server writes `person`; the
  assistant must write `assistant`. Learning only uses `person`.
- **Whisper punctuation is a guess.** The listen check's fragment flag needs a real pause now; the
  unmarked-pause flag can still catch deliberate beats.
- **`ruff format` rewrote long filter strings once;** ffmpeg graphs are built from small helper
  functions (`_zoompan`, `_displacement_maps`) to keep them reviewable.
- **Tests:** `pytest` runs everything but the 12 whole-video renders in about 20 seconds;
  `pytest -m video` runs those (about 40 s each) after a change to production code. The video
  fixture renders small (270×480) at 10 fps: what those tests check does not depend on it.
- **Before a paid run** `tests/test_rehearsal.py` proves, for every configuration and channel
  present, that every prompt loads, every structured output is a schema the API accepts, and
  the story reaches its final package with each agent called on valid input.
- **Waiting on a run from a shell:** never `pgrep -f` a pattern your own command contains; wait
  on a PID or a file.
- **The test suite's `conftest.py` disables the focal detector** and fixes the narrator, so a
  theme can change without breaking tests. It also gives the theme a neutral tone that the fake
  provider's flat stills sit on; the offline demo instead draws them at the theme's own neutral
  tone, so neither redraws for colour. Tests run on `themes/starter`; `tests/test_theme.py`
  loads and checks every theme in `themes/`.
- **Saved runs from before a schema change do not load.** `ReviewHandoff` forbids unknown fields
  and there are no compatibility shims; migrate the file instead, keeping a backup beside it in `.work/`.
- **Story decisions do not re-time the beats.** A cut or demotion changes the ledger and what
  is required, but each beat keeps the words first allotted until the plan is sized again.
- **A step file only loads with the code that wrote it.** Its checkpoints hold our models by
  their module path; a schema change, or moving a record to another module, between sessions
  breaks `--resume` of a run in progress. Reopen with `--at` from `resume.json`
  instead (and migrate that, as above).
- **The assistant's tools end what they start.** Shell commands stop after 30 minutes and take
  any process they started with them, so the assistant always runs with `--detach` and never
  holds a run open waiting for the person.
- **Imports form no cycles and point one way** (`tests/test_architecture.py`). `routing.py` is
  handed the producer's task builders by `graph.py` rather than importing them; a part that
  needs something from a higher layer is a sign it is in the wrong place.

## Where to Optimise

1. **Speed the texture pass** (precomputed vignette mask; grain at half resolution).
2. **Fit Jev thresholds per question** once person labels exist (machine-learning.md, Phase 3).
3. **Calibrate the narration word budget** from a theme's `learning/narration.jsonl` (narration.md).
4. **Report missing extras** at the Start sign-off ("no `vision`: camera aims at the centre").
