# Machine Learning

This page lists every learned or fitted model in the project: what it does, what data it rests on, how it keeps learning, how to check it, and what would improve it. It ends with a playbook for improving a component the way the music analysis was improved.

A channel's taste data (examples, labels, flags, trained models) lives in the directory its
configuration's `learning.directory` names: inside the theme, `themes/<name>/learning/`, so a
fork of the code starts with no one's taste ([themes.md](themes.md#a-themes-taste-data)). Paths
below are relative to it. Like the rest of the channel it is private: gitignored, and kept in
your bucket if you use one ([storage.md](storage.md)).

Most of the "intelligence" lies in language models (the writers, and Jev as the judge). This page covers the rest: small, local, inspectable models, and the published data behind them.

## Register

| Component | Kind | Learns from our runs? | Code | Data |
|---|---|---|---|---|
| Beat and bar tracking | Pretrained transformer (Beat This!) | No, inference only | `production/music_map.py` | CPJKU's training set |
| Focal point | Pretrained open-vocabulary detector (Grounding DINO tiny) | No, inference only | `production/focus.py`, `providers/vision.py` | Each scene's `focus` phrase against its keyframe |
| Picture geometry | Pretrained monocular geometry (MoGe-2 ViT-L, MIT) | No, inference only | `providers/vision.py`, `staging/lift.py` | Each animated keyframe ([picture-shots.md](picture-shots.md)) |
| People's outlines | Pretrained promptable segmentation (SAM 2.1 large, Apache-2.0) | No, inference only | same | The detector's person boxes |
| People's poses | Pretrained pose estimator (ViTPose base, Apache-2.0) | No, inference only | same | The same boxes |
| Painting in behind | Pretrained inpainting (LaMa, ONNX, Apache-2.0) | No, inference only | same | The holes behind people and depth edges |
| Taste models | Sentence embeddings + logistic regression, one per question | **Yes, after every run with new labels** | `learning/` | `learning/examples.jsonl`, `labels.jsonl`, `flags.jsonl` |
| Active learning | Uncertainty sampling + teacher model | On `train --budget` only (paid) | `learning/train.py` | Same, plus `training.jsonl` |
| Colour from emotion | Published regression (Valdez and Mehrabian), inverted | Records kept for refitting | `story/field.py`, theme `tone` | `learning/keyframes.jsonl` |
| Emotional field wording | Hand-designed mapping, research-informed | No | `story/field.py`, theme `field` | Jev's reaction probabilities |
| Faithfulness gate | Pretrained NLI model (`Xenova/nli-deberta-v3-small`, ONNX) | No, inference only | `story/faithfulness.py` | Each line against its cited claims |
| Transcription | Pretrained ASR (`openai/whisper-large-v3-turbo`, via OpenRouter) | No | `production/media.py` | — |
| Syllable counts | Rule-based (`textstat`) | No | `story/pace.py` | — |

Measurements that are signal processing, not learning (listed so nobody mistakes them for models):
- EBU R128 loudness and loudness range;
- `signalstats` brightness, saturation and warmth;
- scene-cut detection;
- word error rate;
- the reference narrator's profile (`production/narration_analysis.py`, descriptive statistics).

## Training as We Go

Every run started from the CLI with a `learning` section in its configuration (`config.example.json` has one, and so every new channel) finishes with a free, local learning step (`learning/after_run.py`) and prints one "Learning:" line. Nothing in it calls a paid model.

| What you (or the run) do | What gets stored | Which model learns |
|---|---|---|
| Jev answers a question | an example: the exact state Jev saw plus its answer | taste models (inputs) |
| The fact checker blocks or clears a unit | an `outcome` label on "is it supported?" | taste models |
| You **approve** a stage | a `review` label confirming each answer Jev passed on what you approved | taste models |
| You approve something Jev **failed** | a flag ("You approved this; Jev answered …") | taste models, via `label` |
| You write `S4: feel brace` on a one-unit scene | **your** label on that unit's reaction | the local reaction model |
| You write `S4: feel brace` on a scene of several units | a flag on each unit's reaction | via `label` |
| You write any other targeted note (`U3: …`, `S2: …`) | a flag on every example about that target, with your note | via `label` |
| You run `label` | **your** labels, flagged examples first | taste models, and the yardstick for promotion |
| The narrator speaks a passage | the take's text, voice, direction and measured seconds | kept for later (how each voice paces itself) |
| A keyframe is drawn | its field's circumplex point, colour targets, and measured brightness, saturation and warmth | colour scales (refit by hand for now) |
| You run `train --budget` | teacher labels, and the run's spend in `training.jsonl` | taste models |

Rules that keep this safe:
- **Your labels are the only yardstick.** Review, outcome and teacher labels train the models, but a model is promoted only if it agrees with *your* labels at least as often as Jev did. It is demoted automatically if Jev later overtakes it.
- **Our own models' answers are never mistaken for Jev's.** Each judgement records who answered it, and harvesting skips local answers.
- **Narration takes are recorded, not fitted.** The pace model was retired (see below); `narration.jsonl` keeps every take's text and trimmed length for a future budget calibration ([narration.md](narration.md#10-levers-for-optimising)).
- **Everything is kept for later.** The `learning/` directory is the durable dataset: append-only JSON lines, readable and diffable. The media cache can be deleted without losing any of it.
- **Traces are self-contained.** They carry revision counts and the research and plan a resumed run started from, so a resumed run can still be harvested.
- **Only a person's decisions teach.** Every review decision records who made it (`decided_by`). Review files an assistant answers count as the assistant's, and older decisions as unknown; neither creates labels or flags.

The commands (free and local, except `train --budget`):

```bash
pip install -e '.[learn]'                                              # numpy + fastembed (CPU, no GPU)
python -m content harvest --config themes/<name>/config.json           # all traces again (runs do this themselves)
python -m content label --count 20 --config themes/<name>/config.json  # you answer; flagged ones first
python -m content train --budget 0.50 --config themes/<name>/config.json
python -m content verdict runs/<topic>/.work/session-1.trace.json \
  --story list --voice flat --exclude --note "…"
```

`verdict` is your judgement of a finished script, the strongest label there is: it labels the
whole script's `script_story` and `script_voice` (judged against the theme's `writing.voice`),
and `--exclude` stops that run's approvals from ever counting as good work.

## Focal Point (Grounding DINO, 2026-10-03)

- **What:** finds where the eye should land in each keyframe, so the camera glides toward it and the frame breathes around it. Before this, the camera moves were fixed pans, and one scene drifted toward a corner, away from the person it was about.
- **Model:** [Grounding DINO tiny](https://huggingface.co/IDEA-Research/grounding-dino-tiny) (Liu et al., 2023), an open-vocabulary detector: given an image and a short phrase, it returns boxes with confidences. It runs on the CPU through `transformers` in about nine seconds per keyframe. The producer caches each answer by image and phrase, so it runs once per keyframe.
- **Input:** the scene's `focus`, three to eight plain words the visual director writes ("the man at the head of the table"). For a public figure, the point is a third of the way down the box, at the face; otherwise it is the box's centre.
- **Measured on the eleven keyframes of a first production (by eye, boxes drawn on a contact sheet):**
  - with the anchor's first clause as the phrase, 8 of 11 were right; the misses found the room the anchor named first (the table, not the man at its head);
  - with a named focus, 11 of 11 were right.
- **Rejected:**
  - spectral-residual saliency (Hou and Zhang, 2007), with no model: it found bright edges, putting S1's point on a hip and S4's on the table's edge;
  - BiRefNet (salient-object segmentation): like saliency, it finds what stands out, not what the scene is about.
- **Install:** the optional `vision` extra, with PyTorch's CPU build. Without it, the camera aims at the frame's centre. Tests always use the centre, so they stay deterministic.
- **Known limits:** for a standing figure the box runs to the feet, so a third of the way down lands on the chest; the glide still frames the person.

## Beat and Bar Tracking (Beat This!)

- **What:** finds every beat and every bar start (downbeat) in the locked music bed, so the track is edited only on bar lines and the narration can land on beats.
- **Model:** [Beat This!](https://github.com/CPJKU/beat_this) (Foscarin, Schlüter and Widmer, ISMIR 2024). It's a transformer over a spectrogram, trained on a large collection of annotated datasets. We use the `final0` checkpoint on the CPU, with `dbn=False`.
- **When it runs:** once per track, during `music-lock` (or `music-map`). The result is readable JSON (`themes/<theme>/music/bed.map.json`) that can be corrected by hand.
- **Install:** the optional `music` extra, with PyTorch's CPU build. This machine has no CUDA GPU, and inference takes seconds anyway.
- **On top, heuristic rather than learned:** four-bar phrases, named by mean short-term loudness (the first is the intro, the loudest the peak, those before it build and those after it outro).
- **Checked by:**
  - a synthetic 120 BPM pulse test;
  - listening to every arrangement at its joins;
  - the largest sample-to-sample jump in a render equals the original's.
- **Known limits:**
  - The pulse can come out at half speed; the bed reads as 75 BPM. That doesn't matter, because we cut on bars.
  - Phrase names come from loudness, not from musical structure.
- **Rejected:** `allin1` labels real sections but needs NATTEN, which has no Python 3.14 wheel. Revisit if phrase naming proves wrong on a future track.

## Open Story Weights (2026-09-27)

- **Numbers per claim:**
  - **evidence** `e`, from the research's classification (verified 1.0, reported 0.7, disputed 0.4, inference 0.3), less 0.1 for a single source;
  - **worth** `w` and **connection** `c`: Jev measurements (0–2, taken as the expected level, then halved).
- **Score** `s = w · c · min(1, e/0.7)`.
- **What the score decides:**
  - which facts are the strongest candidates: the upper group where the scores split most naturally (two-class Jenks breaks, no fixed count). Weaker facts in the plan and strong facts left out are advice at the plan review;
  - where each claim sits within its story role's band of seconds, with how many claims rest on it (`allot_words`; the role, not the score, sets the band: [narration.md](narration.md#time-by-story-role));
  - how each beat is told (`curiosity` if its best claim's evidence is under 0.6, `feeling` if its worth is 0.6 or more, otherwise `logic`);
  - how firmly each claim is stated (assert from 0.9, attribute from 0.6, otherwise ask);
  - whether the strongest beat after the hook starts 45–75% of the way in, near the music's peak;
  - whether a better-weighted verified claim should be the hook.
- **Where they live:** the constants are in the theme's `writing.weights`, and every number is shown at the plan review.
- **Not yet fitted.** The next step is to fit them to your verdicts (`python -m content verdict`).

## Robotic-Writing Detectors and the Listen Check (2026-09-27)

- **Before speech** (`story/prose.py`):
  - verbless sentences, using NLTK's averaged-perceptron tagger, downloaded once (about 3 MB). A line of five or more words, or more than two short ones, goes back to the writer;
  - a short question answered by the next sentence;
  - numbers or three-word phrases in the ending that the story already said.
- **Validated** by replaying them over the scripts a person heard as "no soul": they flag exactly the lines that were heard as robotic (a verbless "[someone], speaking at [a university].", a bare "And the day job?", a figure repeated in the ending), and nothing else in the fixed versions.
- **After speech** (`checks.listen_issues`): read from each take's transcript, a sentence the voice ended where the script runs on, and a pause of 0.45 s or more where the script has no mark. Transcribers split hyphenated words, so they are rejoined first. Replayed on those takes, it finds the verbless fragment.

## Faithfulness Gate (Natural-Language Inference)

- **What:** before the paid fact check, reads each sentence against each claim its unit cites (with their qualifications), and flags a sentence **every** cited claim contradicts. **It is advisory** (shown at review, a hint for the fact checker). As a gate it caused three false blocks on a first production: first from padding, which it now avoids by scoring each pair alone, then from gluing claims together.
- **Model:** `Xenova/nli-deberta-v3-small`, a DeBERTa-v3 model fine-tuned for inference, quantised to ONNX. It runs on the CPU with `onnxruntime` and `tokenizers` (already in the `learn` extra) in about 20 ms per line, downloaded once into `learning/embedder/`. It's switched on by `learning.nli_model`.
- **Validated (2026-09-27)** on a first production's v2 script:
  - all 10 faithful lines scored under 0.2 for contradiction;
  - two deliberately wrong lines (one claiming a panel approved a deal it did not; one claiming a named official said a law was broken and issued a subpoena) scored 1.00.

  The gate blocks at 0.8.
- **Tried and dropped, with the measurements behind each decision:**
  - *"Not supported" warnings* (entailment below 0.5): they caught both insinuations, but also flagged 4 of the 10 faithful lines, e.g. "The Times reported…" when "the Times" sits in the claim's qualification. Too noisy to be useful.
  - *Tension mining* (contradiction between research claims, to find the story's ironies): the model reads any two *different* events as contradicting (Maloney's 2022 probe against Raskin's 2026 probe scored 1.00). It can't find irony across claims.
  - *Story threads* (clustering claims with `bge-small` embeddings): similarities on one story's claims sit in a narrow band (median 0.60, 95th percentile 0.75), so the clusters were either singletons or mush. The planner groups threads better from the text.

## Narration Pace: Set, Not Predicted

- **Retired (2026-09-27):** a linear syllable model (`seconds ≈ intercept + rate × syllables`) predicted each line's length, refitted after runs, and was calibrated on each new voice.
- **Why:** once narration was spoken a passage at a time, the voice model's own speed varied from take to take, from 108 to 155 words per minute across one script. That made the hook sound "dramatic" and later passages rushed, and it put the prediction 25% out.
- **Replaced by control:** each take is measured (words ÷ trimmed seconds) and sped up or slowed, pitch kept, to the theme's rate (`voice.words_per_minute`; the hook at `hook_pace`), within `tempo_range`. Lengths are then just words at the rate: exact, with nothing to fit.
- **The data is still kept:** every take's text, voice, direction and natural length goes to `learning/narration.jsonl`, in case how a voice paces itself is ever worth modelling.

## Judging Soul: What Failed (2026-09-27)

- `script_voice` answered "on voice" at 80–93% confidence on scripts a person heard as soulless. `script_story` sat at about 0.5 on every revision.
- Both are now **measurements**: recorded, and learned from people's verdicts, but they never pass or fail anything.
- **Only a person's decisions teach** the loop (`decided_by`). The 72 review labels from a first production's approvals were purged, since some of those approvals were the assistant's.

## Taste Models (the Self-Learning Loop)

Jev answers every judgement. For **subjective** questions only (`learning.local_questions`), a small local model can take over once it agrees with you at least as well as Jev does. Factual and logical questions always stay with Jev.

- **Model:**
  - `BAAI/bge-small-en-v1.5` sentence embeddings (local ONNX via `fastembed`; no GPU, no PyTorch) of the exact state Jev saw;
  - then multinomial logistic regression with L2 regularisation, written in numpy.

  It trains in under a second and returns probabilities, so it uses the same pass, fail and unsure thresholds as Jev.
- **Label strength:** a person, then an outcome, then a review, then the teacher. One label is kept per example, the strongest.
- **Active learning:** the teacher (the `writer` model) labels the examples the current models are least sure about first.
- **Not adopted:** Laya (low zero-shot accuracy; fine-tuning needs a GPU).
- **Promotion and demotion:** by cross-validated agreement with *your* labels, needing at least `min_gold` (8). Recorded in `learning/models/registry.json` with both accuracies.

### Where a channel stands

`content train --config …` prints each question's labels, your share of them, and whether a
local model is promoted; the counts are `wc -l themes/<name>/learning/*.jsonl`. A new channel
starts with none, so nothing is promoted until you have labelled at least `min_gold` (8) per
question. Only labels you typed (or approvals you gave yourself) count as yours: review answers
the assistant gave are recorded as the assistant's.

### What Would Improve It

1. **Label.** Your labels are the yardstick, and nothing can be promoted without them. `label --count 20` starts with the 5 flagged disagreements.
2. **More runs.** Each one now adds examples, review labels and pace clips automatically.
3. **Phase 3: data-driven thresholds.**
   - Every Jev gate uses 0.6 to pass and 0.2 to fail, fixed by hand.
   - With about 8 of your labels per question, each question can get the thresholds that agree with you most while limiting paid reruns.
   - The inputs (Jev's probabilities and your labels) are already stored.
4. **Phase 4: one paid teacher round,** once you've labelled.
   - `train --budget 3` has Claude (the `writer` model) label about 150 of the least certain examples, stopping at $3.
   - Every run and its spend is logged, with the running total printed.
   - Nothing is promoted unless it beats Jev on your labels.
5. **Known limit.** Once a question is promoted, Jev no longer answers it, so it stops gathering Jev examples. A later fix would be shadow mode: Jev also answers a small sample, for comparison.

Hugging Face isn't needed yet. These models train in under a second on a CPU. Fine-tuning a language model would need GPU time and thousands of your labels; revisit at around 1,000.

## Colour From Emotion (Valdez and Mehrabian, 1994)

The study fitted a linear model on people's ratings of standardised colour samples. Hue mattered far less than brightness and saturation:

```
pleasure =  0.69 × brightness + 0.22 × saturation
arousal  = −0.31 × brightness + 0.60 × saturation
```

The field needs the reverse direction, and two equations in two unknowns invert exactly (`field.colour_units`):

```
brightness = 1.244 × pleasure − 0.456 × arousal
saturation = 0.643 × pleasure + 1.431 × arousal
```

- **Reaction points** (Russell's circumplex, set in the theme; a judgement, stated once):

  | Reaction | Pleasure | Arousal |
  |---|---|---|
  | lean in | +0.4 | +0.4 |
  | brace | −0.6 | +0.6 |
  | recoil | −0.6 | −0.3 |
  | settle | +0.5 | −0.5 |

  A scene's point is its reactions' blend, scaled by intensity (2 = the full point).
- **Units:**
  - the study's coefficients are standardised, so one unit is one standard deviation;
  - the theme's `tone.brightness` and `tone.saturation` hold the median and spread of keyframes whose look you approved: for example 17 approved keyframes, with mean luma 41 ± 11 and mean saturation 4.1 ± 1.7;
  - calibrating on rejected keyframes (ones called too bright and too colourful, 51 ± 8.6, 11.4 ± 3.9) flagged every approved, muted frame as "too muted". Calibrate on approved output, never on rejected output;
  - the brightness target never exceeds the theme's ceiling (55).
- **Targets at full strength:**

  | Reaction | Luma | Saturation | Reads as |
  |---|---|---|---|
  | brace | about 30 | about 4.9 | darker, with a little more colour in the accents |
  | settle | about 51 | about 3.4 | lighter and muted |
  | lean in | about 45 | about 5.5 | slightly lighter, richer |
  | recoil | about 35 | about 2.7 | darker and drained |

- **Check:** a keyframe more than 1.5 standard deviations from its target (±17 luma, ±2.6 saturation) is redrawn once, told to be lighter, darker, richer or more muted.
- **Kept for refitting:** every keyframe's point, targets and measurements go to `learning/keyframes.jsonl`, with whether you approved the storyboard. With a few runs of data, the neutral, spread and tolerance can be refitted to what the image model actually produces, and to what you approve.
- **Known limit:** 17 images from one story set the current scales; `learning/keyframes.jsonl` grows with each run, and the scales should be refitted from the approved ones.

## Emotional Field Wording (Research-Informed, Not Learned)

- **Research basis:**
  - Russell's circumplex;
  - Valdez and Mehrabian (above);
  - film grammar, where an enclosed frame reads as tension and an open one as release.
- **Hand-picked:** the per-reaction `aperture` and `temperature` values and the wording tiers.
- **Input:** Jev's System 1 reaction and intensity. That's the one taste input here that can be learned: `unit_reaction` is a local question, and `feel` notes label it.

## Playbook: Improving a Component

This is what happened with the music: hand-written tempo maths gave 152, then 147.8, then 150.07 BPM, and splices that sounded tampered with. A published pretrained model replaced it in an afternoon, with less code.

1. **Name the problem the way researchers do.** "Where does the bar start?" is *beat and downbeat tracking*; "what emotion does this line carry?" is *valence-arousal prediction*; "does this colour feel tense?" is *colour-emotion association*. The name is the search term.
2. **Look for a solved version first:**
   - a pretrained model (Hugging Face, the paper's GitHub);
   - published data (norms, lexicons, regression tables);
   - a benchmark (MIREX, SemEval).

   Prefer recent work with code and a licence that allows our use.
3. **Check that it runs here:** CPU only, Python 3.14 wheels, no service to host. Record rejected options and why.
4. **Contain it:**
   - an optional extra, if it's heavy;
   - run once at lock or setup time where possible;
   - readable output a person can correct;
   - the video run stays deterministic and free.
5. **Make it learn from our input,** if it has anything to fit:
   - store its raw data in `learning/`;
   - refit after runs only when the refit measurably improves;
   - add a row to "Training as We Go".
6. **Test it deterministically:** a synthetic input with a known answer, plus one test skipped when an optional extra is missing.
7. **Measure before and after** on something real, then delete what it replaces and update this page and `PROJECT_CONTEXT.md`.

## Still Proposed: Word-Level Emotion Norms

Lexicons put words on the same pleasure, arousal and dominance axes:
- the NRC VAD Lexicon (Mohammad, 2018), about 20,000 words;
- Warriner, Kuperman and Brysbaert (2013), about 14,000 lemmas.

Averaging them over a line gives a zero-training emotion score, but it can't read context: "It worked." scores neutral, yet in this narration it's chilling. So the proposal is only to try them as three extra features for the local `unit_reaction` model, kept if cross-validation on your labels improves. It needs your labels first. Check the licences before use on a monetised channel: NRC's is non-commercial without a licence.
