# Visuals: From Storyboard to the Finished Picture

How the pictures are planned, paid for, brought to life and stitched. Paid steps are marked
**($)**; everything else is local ffmpeg and free. The look itself (style, camera moves, motion,
colour) is theme data ([themes.md](themes.md)); values quoted are the starter theme's, or
examples of what a setting could be, and measurements come from a first long-form production
made with this pipeline.

Last reviewed: 2026-10-09.

## The Path at a Glance

```text
Budget            price_pictures: money left after writing → how many scenes it pays for
Storyboard ($)    Visual Director: scenes = anchor + focus + camera + motion + morph bridge
References ($)    Wikimedia photos of real people and places, judged for relevance and match
Narration         (see narration.md) → scene windows
Keyframes ($)     Seedream, one per scene, from the anchor, theme style and emotional field
Checks            colour vs. the field's targets (code); Jev on Gemini's description ($ small)
Focal points      Grounding DINO finds each scene's focus (local, cached)
Animatic          stills only, with real narration, music and subtitles → Pictures sign-off
Morphs ($)        Veo, 4 s from each keyframe into the next
Assembly          glide + breathing stills, camera carried through morphs, local morph layer,
                  continuous texture pass, held ending, subtitles burned in → Final cut
```

## 1. Budget and Storyboard

- **Budget** (`production/budget.py`): a run is capped at `production.max_usd` ($5 in a new channel). Before the
  storyboard, `price_pictures` works out how many scenes the money left pays for, at a keyframe
  (1.5 draws × $0.045 + checks) plus a morph (4 s × $0.03 × 1.3 takes + checks) each, about
  $0.24 a scene. When the person chose a scene count (`--scenes`, at the intake), that is the
  number, never more than affordable; long form morphs every join, so fewer scenes is how a long
  video stays affordable (each picture holds longer, the camera moving within it). The
  storyboard merges scenes to fit; the narration never changes.
- **Frame**: the video's format sets it (9:16 short, 16:9 long). The prompts name it through the
  theme templates' `{frame}` and `{orientation}`; glides, breathing, morph layers, texture and
  subtitles all work from the format's width and height.
- **Storyboard** (Visual Director, `writer` model, `agents/visual_director/prompt.md`). Each scene:
  - `anchor`: subject, setting, composition, key elements, light and colour, and `figure` for a
    public figure (name, likeness, silhouette);
  - **`focus`**: three to eight words naming where the eye lands ("the man at the head of the
    table"); found in the keyframe later, never part of a prompt;
  - `camera`: one of the theme's moves (the starter's: push in, pull out, drift, dolly, rise, orbit;
    a theme can add its own); `motion`: what moves inside the shot;
  - `morph_bridge`: the shape or texture that carries this scene into the next;
  - `reference_ids`: which reference requests it is drawn from.
- **Checks:** Jev on each scene (`scene_duplication`, `scene_meaning`, `scene_concrete`), each
  bridge (`bridge_shared`) and the sequence (`visual_flow`); then the critic. The assistant
  answers the visual-plan review; the person sees the pictures at the Pictures sign-off.

## The Emotional Field

Each scene is a room with one focal point (its anchor), and the room's space, light and motion
follow how its lines land on a listener. Then the space changes, smoothly, into the next room.

1. **Reaction (Jev, measurements):** for every narration unit, what a listener instinctively does
   (`lean_in`, `brace`, `recoil`, `settle`, with probabilities) and how strongly. Gut reactions,
   never verdicts.
2. **Field (code, `story/field.py`):** each scene blends its units' reactions, weighted by how long each
   is heard. Lines resting on anything short of a verified fact are capped, so an allegation never
   gets full-force visuals. The theme's `visual.field` turns the blend into framing, light and
   motion words (never emotion words), and suggests camera moves.
3. **Transitions (code):** the change between two scenes' fields decides how the space moves
   (tunnelling inward as the story tightens, opening as it releases, flowing sideways when little
   changes), swiftly for a big change and slowly for a small one.
4. **Colour (code):** each reaction has a circumplex point in the theme; inverting Valdez and
   Mehrabian's colour-emotion model gives each scene a brightness and saturation target in the
   theme's units (`visual.tone`). Keyframes that miss by more than the tolerance are redrawn
   lighter, darker, richer, warmer or cooler ([machine-learning.md](machine-learning.md#colour-from-emotion-valdez-and-mehrabian-1994)).
5. **Checks:** Jev checks the framing matches (`keyframe_framing`) and that morphs change the way
   their transition asks (`segment_shift`).
6. **Director notes:** `S4: feel brace` sets a scene's field directly; only that keyframe and its
   morphs are redrawn.

## 2. References ($ small)

`production/stages/references.py`, `providers/images.py`.

- Each request (person, place, object) is first judged for relevance to its narration
  (`reference_relevant`); irrelevant requests are never searched again.
- Wikimedia Commons is searched; images under `min_reference_side` are skipped; downloads retry
  on 429 (Wikimedia rate-limits bursts; this once crashed a run).
- Each candidate is described by Gemini and judged against the request (`reference_matches`); the
  best passing ones are **chosen** (`references_per_request`).
- **Chosen photos are saved with the run** (`ReviewHandoff.references`). A resume that searched
  again picked other photos and paid to redraw five keyframes.
- An `R2: wrong building` note at the Pictures sign-off rejects that request's photos for good
  and searches again.
- The best photos go to the image model with the theme's style images, for identity and likeness
  only; everything is still drawn in the theme's style. Licences and authors appear on the story
  sheet. Commons is the only source today; another would be a second `ImageSource` in
  `providers/images.py`.

## 3. Keyframes ($)

`production/stages/keyframes.py` (`keyframe_tasks`, `produce_keyframe`), `theme.keyframe_prompt`.

- **Prompt:** the theme's keyframe template filled with the style, texture, lighting, avoid list,
  the anchor, and the scene's **emotional field** (framing, light, colour temperature, motion
  words from Jev's `unit_reaction`/`unit_intensity` on the scene's lines; see `story/field.py` and
  machine-learning.md "Colour From Emotion"). Public figures are drawn from their reference photos as the
  theme's `visual.figure` template says (or `visual.silhouette` when a portrait is refused).
- **Signature:** model, resolution, prompt, theme references, chosen photo digests. Same
  signature and attempt → cache hit, free.
- **Checks:** brightness and saturation against the field's targets (luma ceiling 55; ±1.5
  standard deviations), then Jev on Gemini's description (`keyframe_matches_anchor`,
  `keyframe_on_theme`, `keyframe_shows_story`, `keyframe_framing`, `keyframe_clean`). A failure
  is redrawn once with fix notes ("darker", "keep it 2D"…). A refused or garbled portrait is
  redrawn as a silhouette.
- **Quirks:** Seedream runs bright; Jev's framing verdicts are often wrong because it reads a
  description, not the picture. Look at the frames before trusting a flag.

## 4. Focal Points (local)

`production/focus.py`, `production/studio.py` (`focal`).

- Grounding DINO finds the scene's `focus` (or, without one, the anchor's first clause) and returns
  a box; the point is its centre, or a third of the way down for a public figure (the face).
- Cached per keyframe and phrase in `.cache/focus/`. Without the `vision` extra, or with no box
  above 0.2 confidence, the point is the frame's centre.
- On a first production: 11 of 11 right with named focus phrases; 8 of 11 with the anchor's first clause
  (checked by eye on a contact sheet with the boxes drawn).

## 5. Bringing Stills to Life (local)

`assemble.glide`, `assemble.motion_clip`.

**The glide** comes from the theme's `visual.camera_moves`: each move's `start` and `end` give a
zoom, how far the view's centre sits from the focal point `(fx, fy)` toward the frame's centre
(`toward_centre`), and an x/y offset. The starter theme's moves:

| Camera | Starts | Ends |
|---|---|---|
| `push_in` | zoom 1.06, halfway | zoom 1.24, on the focal point |
| `pull_out` | 1.24, on the focal point | 1.06, halfway |
| `drift` | 1.16, focal −0.06 across | 1.18, focal +0.06 |
| `dolly` | 1.18, focal −0.10 | 1.18, focal +0.10 |
| `rise` | 1.18, focal +0.08 down | 1.18, focal −0.08 |
| `orbit` | 1.12, (+0.06, −0.04) | 1.20, (−0.06, +0.04) |

A theme adds a move by naming it with a `describe`, a `start` and an `end` (a deep dive, say, from
1.06 halfway to 1.36 on the focal point). The view never leaves the picture, so near an edge the
subject sits off-centre (`landing`).

**Breathing** (theme `visual.motion.breath`): the starter swells the frame by 1% on a 6 s breath
and has no ripples; a theme can add ripples (`ripple_pixels`, e.g. 5 px at 1080 wide) radiating
from where the focal point sits on screen. Both fade in and out with the clip
(`sin(π·progress)`), so a still meets its morphs exactly on its glide. Displacement maps are drawn
at a sixth of the frame size and enlarged (full-size per-pixel maths was many times slower).

**Emotional ripple colour** (theme `visual.motion.breath.tint`, each reaction's
`visual.field.reactions.<reaction>.ripple_colour`): the ripple crests take on the scene's
emotional colour, faintly. Each reaction's colour is blended by how much of the scene lands that
way (`field.ripple_tint`), at an opacity that grows with how strongly it lands, up to `tint` at
full intensity. Only the crests are coloured, fading in and out with the still; the picture
itself is never recoloured, and morphs are untouched. A theme might give each reaction a colour from
its palette (lean in warm, brace cool, recoil a dim red, settle neutral) at most 12%; the starter
has no ripples, so no tint. Changing it re-renders the stills only: free.

## 6. Morphs ($)

`production/stages/segments.py` (`segment_tasks`, `produce_segment`), `assemble.conform_segment`.

Each morph runs from its scene's keyframe (first frame) to the next scene's keyframe (last frame),
so it always lands on a drawn picture and drift can never build up across the video.

- **Veo prompt** (`theme.segment_prompt`): opens on this scene's subject and setting with its
  camera and motion, transforms through the `morph_bridge` and the theme's `visual.morph`
  description, lands on the next scene's subject and setting. Avoid list from
  `visual.morph_avoid`.
- **Checks:** three frames sampled (10%, 50%, 90%), described by Gemini, judged by Jev
  (`segment_keeps_style`, `segment_shift`, `segment_holds_anchor`, `segment_morph`); a failure
  is retried once with fix notes.
- **Refusals:** Veo refuses lifelike real-person close-ups as input. The Pictures review then
  needs the scene redrawn (in shadow, from behind, or as a silhouette). Refusals are cached.
- **The words steer the morph:** Veo does what the theme's `visual.morph` text asks, literally.
  A theme once asked for "a grid of panels that flip over… kaleidoscope… hallucinatory" and got
  exactly that, in neon. Describe the change you want to see (melting,
  dissolving, one shape becoming another) rather than effects; changing the text regenerates
  every morph (~$1.50–3 for a short).

**The local morph layer** (conform, theme `visual.motion.morph`): the camera carries on from the
previous still's last framing to the next still's first (eased), so nothing snaps back. On top,
peaking mid-morph and zero at both ends: liquid warp, light trails (`lagfun`), a mirrored bloom,
colour plates slid apart, a hue swing and extra saturation. A strong setting is 24 px, 0.55,
0.5, 14 px, 1.6 rad and +0.5; the starter switches the layer off (all zero).

## 7. Joining, Texture and Finish (local)

- **Joins** (`dissolve_join`): a still and its morph meet frame to frame (no dissolve, no held
  frame); a held frame there shows as a freeze before each morph. Two
  stills with no morph between them dissolve (`visual.motion.dissolve_seconds`).
- **Texture pass** (`assemble.texture`, theme `visual.motion.texture`), one continuous pass over
  the whole cut so nothing pops at a join: a slowly zooming Mandelbrot set (ffmpeg's `mandelbrot`
  source) blended soft-light in the shadows, a vignette breathing with the stills, colour
  fringing, grain and a light flicker; any layer at 0 is left out. A strong setting is a 22% fractal;
  the starter uses only grain and a slight vignette. With the fractal on, this is the slowest
  step: about 8 minutes for 2:48 at 1080×1920.
- **Held ending:** the last frame holds and fades while the music plays out.
- **Finish:** subtitles burned in (libass, the theme's font), the mix muxed, H.264 CRF 21,
  `faststart`.
- **Final checks:** length vs. the narration timeline (±0.5 s), frame size, and hard cuts at scene
  joins (a join that cuts instead of morphing).

## 8. Cache, Versions and Money

- Paid assets (`.cache/keyframe`, `segment`, `speech`, `reference`, `perception`) are keyed by
  their full request; local derivatives (`still`, `conformed`, `cut`, `held`, `textured`, `final`)
  by their inputs, the theme's motion settings, and the `LOOK` version string in `production/studio.py`.
- Changing the theme's motion settings rebuilds what they affect on its own. **Bump `LOOK`** only
  when the code that renders them changes.
- A morph's signature includes both keyframes' digests: **redrawing one keyframe re-pays the two
  morphs touching it**. Check keyframes are unchanged before approving the Pictures review on a
  resumed run.

## 9. What Changes What

| If you change… | Then… | Costs |
|---|---|---|
| a scene's `focus` | its glide; its two morphs' camera paths (local) | free |
| a scene's anchor, figure or reference photos | its keyframe redraws; its two morphs regenerate | ~$0.30–0.40 |
| `visual.style`, `texture`, keyframe template | every keyframe redraws and every morph regenerates | ~$2–3 |
| `visual.morph`, segment template | every morph regenerates | ~$1.50–3 |
| `visual.camera_moves` glides, `visual.motion` | local re-render of what they affect | free, minutes |
| `subtitles.*` | only the finish | free |

## 10. Levers for Optimising

1. **Morph prompt:** replace the flipping-panel language with fluid melting (the director's ask),
   then judge one transition before regenerating all.
2. **Texture speed:** the per-frame vignette at full resolution dominates; precompute a vignette
   mask and modulate its opacity, or apply grain at half resolution.
3. **Better visual judging:** Jev reads Gemini's text; a vision-native judge, or measuring framing
   in code (the focal point's on-screen position) would cut false flags.
4. **Standing figures' focus:** detect a face inside the person box (a second Grounding DINO
   query, "face") for full-body shots.
5. **Fewer, longer stills:** cheaper runs; the glide and breathing hold attention better than they
   did, so fewer morphs may suffice.
