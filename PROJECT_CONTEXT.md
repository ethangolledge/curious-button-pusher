# Project Context

Last updated: 2026-10-16

Read this first in a new session. It holds the current state of the engine and the decisions that
are not obvious from the code; everything else has one home in `docs/` ([docs/README.md](docs/README.md)).
A channel's own state and decisions live in its private folder (`themes/<name>/notes/`).

## What It Is

A learning project: a LangGraph pipeline that turns a true story into a narrated video, short
and vertical (TikTok, Reels, Shorts) or long and widescreen (YouTube). It researches, plans,
writes, fact-checks and storyboards one connected narration, then produces the video through
OpenRouter and the local ffmpeg. A person brings an idea, answers one round of questions from
the assistant (format, length, scenes, angle), then directs through sign-offs, each before money
is spent ([docs/runs-and-review.md](docs/runs-and-review.md)).

The repository is two parts, and a person's channel is a third, kept apart:

| Part | Where | Holds |
|---|---|---|
| The engine | `src/content/`, `config/`, `tests/`, `docs/` | the pipeline; no style, no story, no channel |
| The starter kit | `themes/starter/` | a complete neutral channel to build from, describing what every setting could be |
| A channel (private) | `themes/<name>/` (gitignored) | its theme, `config.json`, taste data, examples and notes; kept in the person's bucket ([docs/storage.md](docs/storage.md)) |
| Runs | `runs/<topic>/` (gitignored) | one story each; finished ones kept in the bucket |

`content new-channel <name>` makes a channel from the starter; the default configs and the tests
use the starter. Assistant skills in `.claude/skills/`: `new-channel` (building a channel with the
person), `make-video` (running a video with the director), `update-docs` (which doc to update
with a change). `AGENTS.md` says which applies when a session starts.

## Standing Decisions

- **The narration is the spine;** pictures and music fit it ([docs/architecture.md](docs/architecture.md)).
- **Authority:** truth (fact checker) defines what may be said; the Story Architect (Editorial
  Director) decides what matters; the Script Writer owns every word; a first-time listener (the
  cold viewer) tests understanding; Jev and code only judge.
- **Understanding per minute, not information per minute.** Research is complex; the story
  should not feel complex. Every passage answers what happened, why it matters, and why the
  next follows; every term is explained or cut ([docs/narration.md](docs/narration.md#the-standard-understanding-per-minute)).
- **System 2 writes, System 1 (Jev) judges, code measures;** the critic only settles doubt.
- **Five agents, kept separate;** topology only in `workflow/graph.py`; runtime instructions only
  in each agent's prompt files, which stay theme-neutral. Dependencies point one way, down the
  layers (`tests/test_architecture.py`).
- **Code holds no style, no story and no channel.** Look and voice are theme data; stories live
  in run folders and a channel's own `examples/`. Examples in prompts and docs are neutral,
  because they steer every story.
- **A channel is private.** The engine and starter are public; a channel folder is never
  committed, and is kept whole in the person's bucket with every earlier version restorable.
- **The person is the director.** The assistant answers the reviews in between as `assistant`,
  never approves a sign-off for the person, and escalates what changes the story, money or look.
  Only a person's decisions train the learning loop.
- **Never pay twice:** every paid asset is cached by its full request; resumes keep chosen
  reference photos and remembered refusals.
- **A run survives its process.** Every step is saved (`.work/steps.jsonl`); a review can be
  left open (`--detach`) and answered later, on its own page server or in chat
  ([docs/runs-and-review.md](docs/runs-and-review.md)).
- **A run is capped** at `production.max_usd`, lowered to the key's remaining credit.
- **The keyframe is the foundation; Blender moves it.** With `production.pictures: "animated"`
  each approved keyframe is lifted into depth by published models (MoGe-2, Grounding DINO,
  SAM 2, ViTPose, LaMa) and moved in Blender as itself: frame one is the picture, the camera
  glides with real parallax, people breathe. Free and local. Action a still cannot hold is the
  next step: a video model guided by the same shot, paid, with sign-off
  ([docs/picture-shots.md](docs/picture-shots.md)).
- **3D shots are described, then built by a pipeline.** The Visual Director describes what is in
  a shot (things, relations, people, actions, camera); code resolves every thing (library,
  families made from its words, people made from one parametric body, objects made by
  Infinigen or found in free collections and scored by eye on this computer), keeps it in a
  catalogue with its lineage, places every copy clear of everything, and renders it through the
  foundation (`content/blender/stage.py`, the only shot code that touches Blender). Nothing in
  3D costs money; what nothing can stage falls back to a keyframe and goes in the backlog. A
  missing ability is built as a block by people and the assistant. A channel's look and models
  are its own, in its private folder ([docs/staging.md](docs/staging.md)).
- **One paid GPU service, kept apart: SAM 3D** (Meta's SAM 3D Objects and SAM 3D Body). The
  container lives in `cloud/sam3d/`, outside the engine; GitHub Actions builds it on a push to
  `main` that changes it and points two Cloud Run jobs at its digest. A job runs only while it
  works (billed by the second, every picture of a request in one start), has no address and no
  route to the internet; the weights stay in the person's private bucket. Signing in uses
  Workload Identity Federation (no keys), every setting is a GitHub environment secret, and
  everything fetched is pinned by hash. The engine reaches it only through
  `providers/sam3d.py` ([cloud/sam3d/README.md](cloud/sam3d/README.md)). Not yet run on a GPU.
- **Out of scope:** publishing, caption and hashtag copy, thumbnails, sound effects, production
  infrastructure beyond the SAM 3D job, and integrations not explicitly requested. The bucket is the person's own
  permanent storage, not infrastructure the pipeline needs: without one, everything stays local.

## State (2026-10-12)

- Engine: about 16,000 lines in layered packages (`docs/codebase.md`), about 250 deterministic
  tests in 20 s plus 13 whole-video renders (`pytest -m video`), ruff and strict mypy clean, no
  import cycles and one-way layers (enforced by a test). Validated end to end on a first
  long-form production.
- 3D shots (Blender 5.2): scenes described and composed (relations, groups, furnishing);
  things resolved through a cascade into a SQLite catalogue with lineage (families, versions,
  people made with MakeHuman, Infinigen, an Objaverse index, Sketchfab, Poly Pizza, Gazebo
  Fuel, the Smithsonian; CLIP scoring, automatic taking with keep/veto); people posed by
  inverse kinematics to touch what they use, varied across a group, holding what is `held_by`
  them; each staged still looked at by the vision model for physical mistakes and composed
  again once if it fails (about 1p); 41 blocks, 35 props;
  `production.pictures: "staged"` and `production.joins: "rendered"` make a video one moving
  picture ([docs/staging.md](docs/staging.md)); `"animated"` moves each keyframe itself
  ([docs/picture-shots.md](docs/picture-shots.md)). Not yet: motion capture, likenesses on made
  people, cloud rendering.
- Designs (2026-10-16): a person, place or object in two or more scenes is drawn once in the
  channel's look, checked by Gemini and Jev, kept with the channel, and every keyframe showing
  it is drawn from it, in later videos too; `content designs model` makes their 3D models in
  one GPU job after free checks ([docs/3d-reuse.md](docs/3d-reuse.md#designs)). Not yet tried
  in a real run.
- `content eval` caught all seven failures a director named in a rejected final cut, three runs
  out of three ([docs/narration.md](docs/narration.md#regression-content-eval)); false alarms on an
  approved script are not measured yet.

## Next Work

1. The 3D plan ([docs/3d-reuse.md](docs/3d-reuse.md)): the first SAM 3D GPU run, then reuse
   (cast, props, sets made once from reference pictures), the shot ladder, and cheap checks
   (code, then Jev) before the GPU. The channel's own look.
2. Measure `eval`'s false alarms once a channel has a `positive.json`.
3. Tune thresholds and the critic from recorded judgements.
4. The code improvements listed in [docs/codebase.md](docs/codebase.md#where-to-optimise).

Never store credentials or complete provider payloads containing secrets in tracked files.
