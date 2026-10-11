# 3D Shots (Staging)

Last reviewed: 2026-10-11

Besides keyframes, a scene's pictures can be a 3D shot built and rendered in Blender. The
Visual Director **describes** what is in the shot (the room, the things in it and where they
go, what happens, the camera); a pipeline finds or makes every thing, fits it to the scene,
places it, and renders it in the channel's look. It is free to render (render time, not
money), repeatable, and everything found or made is kept for every later video. A channel
chooses it with `production.pictures: "staged"` in its `config.json` (the starter stays on
`keyframes`); scenes the toolkit cannot show are drawn as keyframes, as before.

## From a description to a shot

```text
the scene (the Visual Director's words)                     schemas/staging.py: StagePlan
   room, things (what, how many, height, looks, where), people, actions, camera
        │
        ▼  resolve each thing, cheapest first, everything kept       staging/resolve.py
   the library (made in code, families, versions, models kept before)
   → a person made to fit (MakeHuman)                                  staging/people.py
   → made on this computer (Infinigen) or found in free collections   staging/sourcing.py
     (Objaverse index, Sketchfab, Poly Pizza, Gazebo Fuel, Smithsonian),
     scored by eye (CLIP) and taken when plainly the thing             staging/scoring.py
        │
        ▼  transform: one standard form, upright, real size, role colours  blender/ingest.py
   kept in the catalogue: files by hash, lineage, usage                staging/store.py
        │
        ▼  compose: the room built, every copy placed by its relation,  staging/compose.py
   clear of everything, background detail added, actions given to each copy
        │
        ▼  a job (job.json), then Blender                               blender/worker.py
   the look paints every surface by its role; the audit checks; the shot renders
        │
        ▼  judged like a keyframe; a shot that fails is drawn instead
```

Nothing here costs money. A thing nobody has (and nothing can make) leaves its scene drawn,
and goes in the channel's backlog.

## In a run

| Step | A keyframe scene | A staged scene |
|---|---|---|
| storyboard | anchor, focus, camera, motion, bridge | the same, plus `staging`: the description (`agents/visual_director/staging_prompt.md`); or `missing`, saying what the toolkit lacks |
| storyboard gate | structure | also the free check: the room, the blocks and their settings, every relation's target, and the shot composed (`staging.plan.staging_issues`). A thing the library lacks is not a problem yet when the run can find models: it is looked for before rendering. A shot that still fails after the Visual Director's revisions is drawn instead |
| before rendering | — | what the staged scenes lack is found or made, and taken automatically (`Keyframes._prepare_models`); each model taken without a person is named in the run's warnings for review |
| keyframe | drawn by the image model | the shot's first, middle and last frames rendered; then the same measures and judging: brightness and colour against the feeling, the vision model's description, Jev. The vision model is also told the frame is a 3D shot (`production/shot_perception.md`), so it reports what is physically wrong (a hand short of its glass, a thing floating or passing through another, a person sat in the furniture) as an artefact, and `keyframe_clean` fails on it: the shot is then composed again with the next seed, not only regraded (about 1p a look). Too dark or cool: rendered again with a corrected grade. A shot that cannot be built (it fails the audit) or that Jev finds does not show its scene is drawn instead, at once, its reason in the scene's `missing` and the backlog |
| the feeling | colour words in the prompt, the ripples' tint | a grade on the render (`job.Grade`: exposure, and warmth by white balance), and the same ripples' tint |
| Pictures sign-off | the animatic moves the stills | the animatic plays a quick draft of the shot |
| morphs | from keyframe to keyframe | AI morphs (`production.joins: "ai"`) or rendered joins (`"rendered"`) that play over both shots' moving frames |
| the cut | the still, moved by ffmpeg, breathing | the shot rendered over its window (from the start of the morph into it to the end of the morph out), with the same breathing ripples and tint (`assemble.shot_clip`) |
| credits | — | the makers of CC BY models used are listed with the finished video, for its description |

## The scene, as the Visual Director describes it

```json
{"layout": {"block": "boardroom"},
 "things": [
   {"thing_id": "men", "what": "man in a suit", "count": 8, "height": 1.8,
    "person": {"pose": "seated", "dress": "suit", "motion": "talking"},
    "place": {"relation": "seated_at", "target": "table"}},
   {"thing_id": "glasses", "what": "water glass", "height": 0.12,
    "place": {"relation": "in_front_of", "target": "men", "each": true}},
   {"thing_id": "files", "what": "folder", "count": 5, "height": 0.02,
    "place": {"relation": "stacked_on", "target": "table"}}],
 "furnish": "some",
 "lights": [{"block": "overhead", "settings": [{"name": "over", "value": "table"}]}],
 "camera": {"block": "orbit", "settings": [{"name": "subject", "value": "men"}]}}
```

| Part | Says |
|---|---|
| `layout` | the room or place: a layout block (office, boardroom, room, corridor, street, studio, open ground, a hand-built set) and its settings. Its marks and furniture are named, and things can be placed in relation to them |
| a thing's `what` | plain words, as a prop master would ask ("leather briefcase", "oil tanker"): what the toolkit resolves |
| `count`, `height`, `width`, `depth` | how many, and its real size in metres: a model of any size is scaled (or a family made) to it |
| `looks` | colour and material ("colour: red", "material: brass"): they become the role it is drawn in, and choose a family's settings |
| `place` | a relation to a target (another thing, the room's furniture or marks, or `floor`), `each` for one per copy of the target: `on`, `scattered_on`, `stacked_on`, `in_row_on`, `beside`, `in_front_of`, `behind`, `around`, `seated_at` (chairs added where there are none), `against_wall`, `at`, `held_by` (in people's hands: a drink, a document, a pen, a phone; `each` for everyone, else `count` of them) |
| `person` | for people: `who` (a particular person the library holds), or sex, age, build, dress, pose (standing, seated, walking), activity (what the hands do: resting, lap, folded, pointing, pockets) and motion (breathing, talking, walking, still). Age, build and activity left empty vary across a group |
| `furnish` | `bare`, `some` (pieces against the walls), `lived_in` (also small things on surfaces), by the room's own rules |
| `actions` | an action block done by every copy of `who`, each `stagger` of the shot after the last |
| `camera` | a move; its `subject` may name a thing, and every copy is framed together |

## Resolving a thing: the cascade

| Step | What | When |
|---|---|---|
| the library | the channel's models, the engine's props, versions of either, people made before: searched by words and meaning | always; free and instant |
| a family | a prop with settings made to fit the words: "espresso cup", "conference table" eight metres long, "tower" of 20 storeys | when the library's match is a family |
| a person | made from one parametric body to the description, once, and kept (below) | for people, when `content staging people` has been run |
| made here | Infinigen's generators: about a hundred kinds of everyday object, each in endless variations; the channel's own to use | when installed (`content staging infinigen`) |
| found | the free collections, searched together, the best six prepared and drawn plainly, each scored | when Blender and the `vision` extra are here; each collection when ready (below) |
| drawn instead | the scene becomes a keyframe; the gap goes in the backlog | when nothing fits |

**Scoring a candidate** (`staging/scoring.py`): a CLIP model on this computer looks at the
candidate drawn on the studio plinth and weighs "a 3D model of <the thing>" against everyday
others and the ways a download goes wrong; its title counts a little too. Real mugs score
0.5 to 0.9 as a coffee mug and 0.0 as a ballot box. From 0.5 the best is taken automatically,
joins the library as `auto`, and is named in the run's warnings; a person keeps it or turns it
down (`content staging keep` / `veto`). A turned-down model is never used or offered again.

**Sources** (`providers/sources.py`, searched in this order):

| Source | What it has | Ready when |
|---|---|---|
| Infinigen | ~100 kinds of indoor and outdoor object, made on this computer (2 to 3 s each) | `content staging infinigen` (its own Python 3.11 and Blender 4.2, a few GB, in `.cache/infinigen`) |
| Objaverse | ~800,000 Sketchfab models, indexed here with Objaverse++'s quality scores; only CC0 and CC BY, of good quality, single things | `content staging objaverse` (about 800 MB of metadata, once) |
| Sketchfab | over a million models, searched live | `SKETCHFAB_API_TOKEN` in `.env` |
| Poly Pizza | ~10,000 low-poly models (Kenney's, Quaternius's, Google Poly's) | `POLY_PIZZA_API_KEY` in `.env` |
| Gazebo Fuel | an open library of everyday objects, Google's scanned household items among them | always (COLLADA files are read with the `models` extra) |
| Smithsonian Open Access | museum objects in CC0 | always (`SMITHSONIAN_API_KEY` for more searches an hour) |

Only models anyone may use, commercially too, are ever offered: CC0, public domain, the
channel's own, or CC BY (credit to the maker). `content check` says which sources are ready.

## The catalogue

A channel's models live in its folder, `themes/<name>/assets/`, private and saved with the
channel (`save-theme`, `pull`):

- `catalogue.sqlite`: `models` (one row a model, its record beside the columns worth asking
  about: source, licence, status), `lineage` (every step that made or changed a model: fetched,
  prepared, scored and chosen with every candidate's score, made, versioned, kept, turned
  down), `usage` (which videos used which models). `content staging history <id>` prints a
  model's lineage. An old `library.json` is moved in once.
- `files/<hash>.glb`: every file stored by what it holds, so the same file is kept once and a
  record can never point at a file that changed.

**Every model is the same shape of thing** (`blender/ingest.py`): one hierarchy, standing on
the origin facing −Y, in metres (millimetre, centimetre and inch files recognised, COLLADA's
own unit applied), upright (files whose maker took Z as up are turned), at most 150,000
faces, as `.glb`. Blocks never allow for a file's quirks.

**Search** matches whole phrases, the words in them and plurals ("sedan" finds `car`); with
the `learn` extra, also meaning. Adding a model a search already finds is refused, so the
library never holds one thing twice under different names.

## Made to fit

| Way | What | How |
|---|---|---|
| families | one shape for a whole kind of thing: a cup (mug, teacup and saucer, espresso, beaker), a glass (tumbler, whisky, wine, champagne, pint), a bottle (wine, beer, spirits, water, medicine), a box of any size and material, a table (kitchen, dining, coffee, side, conference), a book (paperback to folio), a building (house, flats, tower, warehouse; any storeys) | a prop with settings; a scene's words choose them (`resolve.settings_for`) |
| stretched | any model, found or made, to a width, depth and height; an axis not given keeps its proportions | `ModelFile.fit`, one formula for the stage and the pipeline (`maths.fit_scale`) |
| repainted | a thing's colour and material words become the role it is drawn in | `resolve.look_of`; `paint` on a version |
| versions | the same shape, repainted part by part and resized, under its own name, no file copied | `content staging vary` |
| its own colours | an imported model's surfaces each take the role their colour is nearest (a white mug paper, a red one brick), or the role their material is named for | `blender/materials.py` |

## People

`content staging people` installs, once, the MPFB extension for Blender and MakeHuman's CC0
clothes and hair (about 650 MB). Then a person a scene describes is made from one parametric
body (`blender/person.py`): shaped by sex, age and build, made the height asked, dressed
(suit, casual, work, uniform) with shoes and hair, and posed by code so the pose fits any body
(standing, seated at a table, mid-stride). What their hands do (`ACTIVITIES` in
`person.py`) is reached for, not set joint by joint: each hand is given a point (on the table,
by the hips, at the chest) and inverse kinematics bends the arm to it, an elbow target keeping
it natural, then the fingers close by how much the grip needs (flat, rest, hold, point). A
person holding something reports where it sits in their hand (`holds`), so the composer puts
the glass there. Still people are baked to plain meshes; moving ones
keep their skeleton and a looping motion written in code for every body alike (breathing,
talking, walking). Every surface is named for its role, so every look draws them its own way.
Each description is made once (3 to 4 seconds) and kept in the library by it; a seated
person's origin is under their hips and their seat height is measured, so they are sat on any
chair.

A particular person (`who`) is the library's own model of them, made once with the director's
sign-off: a figurine model sheet from the image model, then a multiview image-to-3D service
with a rig (about $1, the only paid step in 3D). The Kushner figure was made this way.
Without MPFB, people are the engine's simple figurines.

## Composing: placing everything

`staging/compose.py` builds the room on a rehearsal stage (so its marks, surfaces, furniture
and every solid piece are known), resolves each thing, and places every copy by its relation,
in dependency order (a glass after the man it stands before): on a surface inside its edges,
stacked, in a row, beside, in front of (reaching a nearby table: a glass before a seated man
lands on the table), round a table, in the room's seats then in chairs drawn up, against a
wall facing into the room, or at a mark. Every copy is kept clear of every piece of the set
and of everything placed before; one with no room is left out and said. Copies are a named
group, so a camera move frames them all and an action is given to each in turn. The result
is an ordinary job of `put` actors.

People in a group are made different, as a room of real people is: what the scene leaves open
(age, build, what their hands do) is filled per copy from short lists (`NATURAL`, `AGES`,
`BUILDS` in `compose.py`) in a seeded order, so no two neighbours do the same thing; each is
turned a few degrees off square (`SWAY`) and starts breathing at a different moment. A thing
`held_by` people decides their activity (a glass: drinking; papers: reading; a pen: writing; a
phone: on the phone, by the words in `HELD`), and it is placed at their hand, one per holder:
three glasses held by eight men are three men drinking, not eight hands round eight cups.
A held thing hangs from its holder (`put`'s `held_by`), so it moves with them and the audit
counts it as part of them. A person's room is measured round their real middle (`middle`: a
seated person's knees and arms reach forward of their hips), so nothing is set under their
hands. Low pieces of a set (up to `STEP`, 0.3 m: a pavement, a kerb) are ground to stand on;
whatever is put at a mark stands on the ground there, never on a chair under a window; and a
long thing that does not fit across a place lies along it (a car on a road).

## Commands

| You want | Run |
|---|---|
| every block and model, with their settings | `content staging catalogue [--config themes/<name>/config.json]` |
| the models, or those matching some words | `content staging models "desk lamp"` |
| check or preview a shot: a job file, or a scene's description | `content staging check shot.json`, `content staging preview shot.json [--frames 1,60] [--scene] --config …` |
| a model from every source, drawn side by side | `content staging find "typewriter" --config …`, then `--take N --as typewriter --about "…"` |
| a version of a model | `content staging vary red_ballot_box --from box --paint card=brick --height 0.5 --about "…" --config …` |
| add a file you downloaded | `content staging add chair.glb --as side_chair --about "…" --licence CC0 --source "…" --config …` |
| keep or turn down a model taken automatically | `content staging keep <id>`, `content staging veto <id> --why "…"` |
| where a model came from | `content staging history <id> --config …` |
| another word for a model | `content staging name side_chair "dining chair" --config …` |
| what scenes could not be staged for | `content staging backlog --config …` (`--find`: search for every model wanted) |
| install people, Infinigen, the Objaverse index | `content staging people`, `content staging infinigen`, `content staging objaverse` |
| start a new block | `content staging new action pour_drink [--channel --config …]` |

`preview` renders into `.cache/staging/` (gitignored) and prints the contact sheet's path;
`--scene` also saves the built scene as a `.blend`. With `--config`, the shot is drawn in the
channel's look; a description without one is drawn the starter kit's way.

## What there is

`content staging catalogue` lists every block and setting; this is the shape of it.

| Kind | Blocks | Built on |
|---|---|---|
| layouts | `room`, `office`, `boardroom`, `corridor`, `street`, `studio`, `open_ground`, and `set` (any hand-built set from the library) | `sets.room` (walls, window, blinds, door), `sets.ground`; each layout names its marks and paths |
| actors | `put` (exactly where the composer worked out, playing a motion), `prop` (on a mark), `stack`, `vehicle` (on a road), `picture` (an image on a card) | `sets.stand`, `sets.moved` |
| actions | `travel`, `drive`, `slide`, `turn`, `scatter` (falling sheets, onto clear spots), `topple` (real physics) | `motion.travel` |
| moves | `orbit`, `dolly`, `pan`, `track`, `fly`, `hold`, `vertigo` | `camera.film`, `camera.around` |
| lights | `lamp`, `window`, `overhead`, `studio`, `headlights`, `streetlights`, `sky` | `lighting.source`, `lighting.flicker` |
| transitions (rendered joins) | `dissolve`, `flow`, `zoom_through`, `swirl`, `fractal_dive`, `shatter_dive`, `kaleidoscope`, `dots`, `melt` | `patterns` on the `Canvas` verbs |
| props (made in code) | 35, families among them (cup, glass, bottle, box, table, book, building), and standing and seated figurines | `shapes`, `shapes_figure` |
| looks | `plain`; the starter kit's `starter`; a channel's own | `Plain` |

The theme's camera moves (`visual.camera_moves`) are 3D moves too: `staging.moves` in
`theme.json` maps each to a move block and its settings.

## Transitions: morphs drawn in Blender

`production.joins: "rendered"` replaces the paid AI morphs with transitions drawn in Blender
from the two pictures, free, for keyframe and staged channels alike. Each is a small program
on the frame, written with the `Canvas` verbs (`canvas_api.py`) and built as a GPU shader
(`canvas.py`). Tests record the program instead (`rehearsal.RecordingCanvas`).

| | |
|---|---|
| which transition | the storyboard's choice (a scene's `transition`), or the theme's `staging.joins`: `slow` for a small change of feeling, `swift` for a large one |
| moving through | a join between staged scenes plays over both shots' frames |
| on top | the same ffmpeg morph effects as AI morphs, then the texture |
| cost and time | free; about half a second a frame at 360×640 on this laptop |

The fractal dive is the Droste effect in motion: the frame opens into copies of itself, wound
into a spiral that flows inward; copies of the next picture arrive at the edge ring by ring.

## A continuous video

With `pictures: "staged"` and `joins: "rendered"`, a video is one moving picture: every staged
scene is a rendered shot, every join plays over the moving frames on either side, and the
breathing, colour and texture run over the whole cut. Scenes nothing can stage are drawn
keyframes; one continuous camera move between scenes in the same place (a `travel` join) is
not built yet.

## Custom sets, built by hand

A place the layouts do not cover can be built once in Blender, or downloaded, and used by name
with the `set` layout. Name its parts and they become what shots refer to:

| Name in Blender | Becomes |
|---|---|
| an empty `mark_<name>` | a mark, facing the empty's −Y |
| a mesh `surface_<name>` | a mark on its top: things stand on it |
| empties `path_<name>_0`, `path_<name>_1`… | a path through them in order |
| any object `actor_<name>` | an actor moves and lights can refer to |
| a box `interior` | the space the camera stays in; it is not rendered |

Export it as `.glb` and add it like any model (`content staging add set.glb --as vault …`).

## Looks: the channel's style, kept separate

A look decides how everything is drawn: a material for each role (wood, paper, metal, bulb…),
a material for pictures, anything it adds to every solid (`dress`: an outline), the world,
and the tone. It is the one kind of block that uses Blender's API. The theme names it, and its
settings are the feel:

```json
"staging": {"look": "starter", "look_settings": {"exposure": -0.3, "saturation": 0.75,
            "contrast": "Medium High Contrast", "shadow": "night", "glow": "sun"}}
```

The starter kit's look (`themes/starter/blender/looks/starter.py`) is the template. A
channel copies it into its own `blender/looks/` and changes what it draws.

## Quality: what is checked, and when

| Check | When | Catches |
|---|---|---|
| the shot check | before anything, without Blender | unknown blocks or models, settings out of range, names not in the shot, a relation's missing target, an action given an actor that cannot do it |
| placement | as the shot is composed | things passing into each other or out of the room: never placed so; a thing with no room where it was asked is a problem the Visual Director is told ("room: no space for …") |
| every prop | every test run | each stands on its base (or hangs from its top) |
| inside the set | every camera position | the camera behind a wall: it stays in the layout's `interior` |
| the look at each still | every staged keyframe | what is physically wrong as a vision model sees it (a hand not touching what it holds, floating or interpenetrating things, impossible poses): the shot composed again with a new seed |
| the audit, before rendering | sampled frames | the camera inside a solid thing, the subject hidden, the camera turning faster than 20° a frame, and two separate things passing into each other by more than 1 cm (3 cm for a moving character). A failing audit stops the render; in a run, the scene is then drawn instead |
| a model taken automatically | as it is found | scored by eye; under 0.5 it is not taken |
| stills and contact sheet | `preview` | composition, light, scale |
| block snapshots | every test run | any change to what a block builds |

## Extending it

A new block: `content staging new <kind> <name>`, fill in its docstring, settings and `build`
using `Stage` verbs; the tests and the catalogue pick it up. A family is a prop with settings
read as `self.p`. A new source is a class with `search` and `download` added to
`providers/sources.py`. `.claude/skills/staging/SKILL.md` is the assistant's guide.

Rules the tests enforce:

- A block file defines one block; its docstring says what it is.
- A setting that names a model is a `ModelName`: checked, and its file sent with the shot.
- Blocks use `Stage` verbs and the shared helpers, never Blender's API; only `stage.py`,
  `canvas.py`, `worker.py`, `audit.py`, `ingest.py`, `imports.py`, `person.py`,
  `generate.py` and looks import it, and nothing outside `content/blender/` imports those.
  What the Blender and rehearsal stages keep alike is written once (`bookkeeping.py`).
- Every block's example is built on a stand-in stage and compared with a snapshot; renew one
  on purpose with `UPDATE_SNAPSHOTS=1 pytest -k <name>`.
- A verb is added to `Stage` (`api.py`) only when a new block needs it.

Conventions: metres and seconds; +Z up; a thing's front faces −Y; camera angles are degrees
round from the subject's front, anticlockwise from above.

## Measured on this laptop

Intel i7-10710U with integrated graphics, Blender 5.2.2, 540×960 stills: building a shot
0.1–3 s, rendering 2–15 s a frame (a room of 30 things and eight people about 14 s). A person
is made in 3–4 s, an Infinigen object in 2–3 s, a found model prepared in about 10 s; a scene
with two things to find took 88 s the first time and nothing after. A full-size final wants a
real GPU.

## Licence

Code that uses Blender's API is a derivative of Blender, so those files (marked
`GPL-3.0-or-later` in their first line: `stage.py`, `canvas.py`, `worker.py`, `audit.py`,
`ingest.py`, `imports.py`, `person.py`, `generate.py`, and looks) are GPL; everything else
stays MIT (`LICENSE`). MakeHuman's assets are CC0; what Infinigen makes is the channel's own;
CC BY models are credited with the video. Renders belong to whoever makes them.

## Installing

| What | How |
|---|---|
| Blender 5.2 LTS | from [blender.org](https://www.blender.org/download/lts/); on macOS set `BLENDER=/Applications/Blender.app/Contents/MacOS/Blender` in `.env`, on Linux put it on the path or set `BLENDER` |
| scoring candidates | the `vision` extra (CLIP is fetched once, ~600 MB) |
| COLLADA models | the `models` extra |
| people | `content staging people` |
| Infinigen | `content staging infinigen` (needs `uv`) |
| Objaverse index | `content staging objaverse` |
| Sketchfab, Poly Pizza | free keys in `.env` (`SKETCHFAB_API_TOKEN`, `POLY_PIZZA_API_KEY`) |

`content check` reports each.

## Not built yet

| Step | What |
|---|---|
| richer motions | motion capture (CMU) retargeted onto made people; gestures that move to and from what they hold |
| carrying while walking | a walking person holding a folder or a briefcase (holding is posed for seated and standing people only; a thing `held_by` a walker is set down in front of them) |
| a particular face on a made person | a likeness from reference photos on the parametric body |
| `travel` joins | one camera move between two framings of a shared set |
| cloud rendering | finals on a rented GPU; this laptop takes seconds a frame |
