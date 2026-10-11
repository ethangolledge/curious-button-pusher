---
name: staging
description: Build 3D shots in Blender the same way every time - compose a shot from the catalogue's blocks and models, check and preview it, find or add models without duplicates, and when something is missing build a new block or look that fits the foundation. Use whenever someone wants a 3D scene, a camera move, a model, a set, a look for 3D shots, or asks "can we do X in Blender".
---

# 3D shots: composing, and growing the toolkit

The whole design is in `docs/staging.md`; read it first. The person directs; you do the
technical work and show them stills before anything is final.

## Composing a shot

1. **Start from what exists.** `content staging catalogue --config <channel>` lists every
   block with its settings; `content staging models "<words>"` searches the models. Reuse
   before you build: most shots are a layout, one or two actors, an action, a light and a move.
2. **Write the shot** as a job file (JSON, the shape in `docs/staging.md`) in the scratchpad or
   the run's folder, never in the repository: a shot belongs to a video.
3. **Check it:** `content staging check shot.json`. Fix every line it reports.
4. **Preview it:** `content staging preview shot.json --config <channel>` renders stills in the
   channel's look and prints a contact sheet. Look at it yourself first (composition, light,
   scale, is the subject in frame and doing something), then show the person. A failing audit
   (camera in a wall, the view blocked, a snap, two things passing into each other) means fix
   the shot (another mark, `across`/`along`), not force the render.
5. Say what is a guess: a size, a time of day, a framing.

## When a model is missing

Never stop at "we don't have it": something always fits, in this order (`docs/staging.md`,
"When something is missing").

1. Search again with other words (`content staging models "<words>"`): a near thing may do.
2. A version of what is there: `content staging vary <id> --from <model> --paint part=role
   --height <m> --about "…" --config <channel>` (same shape, repainted part by part or role by
   role, resized; no file copied).
3. The free sources: `content staging find "<words>" --config <channel>` searches every source
   with a key, prepares the best six and draws them in the channel's look. Look at the sheet
   yourself (is it the thing, upright, at a sane size, not a mess of a scan?), then show the
   person, then `--take N --as <id> --about "…" --names "…"`. Only CC0, public domain, own
   and CC BY are ever offered; CC BY makers are credited with the video automatically.
4. Built in code: `content staging new prop <name>`, from the shared shapes. Generic things a
   channel will use again and again are better as props: simple shapes with bevels read
   better than noisy scans.
5. Downloaded by hand: `content staging add <file> --as <id> --about "…" --licence <CC0|CC-BY…>
   --source "…" --page <url> --author "…" --config <channel>`.

If it is refused as a duplicate, add the words to the existing model instead
(`content staging name <id> "<words>"`). One thing, one model. Look at the four-view sheet
every add prints; wrong scale or facing: add again with `--height` or `--turn`. Keys for the
sources go in `.env` (never ask anyone to paste one into the chat).

## A place the layouts do not cover: a set

Build it once in Blender (or download a CC0 one) and add it as a model; the `set` layout then
uses it by name. Name its parts so shots can refer to them: empties `mark_<name>` (facing their
−Y), meshes `surface_<name>` (props stand on them), empties `path_<name>_0…`, objects
`actor_<name>`, and a box `interior` for the camera's space (`docs/staging.md`, "Custom sets").
Keep it simple and solid: closed walls, real-world size, nothing loose.

## When an ability is missing: build a block

Only when no block, with any settings, can do it. A block is general (`drive`, not
`drive_the_getaway_car`): story and style never go in it.

1. `content staging new <kind> <name>` (engine, public) or with `--channel --config …` (the
   channel's own, private: its style, its signature moves and transitions).
2. Write the docstring first: one paragraph a director would understand; it is what the
   Visual Director and the catalogue read. Layouts list their marks and paths.
3. Settings: a frozen dataclass; every number gets a `Range` with its unit, every name an
   `About`; choices are `Literal`s; defaults for everything but the names it needs.
4. `build` uses `Stage` verbs and the shared helpers only: `camera.around`/`film` for any
   camera move, `motion.travel` for anything that moves along a path, `sets.room`/`stand`
   for places, `shapes` for props, `lighting.source`/`flicker` for lights. If two blocks would
   share code, it goes in a helper, not in both. Never import Blender's API (the tests refuse).
5. Its `example` refers only to what the test stage has: the `centre` mark (a table-top),
   the `across` and `road` paths, the actors `thing` and `car`, the set `sample_set` and the picture `sample_picture` (an actor
   names the model its example places in `example_model`).
   A setting that names a model is a `ModelName`, so the model is checked and sent along.
6. `pytest -k <name>` writes its snapshot; `content staging preview` a shot using it and look.
7. If it truly needs a new verb, add it to `Stage` (`api.py`), both stages (`stage.py`,
   `rehearsal.py`; what they keep alike goes in `bookkeeping.py`) and a test, and say so: it
   is a change to the foundation. Ask first whether an existing verb can do it: `occupied`
   (what stands in a space) and `bounds` answer most "is there room?" questions.
8. A change to an existing block that alters what it builds fails its snapshot; renew it on
   purpose (`UPDATE_SNAPSHOTS=1 pytest -k <name>`) and say what changed.

## A transition

A new transition is a block too (`content staging new transitions <name>`): a program on the frame written with the `Canvas` verbs and the
shared `patterns`, never Blender's API. Keep the theme's rule: it transforms, it never cuts,
strobes or flashes; open from the plain first picture and close on the plain second. Test it
on two real keyframes (a join job: `docs/staging.md`) at small size before anything else.

## A character

Only with the director's sign-off, and only once per person (`docs/staging.md`, "Characters"):
a figurine model sheet (front approved first), a multiview image-to-3D model with a rig, then
`content staging add … --can humanoid --turn … --height …`. Check its four-view sheet faces the
front and stands on the plinth. Anonymous people are the free `person` and `seated_person`.

## A channel's look

The look is the channel's style and lives in its folder (`themes/<name>/blender/looks/`).
Start from the starter kit's (`themes/starter/blender/looks/starter.py`): subclass `Plain`
and override only what differs (`colour`, `sky`, `tone`, or `material` for a whole new
shading style). Put every number a person might tune in its settings, and the values in
the theme (`staging.look_settings`), so the feel changes without code.

## Before you finish

- `content staging check` passes and you have looked at the stills.
- New blocks: docstring, ranges, example, snapshot; `ruff`, `mypy`, `pytest` pass.
- `docs/staging.md` lists any new block kind, helper or rule; channel-only work stays in the
  channel's folder (`content storage save-theme` after it).
