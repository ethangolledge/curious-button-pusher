# 3D Shots (Staging)

Last reviewed: 2026-10-10

Besides keyframes, a scene's pictures can be a 3D shot built and rendered in Blender: a set,
the things in it, what they do, the light, and a camera move, all chosen by name from a
catalogue and built by code. It is free to render (render time, not money), repeatable, and
every model is reused. A channel chooses it with `production.pictures: "staged"` in its
`config.json` (the starter stays on `keyframes`); the Visual Director then stages every scene
the toolkit can show, and draws the rest as keyframes, as before.

## In a run

Nothing about the rest of the pipeline changes; a staged scene goes through the same steps
as a keyframe scene, with its picture rendered instead of drawn.

| Step | A keyframe scene | A staged scene |
|---|---|---|
| storyboard | anchor, focus, camera, motion, bridge | the same, plus `staging`: the shot from the catalogue (`agents/visual_director/staging_prompt.md`); or `missing`, saying what the toolkit lacks |
| storyboard gate | structure | also the shot check (`staging.plan.staging_issues`); a shot that still fails after the Visual Director's revisions is drawn instead |
| keyframe | drawn by the image model | the shot's first, middle and last frames rendered (`production/stages/keyframes.py`); then the same measures and judging: brightness and colour against the scene's feeling, the vision model's description, Jev. A shot measured too dark or too cool is rendered again with a corrected grade; one that cannot be rendered is drawn instead |
| the feeling | colour words in the prompt, the ripples' tint | a grade on the render (`job.Grade`: exposure, and warmth by white balance), and the same ripples' tint |
| Pictures sign-off | the animatic moves the stills | the animatic plays a quick draft of the shot (half size, 12 frames a second) |
| morphs | from keyframe to keyframe | AI morphs (`production.joins: "ai"`) run from the frame where the morph out begins to the next scene's frame where it holds; rendered joins (`"rendered"`) play over both shots' moving frames, so nothing stops at a join |
| the cut | the still, moved by ffmpeg, breathing | the shot rendered in full over its window (from the start of the morph into it to the end of the morph out), its middle held, with the same breathing ripples and tint over it (`assemble.shot_clip`, `studio.ShotWindow`) |
| texture, joins, music, subtitles | the same | the same |

What a scene could not be staged for is kept in the channel's backlog
(`content staging backlog`), most wanted first: the next block or model to build. Nothing is
built at run time.

The budget counts a staged scene's picture as free, so the same cap affords more scenes; the
morphs between them are still paid.

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
| what scenes could not be staged for, most wanted first | `content staging backlog --config …` |

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
| layouts | `room`, `office`, `boardroom`, `corridor`, `street`, `studio`, `open_ground`, and `set` (any hand-built set from the library) | `sets.room` (walls, window, blinds, door), `sets.ground`; each layout names its marks and paths |
| actors | `prop` (on a mark), `stack` (column, pile, row, tower), `vehicle` (on a road), `figure` (a character playing a motion), `picture` (an image on a card: a map on a table, a view out of a window) | `sets.stand` |
| actions | `travel`, `drive`, `slide`, `turn`, `scatter` (falling sheets), `topple` (real physics) | `motion.travel`: facing the way of travel, leaning into bends, no turn faster than 12° a frame |
| moves | `orbit` (to a full 360, closing into a spiral), `dolly` (in, out, sideways, up), `pan` (and panorama), `track`, `fly`, `hold`, `vertigo` (the dolly zoom) | `camera.film`: a path for the camera and a path for what it looks at; `camera.around` frames a subject and keeps the camera inside the set and out of what it films |
| lights | `lamp`, `window`, `overhead`, `studio` (three-point), `headlights`, `streetlights`, `sky` | `lighting.source`, `lighting.flicker` (any light can flicker) |
| transitions (rendered joins) | `dissolve`, `flow` (smooth), `zoom_through`, `swirl` (swift), `fractal_dive` (the endless inward spiral), `shatter_dive` (a splitting mosaic), `kaleidoscope`, `dots`, `melt` | `patterns` (polar coordinates, turning, zooming, mirrored wedges, the Droste spiral) on the `Canvas` verbs |
| props (models made in code) | 36: furniture, paper and money, office things, street and vehicles, and standing and seated figurines | `shapes` (legs, slabs, drawers), `shapes_figure` |
| looks | `plain` (the engine's); the starter kit's `starter`; a channel's own | `Plain`, whose small methods (colour, sky, tone) a look overrides |

The same pieces build on each other: a pan and an orbit are the same camera code with the
moving point swapped; driving is travel plus wheels; the office and the boardroom are the room
plus furniture; the starter look is the plain look with three methods changed.

The theme's camera moves (`visual.camera_moves`: push_in, orbit, drift…) are also 3D moves:
`staging.moves` in `theme.json` maps each to a move block and its settings, so a staged scene
moves the way its keyframe scene would, and the Visual Director can name either.

## Transitions: morphs drawn in Blender

`production.joins: "rendered"` replaces the paid AI morphs with transitions drawn in Blender
from the two pictures, free, for keyframe and staged channels alike. Each is a small program
on the frame: for every point, which picture to show and where in it to look, written with
the `Canvas` verbs (`canvas_api.py`: the pictures, positions, maths, noise, mixing) and built
as a GPU shader (`canvas.py`), so a frame takes a fraction of a second. Tests record the
program instead (`rehearsal.RecordingCanvas`) and compare it with a snapshot.

| | |
|---|---|
| which transition | the storyboard's choice (a scene's `transition`, in a staged storyboard), or the theme's `staging.joins`: `slow` for a small change of feeling between the scenes, `swift` for a large one (the emotional field's shift) |
| moving through | a join between staged scenes plays over both shots' frames (image sequences): the shot it leaves keeps moving, the one it arrives at is already moving |
| on top | the same ffmpeg morph effects (warp, trails, mirror, plates) as AI morphs, then the texture |
| checks | the same as AI morphs: cuts, frozen frames, three moments described and judged |
| cost and time | free; about half a second a frame at 360×640 on this laptop, so a 4-second join at full size is a minute or two |

The fractal dive is the Droste effect in motion: the frame opens into copies of itself, each
smaller than the one round it, wound into a spiral that flows inward; copies of the next
picture arrive at the edge ring by ring until they fill it, and it closes on the next picture.

## Characters

People are the hardest part of 3D and the easiest to get wrong; the channel's style helps,
because drawn and figurine-like characters never ask to be real. The route, each character made
once, with the director's sign-off, and kept in the library:

| Step | How | Cost |
|---|---|---|
| a model sheet | the image model draws the person as a figurine in the channel's style: full figure, relaxed A-pose, flat even light, plain ground; the front first (approved before the rest), then the side and back from it | about $0.05 a view |
| a 3D model | a multiview image-to-3D service (Tripo was tested: clean shapes, a recognisable face all round) | about $0.30 |
| a skeleton and motions | the same service's rig and preset motions (idle, walk, turn…) | about $0.35 |
| into the library | `content staging add figure.glb --as <name> --can humanoid --turn <degrees to face front> --height <metres>`: ingest keeps the skeleton and records the motions | free |
| in a shot | the `figure` actor stands it on a mark and plays a motion | free |

About $1 a character, once. The Kushner figure from the proof of concept is in Arthoodds'
library made exactly this way. Faces: a figurine's simple face holds up at a medium shot; a
close-up is better drawn (a keyframe scene beside staged ones), or its face can be re-projected
from a high-resolution portrait onto the model (not built). Anonymous figures (officials, a
crowd, delegates round a table) are free: the `person` and `seated_person` figurines made in
code. Not built yet: a library of CC0 motions retargeted onto any character (sitting, pointing,
typing), and a step that makes a character from a request during a run.

## A continuous video

With `pictures: "staged"` and `joins: "rendered"`, a video is one moving picture: every staged
scene is a rendered shot, every join plays over the moving frames on either side, and the
breathing, colour and texture run over the whole cut. Nothing holds still unless a scene asks
it to; nothing is paid for but the words and the voice. What it does not yet do:

- **Scenes that cannot be staged** (people, places with no layout) are drawn keyframes: still
  pictures moved by ffmpeg. The backlog says what to build so fewer are.
- **One continuous camera move between scenes in the same place** (a `travel` join: the camera
  flies from one framing of a set to the next, no transition at all) is the next step for
  scenes that share a set; it needs both shots built in one scene.
- **A single world for the whole video** (every set laid out in one place, one camera path
  through them) is possible but fragile and slow to render; the transitions are the channel's
  identity ("one idea holds the panel, then transforms into the next"), so they stay.

## Custom sets, built by hand

A place the layouts do not cover (a harbour, a bank vault, a particular office) can be built
once in Blender, or downloaded, and used by name with the `set` layout. Name its parts and
they become what shots refer to:

| Name in Blender | Becomes |
|---|---|
| an empty `mark_<name>` | a mark, facing the empty's −Y (where props stand, where the camera may look from) |
| a mesh `surface_<name>` | a mark on its top: props stand on it (a counter, a table) |
| empties `path_<name>_0`, `path_<name>_1`… | a path through them in order (a walk, a road, a flight) |
| any object `actor_<name>` | an actor that moves and lights can refer to (a door, a lamp) |
| a box `interior` | the space the camera stays in; it is not rendered |

Export it as `.glb` and add it like any model (`content staging add set.glb --as vault --about
"…" --licence CC0 --source "hand made" --config …`). Ingest records its named parts in the
library, so shots on it are checked without Blender, and the catalogue lists them for the
Visual Director.

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
metal, bulb…), a material for pictures, anything it adds to every solid (`dress`: an outline,
say), the world, and the tone. It is the one kind of block that uses Blender's API.
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
- A setting that names a model is declared so (`ModelName`): the model is checked and its
  file sent with the shot.
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
[blender.org](https://www.blender.org/download/lts/). `content check` says whether it is
found.

| Computer | Install | Then |
|---|---|---|
| macOS | the `.dmg`, dragged to Applications (Apple silicon renders with Metal) | `BLENDER=/Applications/Blender.app/Contents/MacOS/Blender` in `.env` |
| Linux, Windows with WSL | the `.tar.xz`, unpacked anywhere | put it on the path (`ln -s …/blender ~/.local/bin/blender`) or set `BLENDER` in `.env` |

Everything else (ffmpeg included) runs on macOS as on Linux; the effects are the same.

## Not built yet

| Step | What |
|---|---|
| characters during a run | making a character the storyboard asks for, signed off at the Pictures stage (today: by hand, then added to the library) |
| more motions | a CC0 motion library retargeted onto any character; procedural gestures (reach, point, type) |
| finding models in a run | today a missing model makes the scene a keyframe (and a backlog line); next, the run searches free sources and Jev judges the candidates, as reference photos are found |
| `travel` joins | one camera move between two framings of a shared set |
| cloud rendering | finals on a rented GPU, one machine per job that deletes itself; this laptop takes seconds a frame |
| more sources | Sketchfab's CC0 models (needs the channel's own token) |
| imported textures | some museum scans render untextured in the plain look; to look into |
