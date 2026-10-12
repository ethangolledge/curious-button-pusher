# Picture Shots: the Keyframe, Animated in Blender

Last reviewed: 2026-10-12

A picture shot starts from a scene's approved keyframe (the image model's picture) and moves it
in Blender. The picture is the shot: frame one is the keyframe, and everything that moves is
the picture's own content lifted into depth. Blender adds what a still cannot: a real camera
move with parallax, and people who breathe. A channel turns it on with
`production.pictures: "animated"` ([configuration.md](configuration.md)); nothing changes for
a channel that does not. Code-built 3D shots ([staging.md](staging.md)) are separate: they
build scenes nobody has drawn.

## Why this way

A code-built scene is only as good as its models; a picture from the image model already has
the channel's look, light and characters. The established way to move a still in film and
documentary work is camera projection (a 2.5D shot): the picture projected from its own camera
onto rough geometry, what is hidden behind the foreground painted in, the camera moved a little.
Its single-image form is "3D photography" (Shih et al., CVPR 2020: cut the picture at its depth
edges, paint in a band behind each). Published models now do each step from one image:

| Step | Model or tool | Licence | Gives |
|---|---|---|---|
| geometry | MoGe-2 (Microsoft, `Ruicheng/moge-2-vitl-normal`) | MIT | a point in metres for every pixel, and the picture's focal length |
| who is in it | Grounding DINO tiny (also the focal point's detector) | Apache-2.0 | a box for each person |
| their outlines | SAM 2.1 large (Meta, in `transformers`) | Apache-2.0 | a mask inside each box |
| how they stand | ViTPose base (in `transformers`) | Apache-2.0 | 17 body points each (COCO order) |
| what is behind | LaMa (`Carve/LaMa-ONNX`) | Apache-2.0 | the picture painted in where a person or a near edge stood |
| the shot | Blender: meshes from points, an unlit image material, armatures with automatic weights (bone heat), NLA strips | GPL | the moving picture |

All run on this computer for free (`providers/vision.py`; a GPU is used when there is one).
Install with the `vision` extra after PyTorch and torchvision's CPU builds
(`pyproject.toml` says how).

## From picture to shot

1. **Lift** (`staging/lift.py`, outside Blender, cached in the channel's library as a set):
   - geometry and lens from MoGe-2; the lens is 36 mm × the focal length across the longer side;
   - each person found, outlined and posed; their outline's band (`EDGE`, 12 px) takes the
     depth of their solid middle, because the depth model blurs depth across an outline and
     a blurred edge smears as the camera moves;
   - behind each person, the picture painted in (LaMa) over their outline grown by
     `HOLE_MARGIN` (16 px), and depth carried in (OpenCV Telea, in millimetres: on floating-
     point depth it overshoots), never nearer than the person (`BEHIND`, 5 % further);
   - every other depth edge (a chair before the floor, a crowd before the wall): where depth
     changes by more than `EDGE_JUMP` (15 %) across `SHARP` (4) pixels, the blurred ramp is
     snapped to its two sides; on the near side, a band `BAND` (32 px) wide gets the far side
     carried on behind it, painted in by LaMa (each group of holes in its own square, so a
     small hole is filled as sharply as a large one);
   - the background reaches `MARGIN` (6 %) beyond the picture's edges, mirrored there, so a
     move never shows an empty border.
2. **Build** (`blender/lift.py`; a lifted picture is an `.npz` model file, read through the
   importer table like a `.glb`): the background a mesh cut at depth edges (`GROUND_JUMP`,
   10 %), the band behind it a mesh of its own, each person a mesh reaching a little past their
   outline (their picture's soft alpha draws the edge) with a skeleton from their body points
   and two motions on NLA tracks (`breathing`, `talking`, keyed by `rigging.loop`, as made
   people's are). Every surface is unlit and named `painted …`, so no look recolours it. The
   set's parts are `mark_camera` (with its lens), `mark_ahead`, `actor_person_<n>` and
   `interior`.
3. **Shoot** (`staging/plan.picture_job`): layout `set` with the lifted picture and its people's
   `motion`; look `painted` (Standard view transform, anti-aliasing over 0.8 px, so frame one
   is the keyframe); camera `glide` from `mark_camera`, going the way the scene's theme move
   goes (a dolly its direction, an orbit round, anything else barely moving).

In a run, each keyframe is drawn and judged as before; once it passes, it is lifted and its
hold's first, middle and last frames rendered (`Keyframes._animated`). The drawing stays the
scene's picture (its signature, its judgements), so nothing is drawn or paid for twice; the
cut plays the shot in full like any 3D shot, and the morphs meet its first and last frames. A
picture that cannot be animated stays a drawn keyframe, and the gap goes in the backlog.

## How far the camera goes

`glide`'s `amount` is a fraction of the distance to what it films. Unless told, each way has
its own (`glide.AMOUNTS`): in or out 8 %, up or down 5 %, sideways or round 3.5 %; a theme
move that is not a dolly or an orbit drifts 1.5 %. Going in reveals little the picture lacks;
going sideways or round reveals the most.

## Measured on this laptop (2026-10-12, four keyframes of a first production)

| What | Number |
|---|---|
| lifting a 1152×2048 keyframe (CPU) | about 60 to 90 s, once per picture |
| rendering a final frame at 1080×1920 (EEVEE on integrated graphics) | several seconds; a 5 s scene takes minutes (a GPU makes it far quicker) |
| frame one against the keyframe (the desk portrait) | 23.4 dB PSNR, mean difference 6.7 of 255: resampling, not content |
| people found | 1 of 1 (portrait), 3 of 3 (three at a table), 5 (a room of figures), 2 of a dozen (a dark hall of silhouettes) |


## What it can and cannot do

| Can | Cannot |
|---|---|
| push in, pull out, rise, drift, a small arc round the subject, with true parallax | swing round to see what the picture never showed |
| people breathing, a head leaning a little | a person walking across the room, or turning round |
| any picture the image model draws, in its own look | change what the picture shows |

Figures the detector does not see as people (silhouettes in a dark crowd) move with the
background as depth layers, without breathing.

## The next step: action guided by the shot

For a shot where someone must act (walk in, turn, hand something over), the picture shot is the
guide: Blender plays the action on the lifted scene and renders depth and pose passes, and a
video model with control (Wan VACE, Kling motion control, Seedance 2 with a reference video)
paints the action in the picture's look from the keyframe as its first frame. That is a paid
call per scene (about $0.05 to $0.17 a second) and needs the director's sign-off.
