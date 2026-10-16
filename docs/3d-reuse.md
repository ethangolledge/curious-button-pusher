# 3D That Is Cheap, Reused and Good: the Plan

Last reviewed: 2026-10-16. Status: being built. Done: the SAM 3D cloud job
([../cloud/sam3d/README.md](../cloud/sam3d/README.md), not yet run on a GPU) and
[designs](#designs), with their free checks and their 3D models in one GPU batch. Next: the
first GPU run, then 3D models in shots.

How the channel should use Blender and the SAM 3D models so that each thing is made once,
reused wherever it recurs, checked cheaply before money is spent, and still looks as good as
the keyframes. Being cheap must never mean paying twice: a poor result that has to be redone,
or a review wasted on it, costs more than doing it right once.

## What we learned

| Tried | Verdict | Why it failed |
|---|---|---|
| code-built grey scenes and people (2026-10-11) | "looks like a 3 year old made it" | none of the keyframe's look or character |
| stock library models placed by a survey, the keyframe projected onto them (2026-10-12) | "horrendous", "a blob lizard" | a stock model never has the drawn shape, so the picture smears across it |
| flat cut-outs from the picture | "not much of an improvement" | no depth to the things themselves |
| the keyframe lifted into depth and moved (picture shots) | the current way | frame one *is* the picture |

**The rule that follows:** whatever the viewer sees must be either the picture itself, or made
from the same source the picture was made from. Reuse the *identity* of a thing (what it looks
like), never someone else's pixels or a stock shape.

## The idea in one paragraph

Each thing that recurs in a story (a person, an object, a place) is designed once: a reference
picture, approved by the director. Every keyframe it appears in is drawn *with that reference*
(the keyframe step already passes reference pictures to the image model). When a shot needs it
in real 3D, its model is made once, from the same reference, with SAM 3D, and kept in the
channel's catalogue. Because the pictures and the model come from one source, they agree, and
putting one with the other works. Everything that does not need 3D stays a lifted picture,
which is free.

## Designs

*Built.* The first piece of reuse, and the one everything else stands on.

**In a run, by itself.** When the reference photos are chosen (`production/stages/references.py`),
every person, place or object the storyboard names in `design_min_scenes` scenes or more
(default 2) gets a design: one picture of it alone, in the channel's look, drawn from its photos
(`visual.design_template`, `visual.design_views`: a person standing whole on plain grey, an
object whole on plain grey, a place wide and empty). Gemini describes it and Jev checks two
things with a right answer: is it alone and whole as the view asks (`design_view`), and is it
the thing asked for (`design_matches`). A design that fails is drawn once more, differently;
if that fails too, keyframes are drawn from the photos as before. Every keyframe showing it is
then drawn with the design first among its references, so it looks the same in every scene.

**Kept with the channel** (`themes/<name>/designs/`, saved to the bucket with everything else):
a later video that names the same thing reuses its design for nothing. A design is known by
what it is (`object-brass-lamp`: capitals, punctuation and "the" do not matter) and by the look
it was drawn in; when the channel's look changes, it is drawn again in the new one.

| You want to | Run |
|---|---|
| see the designs | `content designs list --config themes/<name>/config.json` |
| turn one down (drawn again, differently, when next needed) | `content designs veto <design-id> --config …` |
| see which are ready to become 3D, for free | `content designs model --config …` |
| make their 3D models (paid: one GPU job per model kind, every design in it) | `content designs model --go --config …` |

**Before the GPU, for free** (`staging/designs.py`): each design's subject is found and outlined
on this computer (Grounding DINO, SAM 2). It is sent only if it was found clearly (confidence
0.5; on real keyframes a person scored 0.84 and a lamp that was not there 0.40), fills between
2% and 90% of the picture, is clear of the frame's edge, and is in one piece. On three real
keyframes all three were held back (things in a full scene run off the edge): exactly why
designs are drawn alone on plain grey. A person goes to SAM 3D Body with their box, an object to
SAM 3D Objects with its outline; each model comes back as `designs/<design-id>.glb`. Places stay
pictures: they are lifted, not modelled.

## The shot ladder: the cheapest shot that does the job

| Rung | Shot | Cost per scene | When |
|---|---|---|---|
| 0 | the keyframe, with a slow move | free | nothing needs depth |
| 1 | **picture shot**: the keyframe lifted into depth, camera glides, people breathe ([picture-shots.md](picture-shots.md)) | free (laptop) | the default: push in, pull out, drift, a small arc |
| 2 | picture shot **plus one or two SAM 3D things** in front of the lifted backdrop | about 3–15 cents of GPU, once | the camera goes round a foreground thing, or a thing must move or be picked up |
| 3 | **a reused set**: a recurring place built once, filmed from many cameras | GPU once per place; later shots free | a place in three or more scenes |
| 4 | action painted by a video model, guided by Blender's passes | $0.05–0.17 a second | someone must act (walk in, turn, hand over); the director signs off |

Code chooses the rung from the storyboard, not a model: how far the camera goes against what a
lifted picture can hold (`glide.AMOUNTS`), whether the scene's description has a thing moving
or being handled, and how many scenes share a person, thing or place. It is deterministic,
free, and the director can see why.

## What is kept, and how it is reused

Three kinds of thing, in the channel's own catalogue (`staging/catalogue.py`, with lineage:
every model knows what it was made from):

| Kind | Made once | Reused as |
|---|---|---|
| **cast** (a recurring person) | a reference sheet (front, side, back on a plain background), one image-model call, about 5–10 cents; a SAM 3D Body model only if a rung 2 or 4 shot needs it | a reference for every keyframe they appear in; their model in every 3D shot |
| **prop** (a recurring object) | a reference picture; a SAM 3D Objects model when needed | the same |
| **set** (a recurring place) | a wide reference picture, lifted; SAM 3D for its main furniture; saved as a named scene (a `StagePlan`: data, not a `.blend` file) | each later scene there: Blender renders the set from the new camera (free) as a *layout guide* for the image model, with the cast and prop references, so the new keyframe keeps the room's geography and the channel's look; that keyframe is then lifted (free) |

The set row is "3D for consistency, picture for look": the gray-box-then-reskin pattern AI
previsualisation tools use (see *Research* below). The raw render is never shown; the image
model repaints it.

**Never pay twice**, extended: every SAM 3D result is cached under the hash of what made it
(picture, mask, model revision, seed), like every other paid asset. A cast member made for one
video costs nothing in the next: the catalogue belongs to the channel, not the run.

**Is this the same thing we already have?** A local image embedding (free) finds the
candidates in the catalogue; one cheap check (below) confirms; when unsure, the director
decides. Nothing is reused on a guess.

## Checks: code first, Jev second, the director last

**Jev reads text, not pictures.** Gemini Flash describes a picture (about half a cent), then
Jev answers fixed questions about that description (a fraction of a cent each). One description
answers many questions, so a picture's checks cost about a cent in all. Ask Jev only questions
with a right answer; taste belongs to the director.

| When | Code (free, exact) | Jev (cheap, objective questions) |
|---|---|---|
| **before the GPU** (is this worth sending?) | the mask's size; whether it touches the frame's edge; how much another mask covers it; whether it is one piece | "Is the [thing] shown whole, not cut off by the frame?" "Is it partly hidden behind something?" "Is there exactly one [thing]?" For a reference sheet: "Is it on a plain background?" "Are the front, side and back all shown?" |
| **after the GPU** (is the model right?) | render the model from the picture's own camera and compare its outline with the mask (the strongest test: it must overlap closely); the mesh is one piece with no large holes; its size agrees with the picture's measured depth | on a four-view turntable render: "Is the object complete from every side?" "Is it the same kind of object as the reference?" "Are there floating fragments?" |
| **reuse** | embedding similarity | "Is the [thing] in this picture the same one as in the reference?" |
| **once per new cast member or prop** | | the director sees its turntable: taste is theirs |

A gate costs under a cent, a wasted GPU run 3–15 cents, a wasted review the director's time;
each check sits before the next more expensive step. New Jev questions are measured on known
good and bad cases before they may block anything.

## Keeping the GPU off

- **One job per video, not per scene.** After the storyboard is signed off, every rung 2 and 3
  thing in the whole video is gated and sent together: one cold start (about a minute).
- **Never twice:** the hash cache, and the catalogue across videos.
- **Only what moves goes 3D.** The backdrop stays the lifted picture.
- **Previews on the laptop**, at low resolution and few samples; the final render once, after
  sign-off.

## Where each piece lives (the layers already enforced)

| Part | Job | Change |
|---|---|---|
| `providers/sam3d.py` | the GPU job | built; another generator (TRELLIS.2, Hunyuan3D, MIDI-3D) would be another model behind the same request format |
| `staging/resolve.py` | finding or making each thing | a new first source, "made from its reference", and stock sources no longer used for anything that appears in a picture |
| `judging/questions.py` | Jev's fixed questions | the gate, accept and reuse questions above |
| `blender/` | the foundation | unchanged: a `.glb` is a model file like any other |
| the channel's catalogue | cast, props and sets with lineage | the three kinds above |

## Build order: each step shown working on one scene before the next

1. **First GPU run** (needs the steps in the SAM 3D README): `content designs model --go` on the
   first designs a run makes, one object and one person. Shows a turntable; measures memory,
   time and cost. Go or no-go for everything below. About 25 cents.
2. **The outline check against the picture's camera** (code, free). *The checks before the GPU
   are built (designs); a design is modelled once, so it needs no cache key of its own.*
3. **The gate and accept questions**, validated on ten known cases before they block.
4. **Rung 2 in a real run**: a picture shot with one SAM 3D thing in front of the lifted
   backdrop. A clip shown to the director early.
5. **Designs** *(built)*: recurring people, places and objects drawn once and every keyframe
   drawn from them. Still to measure: consistency across scenes ("the same person?").
6. **Sets (rung 3)**, once a story has a recurring place.
7. **Rung 4 last**, for action only, with sign-off.

## What it should cost (estimates until step 1 measures them)

For a 20-scene video, on top of today's keyframes and morphs: most scenes on rungs 0–1 ($0);
four on rung 2 (about 40 cents); one set (about 15 cents); two cast sheets (about 20 cents, the
first time only); checks (about 10 cents). **About 85 cents the first video, less after**,
plus about $2–4 a month for storing the image and the models.

## Not doing, and why

| Not | Why |
|---|---|
| stock models fitted to pictures | rejected on screen (above) |
| a whole 3D scene for every scene | dear, and the picture looks better |
| Gaussian splats in final renders | Blender has no native splat renderer (add-ons approximate one); SAM 3D gives a mesh too, which renders in the channel's look |
| MIDI-3D first | whole scenes from one image (Apache-2.0) but about 30 GB of GPU memory when textured; a candidate to compare for sets later |
| our own generator or training | published models do it |

## Research

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
