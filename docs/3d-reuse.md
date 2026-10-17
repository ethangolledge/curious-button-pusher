# 3D That Comes Together: Layouts, Designs and Moving Pictures

Last reviewed: 2026-10-16. How a channel uses Blender, its catalogue and the image and video
models so that a story's places and people stay the same from scene to scene, everything is
made once and reused, money is spent only where it shows, and every frame looks as good as the
keyframes. Built: [drawing over a layout](#drawing-over-a-layout), [designs](#designs),
backdrops, the SAM 3D cloud job (not yet run on a GPU). Still to come: [below](#still-to-come).

## What we learned

| Tried | Verdict | Why it failed |
|---|---|---|
| code-built grey scenes and people (2026-10-11) | "looks like a 3 year old made it" | none of the keyframe's look or character |
| stock library models placed by a survey, the keyframe projected onto them (2026-10-12) | "horrendous", "a blob lizard" | a stock model never has the drawn shape, so the picture smears across it |
| flat cut-outs from the picture | "not much of an improvement" | no depth to the things themselves |
| the keyframe lifted into depth and moved (picture shots) | kept: how every picture moves | frame one *is* the picture |
| a 3D layout drawn over by the image model (2026-10-16) | the way 3D is used | the layout holds (box overlap 0.84–1.0), the look and likeness are the drawing's |

**The rule that follows:** whatever the viewer sees is a drawing by the image model, made from
the channel's own references. 3D decides where things are, never how they look. Reuse the
*identity* of a thing (its design) and the *geography* of a place (its layout), never someone
else's pixels or a stock shape on screen.

## Drawing over a layout

*Built.* **3D is the structure, the image model is the look.** A staged scene
([staging.md](staging.md)) is described by the Visual Director as data (`StagePlan`: the room,
the things and where they go, people and their poses, lights, the camera); code composes it
from the catalogue's blocks and models, clear of everything; and Blender renders it once, from
where its camera starts, in the `guide` look (`blender/blocks/looks/guide.py`: grey clay, a
shade per kind of surface, ink outlines, soft light; free). The image model draws the keyframe
over it: the guide first, told by the theme's `visual.repaint_note` to keep its camera, framing
and placing and never its grey 3D look, then the scene's designs and photos. The picture is
judged like any keyframe and also looked at for what is physically wrong; a layout that fails
its checks, or a picture with something physically wrong, is composed again with the next seed;
a layout that never builds is drawn from words. Then the picture moves as a
[picture shot](picture-shots.md).

```
storyboard scene ── StagePlan (the Visual Director writes data, never Blender code)
      │  free check: blocks, settings, names, the shot composed (staging.plan.staging_issues)
      ▼
compose (staging/compose.py): every thing from the catalogue (designs, the library, families,
      made people, free sources), placed by its relation; backdrops beyond the space
      ▼
the guide (Keyframes._guide): one still in the guide look; the audit (overlaps, camera)
      ▼
the keyframe: the image model draws over the guide, with designs and photos (~5 cents)
      │  measured (tone, colour), described (Gemini), judged (Jev), physically checked
      ▼
the picture shot: the keyframe lifted into depth, the camera glides, people breathe (free)
      ▼
joins (AI morphs or rendered transitions) and the cut, as for any scene
```

Why it works: a mesh's flaws stop mattering, since only its shape and place are used; plain
blocks are enough (a 150 m tower behind a street of grey boxes came out as a lit glass tower
over stone fronts, the layout kept); and because the layout fixes where everything is, the
same room drawn from two cameras stays the same room. Tested on a real scene from an angle its
keyframe never showed: boxes round the man, the desk and the lamp overlapped the layout's by
0.84 to 1.0 in all three pictures, in the channel's look and the keyframe's likeness, for 4.8
cents each.

**Consistency, scene to scene.** Three things are shared: the *layout* (the Visual Director is
asked to stage every scene in a recurring place with the same layout and things, changing only
the camera and what moved), the *designs* (the same reference picture for a person or object in
every picture), and the *theme* (the same style prompt and checks).

## Designs

*Built.*

**In a run, by itself.** When the reference photos are chosen (`production/stages/references.py`),
every person, place or object the storyboard names in `design_min_scenes` scenes or more
(default 2) gets a design: one picture of it alone, in the channel's look, drawn from its photos
(`visual.design_template`, `visual.design_views`: a person's turnaround sheet, standing whole,
front and profile, on plain grey; an object whole on plain grey; a place wide and empty).
Gemini describes it and Jev checks two things with a right answer: is it alone and whole as the
view asks, once from each side it asks for (`design_view`), and is it
the thing asked for (`design_matches`). A design that fails is drawn once more, differently;
if that fails too, keyframes are drawn from the photos as before. Every keyframe showing it is
then drawn with the design first among its references, so it looks the same in every scene.

**Kept in the channel's catalogue** (`themes/<name>/assets/`, saved to the bucket with everything
else): a design is a model like any other (`library.Identity` says what it is and holds its
drawing), so it is kept, turned down and traced the same way, and a later video that names the
same thing reuses it for nothing. It is known by what it is (`object_brass_lamp`: capitals,
punctuation and "the" do not matter) and by the look it was drawn in; when the channel's look
changes, it is drawn again in the new one. No shot can use a design until its 3D model is made:
a flat drawing in a 3D shot was turned down.

**A channel's own characters** (`visual.cast`: a name and what the character is drawn as) are
designs too, but never searched for: a storyboard names one (a mascot standing for ordinary
people, say), the request is relevant without photos, and the character is drawn from its
description, even if it is in only one scene. A drawing the person approved is kept as the
character's design with `content staging cast`; it is drawn again only if the look changes.
In a staged shot the character is posed like any other person (`docs/staging.md`, People):
the skeleton says how they stand, the design what they look like. The design shows their
usual clothes; a scene that needs others (overalls, a uniform) says so in its anchor.

| You want to | Run |
|---|---|
| see the designs | `content staging designs --config themes/<name>/config.json` |
| keep an approved drawing as a cast member's design | `content staging cast <name> <drawing.png> --config …` |
| turn one down (drawn again, differently, when next needed) | `content staging veto <design-id> --why "…" --config …` |
| see how one was made | `content staging history <design-id> --config …` |
| see which are ready to become 3D, for free | `content staging model --config …` |
| make their 3D models (paid: one GPU job per model kind, every design in it) | `content staging model --go --config …` |

**Before the GPU, for free** (`staging/designs.py`): each design's subject is found and outlined
on this computer (Grounding DINO, SAM 2). It is sent only if it was found clearly (confidence
0.5; on real keyframes a person scored 0.84 and a lamp that was not there 0.40), fills between
2% and 90% of the picture, is clear of the frame's edge, and is in one piece. On three real
keyframes all three were held back (things in a full scene run off the edge): exactly why
designs are drawn alone on plain grey. An object goes to SAM 3D Objects with its outline; its
model comes back, is brought into the library's form (upright, in metres, facing −Y) like any
model taken in, and becomes its design's file. A person is never made as a mesh at all:
in a layout every person is a pose of real recorded motion, drawn over it as a skeleton
([staging.md](staging.md#people)), and the image model draws them from it and from their
design. Places stay pictures: they are lifted, not modelled.

## How a scene is made to move

| Shot | Cost | Status |
|---|---|---|
| the keyframe moved by ffmpeg (`pictures: "keyframes"`) | free | built |
| **picture shot**: the keyframe lifted into depth, the camera glides, people breathe | free (laptop) | built: every keyframe of an `animated` or `staged` channel |
| picture shot plus one or two SAM 3D things before the lifted backdrop (the camera goes round a thing, a thing is picked up) | 3–15 cents of GPU, once per thing | to come: needs the first GPU run |
| **action**: Blender plays the action on the layout's stand-ins and renders depth and pose; a control-video model (Wan 2.2, on our own Cloud Run GPU job, like SAM 3D) draws it from the keyframe | to measure; the director signs off each | to come |

Which shot a scene gets will be chosen by code from the storyboard (how far the camera goes
against what a lifted picture can hold, whether something is handled or someone acts) once
there is more than one to choose from; it is not built before then.

## Checks: code first, Jev second, the director last

**Jev reads text, not pictures.** Gemini Flash describes a picture (about half a cent), then
Jev answers fixed questions about that description (a fraction of a cent each). Ask Jev only
questions with a right answer; taste belongs to the director.

| When | Code (free, exact) | Jev and the vision model (cheap) | Status |
|---|---|---|---|
| a layout, before Blender | blocks, settings, names, the shot composed | | built |
| a layout, in Blender | things passing through each other, the camera inside something | | built |
| a picture drawn over a layout | tone and colour against the feeling | what is physically wrong; does it show the scene | built |
| a design | | alone and whole as asked; the thing asked for | built |
| before the GPU | the mask's size, the frame's edge, one piece | | built |
| after the GPU | the model's outline from the design's camera against its mask; one piece, no large holes | a four-view turntable: complete, the same kind of thing, no fragments | to come, validated on known cases before it blocks |

## Still to come

1. **First GPU run** (the director's steps in [the SAM 3D README](../cloud/sam3d/README.md)):
   `content staging model --go` on one object design; measure memory, time and cost. About 25
   cents.
2. **SAM 3D models as stand-ins**: a design's mesh in the layout in place of a stock prop, so
   the guide carries its true shape; the after-GPU checks. People stay poses.
3. **Action**: the Wan control job on Cloud Run (the SAM 3D job's pattern, its shared parts
   moved into one provider), Blender's depth and pose passes, the director's sign-off per shot.
   People's poses already move frame by frame from free recorded motion
   ([staging.md](staging.md#people)): the pose control it takes.
4. **Places kept across videos**: a recurring place's layout saved in the catalogue, so a later
   video's scene there starts from it.
5. **The starter kit**: the guide look and `repaint_note` are already theme data; anything new
   follows them.

## What it costs (measured 2026-10-16)

| Thing | Paid |
|---|---|
| a layout, its guide, the checks, lifting and moving the picture | free (laptop) |
| a picture drawn over a layout | 4.8 cents, the same as any keyframe |
| a design | about 5 cents, once per channel |
| a SAM 3D model | estimated 3–15 cents, once per thing |

## Not doing, and why

| Not | Why |
|---|---|
| a raw 3D render on screen | turned down twice; the drawing looks better and keeps the look |
| stock models fitted to pictures | rejected on screen |
| an agent writing Blender code (an MCP bridge to Blender) | the agent describes, code builds from tested blocks: repeatable and checkable |
| city models from map data | blocks drawn over are enough |
| Gaussian splats in final renders | Blender has no native splat renderer; SAM 3D gives a mesh too |
| MIDI-3D first | whole scenes from one image but about 30 GB of GPU memory; a candidate for places later |
| our own generator or training | published models do it |
| non-commercial motion data | the channel publishes |

## Research

- Rendering depth (and other passes) from a 3D scene to guide an image or video diffusion
  model, so the look comes from the model and the structure from 3D:
  [Generative Rendering](https://arxiv.org/pdf/2312.01409); scene graphs written as Blender
  code from a library of functions, checked by a vision model:
  [SceneCraft](https://arxiv.org/pdf/2403.01248) (our blocks and `StagePlan` are that library,
  with the agent writing data, not code).
- Wan 2.2 (Apache-2.0) animates or replaces a character from a reference picture and a pose
  video, and its Fun Control models take depth and pose control
  ([Wan2.2](https://github.com/Wan-Video/Wan2.2)); the 5B fits a 24 GB L4 with offloading,
  the 14B needs about 80 GB. Hosted VACE depth control costs $0.04–0.08 a second
  ([fal](https://fal.ai/models/fal-ai/wan-vace-14b/depth)); OpenRouter's video API takes first
  and last frames and reference pictures, not a control video
  ([docs](https://openrouter.ai/docs/features/multimodal/video-generation)).
- Motion for people: the CMU motion capture library ("may be copied, modified, or redistributed
  without permission", [FAQ](http://mocap.cs.cmu.edu/faqs.php)) and 100STYLE (100 walking and
  idle styles, CC BY 4.0, credited "The 100STYLE Dataset - Ian Mason":
  [100STYLE](https://www.ianxmason.com/100style/)), and free animated characters on Sketchfab
  (CC BY), read once as poses. Built 3D bodies were tried and dropped (2026-10-17): the image
  model draws a person far better from a pose skeleton than from any body we render.
  Not used: HY-Motion (its licence excludes the UK and EU:
  [issue](https://github.com/Tencent-Hunyuan/HY-Motion-1.0/issues/49)), Bandai Namco and LaFAN1
  (non-commercial).
- Cities: Buildify and blender-osm build streets from map data, with primitive buildings
  ([CG Channel](https://www.cgchannel.com/2022/07/download-free-blender-3d-building-generator-buildify/));
  drawn over, plain blocks were enough (below), so neither is used.
- SAM 3D Objects composes several objects from one picture into a scene with their layout
  (its multi-object notebook); [MIDI-3D](https://github.com/VAST-AI-Research/MIDI-3D) and
  [SceneGen](https://arxiv.org/pdf/2508.15769) do the same in one pass; none keeps a thing's
  identity across pictures, which is why the reference sheet comes first.
- Image-to-3D models guess a thing's hidden sides from one view; front, side and back views
  give consistent geometry ([Hunyuan3D multi-view
  input](https://www.3daistudio.com/Models/Hunyuan3D-3-1)). Hence the reference *sheet*.
- AI previsualisation tools block a shot in grey, then a model reskins it from reference
  pictures; their lessons are to sketch cheap, render only on save, and share one environment
  reference across shots for continuity
  ([genzen research note](https://github.com/joshcoolman/genzen/issues/742)); Blender passes
  (depth, normals) drive video models such as Wan VACE
  ([Wan2GP VACE guide](https://github.com/deepbeepmeep/Wan2GP/blob/main/docs/VACE.md),
  [ControlNet render add-on](https://github.com/x6ud/controlnet-render-blender-addon)).
- Seedream 5 takes several reference pictures and keeps a character's identity across them
  ([Seedream 5.0 overview](https://artlist.io/blog/new-seedream-5-0-announcement/)).

## Notes from building the SAM 3D job (2026-10-16)

- **Why it took long.** No video tests ran (`pytest -m video` was not used). The time went on
  reading both models' code to install only what they use, and on building the container on
  the laptop four times: each build downloads about 10 GB and compiles the 3D libraries for the
  GPU (30–60 minutes). Two builds died on network drops; two found real faults that would
  otherwise have failed in the cloud (the MoGe version the authors pin has no v2; Lightning
  needs a setuptools older than 81). From now on the build runs on GitHub's machines,
  unattended; a change to the container takes about an hour there because each build starts
  clean.
- **Where it stands:** the image builds, runs as a non-root user, holds no secrets, and every
  import the models need passes; a hostile request (`../../etc/passwd`) is refused inside the
  real container. It has not run on a GPU: the first run decides whether the L4's 24 GB is
  enough for SAM 3D Objects (its authors ask for 32 GB).
