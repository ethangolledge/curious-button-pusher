# Every Channel Setting

Last reviewed: 2026-10-10

A channel is the folder `themes/<name>/`. Its `theme.json` holds every exact value below; its
`SKILL.md` holds the channel in words (the feeling, the look, the voice, the shape of its
stories), which every creative agent reads. This page is the complete list of `theme.json`
settings: what each does, the starter's value, when to change it, and what changing it costs.
[themes.md](themes.md) explains how a theme fits together; [visuals.md](visuals.md) and
[narration.md](narration.md) explain the pictures and the narration in depth.

**What changing a setting costs.** Nothing, until the next video. In a video already made, a
change re-makes only what depends on it:

| "Re-makes" says | Means |
|---|---|
| free | local rendering or checks only (ffmpeg on your computer) |
| writing | the next script, plan or storyboard is written with it (paid, cents to a dollar or two) |
| pictures | keyframes are drawn again, and the morphs from them (about $0.05 a picture, $0.12 a morph) |
| narration | passages are recorded again (about $0.09 a take) |
| music | a new music bed is generated (cents), unless a bed is locked |

`tests/test_theme.py` checks every theme loads: values in range, templates using only known
slots, colours as `#RRGGBB`, every file present.

## Identity and formats

| Setting | What it does | Starter | Change it when | Re-makes |
|---|---|---|---|---|
| `name` | the channel's name, written by `new-channel` | `starter` | never by hand | — |
| `format` | the format a video uses when you do not choose one | `short` | your channel is mostly long form | — |
| `formats.<format>.platforms` | where this format goes, in plain words, shown when choosing | "YouTube Shorts, TikTok, Instagram Reels" | you publish elsewhere | — |
| `formats.<format>.width`, `formats.<format>.height` | the video's size in pixels | 1080×1920 (short), 1920×1080 (long) | a platform needs another size | pictures |
| `formats.<format>.fps` | frames per second | 30 | rarely; 24 for a film feel | free |
| `formats.<format>.aspect_ratio` | the shape, as the image and video models are told | `9:16`, `16:9` | with the size | pictures |
| `formats.<format>.frame`, `formats.<format>.orientation` | how prompts name the frame ("Vertical 9:16", "vertical") | as shown | with the size | pictures |
| `formats.<format>.min_seconds`, `formats.<format>.max_seconds` | the shortest and longest video of this format | 40–180 s; 120–1800 s | a platform's limit changes | — |
| `formats.<format>.review_plan` | you sign off the story plan before any script is written | off (short), on (long) | you want to see every plan | — |
| `formats.<format>.subtitle_font_size`, `formats.<format>.subtitle_max_words`, `formats.<format>.subtitle_margin_bottom` | subtitles sized for this frame, over the channel's `subtitles` | 58, 5, 110 (long only) | they look wrong in this frame | free |

Add a format by copying one and naming it (`square`, say); remove one you never make.

## The look in words

Each is words an image or video model follows. Name a technique, never an artist or franchise.

| Setting | What it does | Starter | Change it when | Re-makes |
|---|---|---|---|---|
| `palette.<colour>` | the channel's named colours (`#RRGGBB`), for you and for the words below | night, paper, sun, slate, sea | always: your colours | — (the words that use them do) |
| `visual.style` | the medium and look of every picture: the most important line | "clean modern flat illustration…" | always | pictures |
| `visual.texture` | surface: grain, print, brushwork | "smooth flat colour with a fine paper grain" | your medium has a texture | pictures |
| `visual.lighting` | how light falls | "soft, even, natural light…" | darker, moodier, brighter | pictures |
| `visual.avoid` | what no picture may contain (photorealism, text, logos…) | a list | the model keeps drawing something unwanted | pictures |
| `visual.figure` | how a real public figure is drawn; slots `{subject}`, `{name}`, `{likeness}` | "…drawn in the same simple illustration style…" | your style draws people differently | pictures |
| `visual.silhouette` | the fallback when a portrait is refused or garbled; slots `{subject}`, `{silhouette}` | "…a simple flat silhouette…" | rarely | pictures |
| `visual.reference_note` | added when real reference photographs are attached: use them for identity only | "…only for identity and shape…" | rarely | pictures |
| `visual.morph` | how one picture becomes the next, told to the video model. Describe the change you want to see; effect words get literal results | "The picture flows smoothly into the next…" | always: your transitions | pictures (morphs) |
| `visual.morph_avoid` | what no morph may contain | a list | flashes or cuts appear | pictures (morphs) |
| `visual.keyframe_template` | the full prompt for each scene's picture, built from slots: `{frame}`, `{orientation}`, `{subject}`, `{setting}`, `{composition}`, `{key_elements}`, `{light_and_colour}`, `{field_frame}`, `{field_light}`, `{style}`, `{texture}`, `{lighting}`, `{avoid}` | see the file | you need a different prompt shape | pictures |
| `visual.segment_template` | the prompt for each morph from the slots above, minus the composition ones, plus `{camera}`, `{motion}`, `{field_motion}`, `{shift}`, `{morph_bridge}`, `{morph}`, `{next_subject}`, `{next_setting}` | see the file | as above | pictures (morphs) |
| `visual.final_segment_template` | the prompt for the last scene, which settles instead of morphing | see the file | as above | pictures (last morph) |
| `references` | style images in `references/`, attached to every picture so every scene shares one look; 2–4 images, no text or real people | none | you have images that capture the look | pictures |

## Camera moves (local, free)

A still glides over its picture: from `start` to `end`, toward the scene's focal point.

| Setting | What it does | Starter | Change it when | Re-makes |
|---|---|---|---|---|
| `visual.camera_moves.<move>.describe` | how the move is described to the video model | "a slow push-in" | you rename or add a move | pictures (morphs) |
| `visual.camera_moves.<move>.start.zoom`, `visual.camera_moves.<move>.end.zoom` | how far the view is magnified (1 = the whole picture) | 1.06 → 1.24 (push in) | stronger or gentler moves | free |
| `visual.camera_moves.<move>.start.toward_centre`, `visual.camera_moves.<move>.end.toward_centre` | how far the view's centre moves from the focal point toward the frame's centre (0–1) | 0.5 at the wide end | rarely | free |
| `visual.camera_moves.<move>.start.x`, `visual.camera_moves.<move>.start.y`, `visual.camera_moves.<move>.end.x`, `visual.camera_moves.<move>.end.y` | a sideways and vertical shift, in fractions of the picture | e.g. drift −0.06 → +0.06 | for drifts, dollies and rises | free |

The starter's moves: `push_in`, `pull_out`, `orbit`, `drift`, `dolly`, `rise`. Add one by
naming it; the field (below) chooses which moves each feeling uses.

## Motion and texture (local, free)

Zero switches an effect off. The starter is calm; [visuals.md](visuals.md) gives strong values.

| Setting | What it does | Starter | Change it when | Re-makes |
|---|---|---|---|---|
| `visual.motion.breath.seconds` | one slow breath of a still, in seconds | 6.0 | slower or quicker breathing | free |
| `visual.motion.breath.swell` | how much the frame swells each breath (share of the frame, up to 0.1) | 0.01 | more life in still pictures | free |
| `visual.motion.breath.ripple_pixels` | ripples spreading from the focal point (pixels at 1080 wide, up to 40) | 0 | a dreamier look | free |
| `visual.motion.breath.tint` | ripples take the scene's emotional colour, at most this opacity (up to 0.3) | 0 | with ripples on | free |
| `visual.motion.morph.warp_pixels` | a liquid warp over each morph, peaking mid-way (pixels, up to 80) | 0 | wilder transitions | free |
| `visual.motion.morph.trails` | light trails over each morph (0–1) | 0 | as above | free |
| `visual.motion.morph.mirror` | a mirrored bloom over each morph (0–1) | 0 | as above | free |
| `visual.motion.morph.plate_shift_pixels` | colour plates slid apart, like misprinted ink (pixels, up to 60) | 0 | a printed look | free |
| `visual.motion.morph.hue_radians` | a swing of colour during each morph (radians, up to 3.2) | 0 | psychedelic moments | free |
| `visual.motion.morph.saturation` | extra colour during each morph (up to 2) | 0 | as above | free |
| `visual.motion.texture.fractal` | a slowly zooming fractal blended into the shadows (opacity 0–1); the slowest effect to render | 0 | a hypnotic background | free |
| `visual.motion.texture.vignette_swing` | the dark edges breathe by this much (radians, up to 0.5) | 0.03 | more or less vignette movement | free |
| `visual.motion.texture.fringe_pixels` | colour fringing at edges (pixels, up to 10) | 0 | a printed or retro look | free |
| `visual.motion.texture.grain` | film grain strength (up to 40) | 3 | more or less grain | free |
| `visual.motion.texture.flicker` | a light flicker (up to 0.1) | 0 | an old-film feel | free |
| `visual.motion.dissolve_seconds` | how long two stills dissolve when no morph joins them | 0.6 | rarely | free |

## Tone: how bright and colourful pictures should be

Code measures every keyframe and redraws one that misses (once). Leave these until your first
run's pictures are approved, then refit them from what you approved
([machine-learning.md](machine-learning.md)).

| Setting | What it does | Starter | Change it when | Re-makes |
|---|---|---|---|---|
| `visual.tone.max_mean_brightness` | the brightest a picture may be on average (0–255) | 80 | a brighter or darker channel | pictures (redraws) |
| `visual.tone.max_highlight_saturation` | how colourful its brightest tenth may be (0–181) | 45 | a more colourful channel | pictures (redraws) |
| `visual.tone.brightness.neutral`, `visual.tone.brightness.per_unit`, `visual.tone.brightness.tolerance` | the brightness a neutral scene aims for, how far each feeling moves it, and how far a picture may miss before it is redrawn | 60, 10, 20 | refit after approved pictures | pictures (redraws) |
| `visual.tone.saturation.neutral`, `visual.tone.saturation.per_unit`, `visual.tone.saturation.tolerance` | the same for colourfulness | 9, 3, 7 | as above | pictures (redraws) |
| `visual.tone.darker`, `visual.tone.lighter`, `visual.tone.richer` | what a redraw is told when a picture was too bright, too dark, or too muted | "A little darker and calmer…" | your words for it | pictures (redraws) |

## The emotional field: how each scene feels

Each line of narration is measured for how a listener reacts: `lean_in` (curious),
`brace` (tense), `recoil` (repelled), `settle` (at rest). A scene's space, light, colour and
camera follow its lines' reaction, in three strengths (slight, clear, strong). Only space, light,
colour and motion: never emotion words, never added content. [visuals.md](visuals.md).

| Setting | What it does | Starter (lean_in) | Change it when | Re-makes |
|---|---|---|---|---|
| `visual.field.reactions.<reaction>.aperture` | how open the space is: −1 enclosed, 1 wide open | 0.7 | your channel frames feelings differently | pictures |
| `visual.field.reactions.<reaction>.temperature` | colour temperature: −1 cold, 1 warm; also checked on the picture | 0.6 | as above | pictures |
| `visual.field.reactions.<reaction>.pleasure`, `visual.field.reactions.<reaction>.arousal` | where the reaction sits on the circumplex of emotion (−1 to 1): sets the scene's brightness and colour targets | 0.4, 0.4 | rarely | pictures |
| `visual.field.reactions.<reaction>.frame`, `visual.field.reactions.<reaction>.light`, `visual.field.reactions.<reaction>.motion` | three wordings each (slight, clear, strong) for the picture's framing, its light, and how it moves | "an open frame with space around the focal point"… | your channel's visual language | pictures |
| `visual.field.reactions.<reaction>.framing` | plain words for the frame, checked against what the vision model sees | "an open frame" | with `frame` | free (checks) |
| `visual.field.reactions.<reaction>.cameras` | which camera moves suit it | `push_in`, `orbit`… | with your moves | pictures (morphs) |
| `visual.field.reactions.<reaction>.ripple_colour` | the colour its ripples take (`#RRGGBB`), with ripples on | from the palette | with your palette | free |
| `visual.field.neutral.aperture`, `visual.field.neutral.temperature`, `visual.field.neutral.pleasure`, `visual.field.neutral.arousal`, `visual.field.neutral.frame`, `visual.field.neutral.light`, `visual.field.neutral.motion`, `visual.field.neutral.framing`, `visual.field.neutral.cameras`, `visual.field.neutral.ripple_colour` | the same for a scene with no measured reaction | balanced, even, a gentle drift | rarely | pictures |
| `visual.field.shifts.inward`, `visual.field.shifts.outward`, `visual.field.shifts.sideways` | how the space changes into the next scene, by whether it closes, opens, or stays | "the space folds gently inward…" | your transition language | pictures (morphs) |
| `visual.field.speeds.slow`, `visual.field.speeds.swift` | how fast that change happens; swift is never a cut | "slowly and smoothly" | as above | pictures (morphs) |
| `visual.field.swift_above` | how big a change in feeling makes it swift | 0.9 | rarely | pictures (morphs) |
| `visual.field.warmer`, `visual.field.cooler` | what a redraw is told when a picture's colour temperature is wrong | "Warmer light than before…" | your words | pictures (redraws) |

## Writing: how the narration is written

| Setting | What it does | Starter | Change it when | Re-makes |
|---|---|---|---|---|
| `writing.voice` | the narration's voice in one sentence; every script is judged against it | "Clear, curious and fair: plain words that explain, a little warmth, no hype." | always: your storyteller | writing |
| `writing.max_weighty_lines` | how many solemn or aphoristic lines one script may carry | 1 | a more or less dramatic channel | writing |
| `writing.rhythm.sentence_words_mean`, `writing.rhythm.sentence_words_spread` | the average sentence length and how much it varies (guidance, never a gate) | 14, 8 | set it from a narrator you admire: `content analyse-narration <audio> --apply` | writing |
| `writing.rhythm.short_share`, `writing.rhythm.long_share` | the share of very short (≤4 words) and long (≥20) sentences | 0.2, 0.2 | as above | writing |
| `writing.rhythm.source` | where the rhythm numbers came from | a general guide | written by `analyse-narration` | — |
| `writing.weights.evidence.verified`, `writing.weights.evidence.reported`, `writing.weights.evidence.disputed`, `writing.weights.evidence.inference`, `writing.weights.evidence.unsupported` | how firmly each kind of research claim can be stated (0–1) | 1.0, 0.7, 0.4, 0.3, 0 | a more cautious or bolder channel | writing |
| `writing.weights.single_source_penalty` | what resting on one source costs a claim | 0.1 | rarely | writing |
| `writing.weights.full_evidence` | evidence at or above this counts in full; below, a claim's score is scaled down | 0.7 | rarely | writing |
| `writing.weights.assert_from`, `writing.weights.attribute_from` | a claim is stated plainly above the first, attributed ("according to…") above the second, otherwise only as a question | 0.9, 0.6 | a more cautious channel raises them | writing |
| `writing.weights.feeling_from` | a beat whose strongest claim is worth this is told with feeling | 0.6 | rarely | writing |
| `writing.weights.turn_window` | where (share of the narration) the story's turn should land: near the music's peak | 0.45–0.75 | rarely | writing |
| `writing.weights.role_seconds.spine`, `writing.weights.role_seconds.essential_context`, `writing.weights.role_seconds.supporting_evidence`, `writing.weights.role_seconds.colour`, `writing.weights.role_seconds.expendable` | how many seconds each kind of claim may take (shortest, longest): the story's central claims, the context they need, evidence, colour, and what can go | 12–25, 5–10, 3–6, 0–4, 0 | slower for a contemplative channel, quicker for a brisk one | writing |
| `writing.weights.transition_seconds`, `writing.weights.beat_floor_seconds` | seconds added to each beat for its transition, and the least a beat gets | 2, 4 | rarely | writing |

## The narrator

| Setting | What it does | Starter | Change it when | Re-makes |
|---|---|---|---|---|
| `voice.model`, `voice.voice` | the voice model and its preset voice (all through OpenRouter) | `google/gemini-3.8-flash-tts`, "Algenib" | you pick another after auditions | narration |
| `voice.reference_audio`, `voice.reference_transcript` | a recording to clone instead of a preset, and its exact words (`voice-lock` sets both) | none | you lock a designed or recorded voice; a real person only with their consent | narration |
| `voice.direction_style` | how the model takes spoken direction: `none`, `google`, `openai`, or `inline` (a tag before the text) | `google` | with the model | narration |
| `voice.direction` | how every passage is spoken, for voices that take direction | "Clear, warm and curious…" | your narrator's manner | narration |
| `voice.words_per_minute` | the pace every passage is brought to (each take is measured and gently sped up or slowed, pitch kept) | 160 | a slower or brisker channel | narration |
| `voice.hook_pace` | the opening runs a little slower (a share of the pace) | 0.92 | rarely | narration |
| `voice.tempo_range` | the most a take may be slowed or sped up; past about 1.2× it audibly lurches | 0.9–1.2 | rarely | narration |
| `voice.retakes` | fresh takes when one would need more stretch than allowed | 2 | to save or spend a little | narration |
| `voice.pauses.build`, `voice.pauses.hold`, `voice.pauses.turn`, `voice.pauses.release` | the breath before a passage, by how it enters (seconds) | 0.35, 0.5, 0.8, 0.7 | a more or less spacious delivery | free (re-timing) |
| `voice.tail_seconds` | silence after the last line before the music plays out | 1.5 | rarely | free |
| `voice.length_tolerance` | how far the spoken narration may miss its planned length before the script is revised | 0.15 | rarely | writing |
| `voice.lexicon` | how words are spoken: `"NASA": "Nasa"`, `"BBC": "B-B-C"` (subtitles still show the written word) | none | the voice mispronounces something | narration (lines with the word) |
| `voice.candidates[].model`, `voice.candidates[].voice`, `voice.candidates[].direction_style`, `voice.candidates[].clone` | the voices `voice-audition` renders for you to compare; `clone` speaks with your locked recording | four voices | you want to hear others | — |
| `voice.audition_text`, `voice.audition_direction` | what every candidate reads in the audition, and how | "The first bridge across the river took eleven years to build…" | something closer to your stories | — |
| `voice.designs` | narrators `voice-design` renders from written descriptions (`model`, `voice`, `direction_style`, `description`: who is speaking); the one you lock becomes `reference_audio` | none | you want a voice no one else uses | — |

## Subtitles (local, free)

| Setting | What it does | Starter | Change it when | Re-makes |
|---|---|---|---|---|
| `subtitles.font_file`, `subtitles.font_name` | the font file in `fonts/`, and its name inside the file | Archivo Black | your channel's font (licensed for video) | free |
| `subtitles.font_size` | size, in pixels at the video's height | 78 | too big or small | free |
| `subtitles.primary_colour`, `subtitles.highlight_colour`, `subtitles.outline_colour` | the words, the word being spoken, and the outline (`#RRGGBB`) | bone, yellow, near-black | your palette | free |
| `subtitles.outline`, `subtitles.shadow` | outline and shadow thickness | 6, 2 | readability | free |
| `subtitles.max_words`, `subtitles.max_chunk_seconds` | most words, and seconds, on screen at once | 3, 1.8 | calmer or punchier captions | free |
| `subtitles.uppercase` | capital letters | on | a quieter style | free |
| `subtitles.margin_bottom` | distance from the bottom edge, in pixels (clear of a platform's buttons) | 640 | a platform's layout | free |

## Music

One bed for every video, chosen by audition and locked, like the voice. Without one, music is
generated for each video from `music.prompt`.

| Setting | What it does | Starter | Change it when | Re-makes |
|---|---|---|---|---|
| `music.prompt` | what the music model is asked for | "Instrumental only, no vocals. A light, curious underscore…" | always: your channel's sound | music |
| `music.variations` | endings added to the prompt for `music-audition`, one candidate each | four instrumentations | you want different candidates | — |
| `music.track` | the locked bed in `music/` (`music-lock` sets it and maps its beats) | none | you lock a bed | free (re-fit) |
| `music.outro_seconds` | how long the music plays on after the last line (shortest, longest); default 1–6 s | default | rarely | free |
| `music.below_voice_db` | how far the music sits below the voice | 15 | music too loud or quiet | free |
| `music.duck_threshold`, `music.duck_ratio` | how hard the music dips under speech | 0.02, 2.0 | music fights the voice | free |
| `music.duck_attack_ms`, `music.duck_release_ms` | how gently it dips and comes back (slow keeps it from pumping) | 200, 1500 | as above | free |
| `music.loudness_lufs`, `music.true_peak_db` | the finished video's loudness and peak (platforms expect about −14 LUFS) | −14, −1 | a platform asks for other values | free |

## 3D shots

How scenes built in Blender are drawn ([staging.md](staging.md)). The look is a file; its
settings are the feel, so the feel is tuned here, in numbers, not in code.

| Setting | What it does | Starter | Change it when | Re-makes |
|---|---|---|---|---|
| `staging.look` | the look by name: `plain` (the engine's), or the channel's own file in `blender/looks/` | `starter` (`themes/starter/blender/looks/starter.py`) | you make your own look | 3D renders (free, render time) |
| `staging.look_settings` | the look's settings, as its file lists them; the starter's: `exposure` (stops), `contrast` (Blender's tone curve name), `saturation` (0 grey to 1 full), `shadow` and `glow` (palette names: the colour of the dark and of lamps and screens) | −0.3, Medium High Contrast, 0.75, night, sun | the 3D pictures do not feel like the channel | 3D renders (free, render time) |
| `staging.moves.<move>.block`, `staging.moves.<move>.settings` | each of the theme's camera moves (`visual.camera_moves`) as a 3D move: the move block and its settings, so a staged scene moves the way its keyframe scene would; the Visual Director's own settings refine them | push_in, pull_out (dolly in, out), orbit (40°), drift (a breathing hold), dolly (sideways), rise (up) | you add a camera move, or want one to move differently in 3D | 3D renders (free) |

