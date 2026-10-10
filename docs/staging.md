# 3D Shots (Staging)

Last reviewed: 2026-10-10

Besides keyframes, a scene's pictures can be a 3D shot built and rendered in Blender: a set,
the things in it, what they do, the light, and a camera move, all chosen by name from a
catalogue and built by code. It is free to render (render time, not money), repeatable, and
every model is reused. Today it is a toolkit you use from the command line; joining it to
the Visual Director and production is the next step (at the end).

## The idea in one picture

```text
a shot (job.json)        names and settings, chosen from the catalogue; never code
   │  content staging check: every name, setting, model and capability, without Blender
   ▼
blocks (one file each)   layout → actors → actions → lights → camera, in that order
   │  written against `Stage`, a short list of verbs (place, animate, follow, light…)
   ▼
stage.py                 the only shot code that touches Blender's API: the foundation
   │  + the look (materials, world, tone): the channel's style, a file of its own
   ▼
audit, then render       the camera inside something, blocked, or snapping: no render
```

## Commands

| You want | Run |
|---|---|
| every block and model, with their settings | `content staging catalogue [--config themes/<name>/config.json]` |
| the models, or those matching some words | `content staging models "desk lamp"` |
| a model the library lacks, from free sources | `content staging find "typewriter" --config …`, then `--take N --as typewriter --names "type writer"` |
| add a model you downloaded (CC0 only) | `content staging add chair.glb --as side_chair --about "…" --licence CC0 --source "Poly Haven" --config …` |
| another word for a library model | `content staging name side_chair "dining chair" --config …` |
| check a shot without rendering | `content staging check shot.json` |
| stills of a shot, and a contact sheet | `content staging preview shot.json [--frames 1,60,120] [--scene] --config …` |
| start a new block | `content staging new action pour_drink [--channel --config …]` |

`preview` renders into `.cache/staging/` (gitignored) and prints the contact sheet's path;
`--scene` also saves the built scene as a `.blend` to open and look around in Blender. With
`--config`, the shot is drawn in the channel's look.

A shot, by hand (in the pipeline the Visual Director will write it):

```json
{
  "shot_id": "night-drive", "seconds": 5,
  "layout": {"block": "street", "settings": {"length": 80, "lamps": 3}},
  "actors": [{"actor_id": "car", "block": "vehicle", "model": "car", "settings": {"path": "road"}}],
  "actions": [{"block": "drive", "settings": {"vehicle": "car", "path": "road"}}],
  "lights": [{"block": "sky", "settings": {"time": "night"}}, {"block": "streetlights"},
             {"block": "headlights", "settings": {"vehicle": "car"}}],
  "camera": {"block": "track", "settings": {"subject": "car", "side": "left", "framing": "wide"}},
  "look": {"block": "plain"}
}
```

## What there is

`content staging catalogue` lists every block and setting; this is the shape of it.

| Kind | Blocks | Built on |
|---|---|---|
| layouts | `room`, `office`, `boardroom`, `corridor`, `street`, `studio`, `open_ground` | `sets.room` (walls, window, blinds, door), `sets.ground`; each layout names its marks and paths |
| actors | `prop` (on a mark), `stack` (column, pile, row, tower), `vehicle` (on a road) | `sets.stand` |
| actions | `travel`, `drive`, `slide`, `turn`, `scatter` (falling sheets), `topple` (real physics) | `motion.travel`: facing the way of travel, leaning into bends, no turn faster than 12° a frame |
| moves | `orbit` (to a full 360), `dolly` (in, out, sideways, up), `pan` (and panorama), `track`, `fly`, `hold` | `camera.film`: a path for the camera and a path for what it looks at; `camera.around` frames a subject and keeps the camera inside the set |
| lights | `lamp`, `window`, `overhead`, `studio` (three-point), `headlights`, `streetlights`, `sky` | `lighting.source`, `lighting.flicker` (any light can flicker) |
| props (models made in code) | 34: furniture, paper and money, office things, street and vehicles | `shapes` (legs, slabs, drawers) |
| looks | `plain` (the engine's); the starter kit's `starter`; a channel's own | `Plain`, whose small methods (colour, sky, tone) a look overrides |

The same pieces build on each other: a pan and an orbit are the same camera code with the
moving point swapped; driving is travel plus wheels; the office and the boardroom are the room
plus furniture; the starter look is the plain look with three methods changed.

## Models: one library, searched by meaning

A channel's models live in its folder, `themes/<name>/assets/` (`library.json` and the
files), so they are private and kept in the archive with the channel (`save-theme`, `pull`).
The engine's props are listed beside them. Each model has one id and other words for it.

- **Search** matches whole phrases, the words in them, and plurals: "sedan" finds `car`,
  "dossier" finds `folder`, "filing cabinets" finds `filing_cabinet`. With the `learn` extra
  installed it can also match by meaning.
- **No duplicates.** Adding a model that a search already finds is refused, with the command
  to add the new words to the existing one instead (`--alongside` for a genuinely different
  version).
- **Every model is the same shape of thing** (`blender/ingest.py`): one hierarchy, standing on
  the origin facing −Y, in metres (millimetre and centimetre files are recognised), at most
  150,000 faces, saved as `.glb`. Blocks never allow for a file's quirks.
- **Only free licences** (CC0, public domain), with the source, page and author kept.
- **Fetched when a shot needs it, never in bulk;** `used_in` records which videos used each.

| Source | What it has | How |
|---|---|---|
| props made in code | generic things: furniture, paper, money, vehicles, street | in the engine; add one with `content staging new prop` |
| Smithsonian Open Access | museum objects in CC0, often period pieces; coverage is narrow | `content staging find` (a free key from api.data.gov in `SMITHSONIAN_API_KEY`; without one, a few searches an hour) |
| Poly Haven and other CC0 sites | high-quality props | download by hand, then `content staging add` (Poly Haven's API needs a commercial licence; its files are CC0) |

## Looks: the channel's style, kept separate

A look decides how everything is drawn: a material for each role a block names (wood, paper,
metal, bulb…), the world, and the tone. It is the one kind of block that uses Blender's API.
The theme names it, and its settings are the feel:

```json
"staging": {"look": "starter", "look_settings": {"exposure": -0.3, "saturation": 0.75,
            "contrast": "Medium High Contrast", "shadow": "night", "glow": "sun"}}
```

The starter kit's look (`themes/starter/blender/looks/starter.py`) is the template: the plain
look, desaturated and pulled towards the palette. A channel copies it into its own
`blender/looks/`, renames it and changes what it draws; nothing in the engine changes. A
channel's own blocks (`blender/<kind>/`) work the same way, and may not reuse an engine
block's name.

## Quality: what is checked, and when

| Check | When | Catches |
|---|---|---|
| the shot check (`content staging check`) | before anything else, without Blender | unknown blocks or models, settings out of range, names that are not in the shot, an action given an actor that cannot do it (`drive` given a desk) |
| inside the set | every camera position, whatever the move | the camera behind a wall or in a building: it stays in the layout's `interior`, and the lens widens (to 20 mm at most) where it cannot step back |
| the audit, before rendering | sampled frames | the camera inside a solid thing, something blocking the view of the subject (glass does not count), the camera turning faster than 20° a frame. A failing audit stops the render |
| stills and contact sheet | `preview` | composition, light, scale |
| block snapshots | every test run, offline | any change that alters what a block builds (below) |

## Extending it

The routine change is a new block: `content staging new <kind> <name>` writes a template,
you fill in its docstring, settings and `build` using `Stage` verbs, and the tests and the
catalogue pick it up. Nothing else changes. `.claude/skills/staging/SKILL.md` is the
assistant's guide to doing it consistently.

Rules the tests enforce:

- A block file defines one block; its docstring says what it is (the catalogue shows it).
- Blocks use `Stage` verbs and the shared helpers (`maths`, `camera`, `motion`, `sets`,
  `shapes`, `lighting`), never Blender's API; only `stage.py`, `worker.py`, `audit.py`,
  `ingest.py` and looks import it, and nothing outside `content/blender/` imports those.
- Every block's example is built on a stand-in stage and its calls compared with a stored
  snapshot (`tests/snapshots/staging/`). A change that alters a block fails until the
  snapshot is renewed on purpose: `UPDATE_SNAPSHOTS=1 pytest -k <name>`.
- A verb is added to `Stage` (`api.py`) only when a new block needs it; it is the one routine
  reason to touch the foundation.

Conventions: metres and seconds; +Z up; a thing's front faces −Y; camera angles are degrees
round from the subject's front, anticlockwise from above.

## Measured on this laptop

Intel i7-10710U with integrated graphics, Blender 5.2.2, 540×960 stills: building a shot
takes 0.1–1.6 s (physics the longest), rendering 2–6 s a frame. A full-size final wants a real
GPU; a rented NVIDIA L4 is about $0.38 an hour on spot (to be benchmarked before relying on
it).

## Licence

Code that uses Blender's API is a derivative of Blender, so those few files (marked
`GPL-3.0-or-later` in their first line: `stage.py`, `worker.py`, `audit.py`, `ingest.py`,
and looks) are GPL; everything else stays MIT, because it only writes job files and runs
Blender as a program (`LICENSE`). A channel's own look is never distributed, so nothing is owed
for it. Renders belong to whoever makes them.

## Installing Blender

Blender 5.2 LTS, the version the blocks are written for, from
[blender.org](https://www.blender.org/download/lts/). On Linux, unpack it anywhere and set
`BLENDER=/path/to/blender` in `.env` (or put it on the path). `content check` says whether it
is found.

## Not built yet

| Step | What |
|---|---|
| the pipeline | `Scene.staging` in the storyboard; the Visual Director choosing from the catalogue (its prompt is a proposed change, for review); `check_visuals` running the shot check; a `find_assets` stage like `find_references`, with Jev judging models; `render_shots` before the Pictures sign-off; staged clips in the cut |
| figures | people: a CC0 base character and motion library, retargeted; a public figure as a model sheet and image-to-3D (about $1, once) |
| cloud rendering | finals on a rented GPU, one machine per job that deletes itself |
| transitions | joins built in 3D (pushing through into the next shot, one continuous take) beside today's dissolves and morphs |
| more sources | Sketchfab's CC0 models (needs the channel's own token) |
| imported textures | some museum scans render untextured in the plain look; to look into |
