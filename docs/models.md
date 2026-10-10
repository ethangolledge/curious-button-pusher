# Every Model

A register of every model the pipeline calls or runs: what it does, where, what it costs, how it
fails, and how to test or replace it. Local and learned models have a deeper write-up in
[machine-learning.md](machine-learning.md); the narration path is in [narration.md](narration.md).

Last reviewed: 2026-10-04.

## At a Glance

| Model | Role | Where it runs | Cost | Code |
|---|---|---|---|---|
| `anthropic/claude-opus-5.5` ("architect") | Editorial Director: plan and story ledger, story decisions | OpenRouter | ~$0.30–0.50 per plan (the ledger adds ~$0.04–0.08, estimated); ~$0.05 per story decision | `agents/editorial_director/` |
| `anthropic/claude-sonnet-5` ("writer") | Script Writer, Visual Director; the Editorial Director's critic and director-note sorting (`critic_model`), findings only; teacher for labels | OpenRouter | ~$0.08–0.15 per script, ~$0.09 per storyboard | `agents/script_writer/`, `agents/visual_director/` |
| `openai/gpt-5.6-sol` ("auditor") | Fact Researcher (with web search), Fact Checker | OpenRouter | ~$0.38 research, ~$0.09–0.10 fact check | `agents/fact_researcher/`, `agents/fact_checker/` |
| `openai/gpt-5.6-sol` at medium effort ("auditor_light") | the Fact Checker's audit of three or fewer changed lines (`LIGHT_AUDIT_UNITS`); any finding it returns is audited again on "auditor" before it counts | OpenRouter | less than a full audit (not yet measured) | `FactCheckerNode`, `agents.fact_checker.light_model` |
| `typesafe/jev-1.13` (Jev) | System 1 judge: 39 fixed questions | OpenRouter Decisions API (alpha) | fractions of a cent | `judging/questions.py`, `judging.py` |
| the theme's `voice.model` | Narration. Starter: `google/gemini-3.8-flash-tts`, a preset voice; a cloned narrator: e.g. `bytedance-seed/seed-audio-1-0` with `voice/master.wav` | OpenRouter | ~$0.09 per take (unpriced in responses) | `production/media.py`, `producer.narrate_passage` |
| `openai/whisper-large-v3-turbo` | Word timestamps for timing, subtitles, listen checks | OpenRouter | ≈ free | `media.transcribe` |
| `bytedance-seed/seedream-5-0-pro` (2K) | Keyframes | OpenRouter | ~$0.045 each | `production/stages/keyframes.py` |
| `google/veo-3.1-lite` (720p, 4 s) | AI morphs between keyframes | OpenRouter | ~$0.12 per take ($0.03/s) | `production/stages/segments.py` |
| `google/gemini-3.8-flash` | Vision: describes keyframes, morph frames and references for Jev | OpenRouter | ~$0.005 per call | `production/studio.py` (`perceive`) |
| `anthropic/claude-haiku-4.5` ("editor", effort low) | The Script Writer's line edits: new words for a few named lines, never the whole script; escalates to "writer" when a line it edited comes back | OpenRouter | ~$0.01 per edit (estimate; not yet measured on a run) | `ScriptWriterNode._revise_lines`, `agents/script_writer/LINE_EDIT.md` |
| `google/gemini-3.8-flash` ("listener") | The cold viewer: hears only the narration and says what it understood; a third model family, apart from the writer (Anthropic) and the fact checker (OpenAI) | OpenRouter | ~$0.01 per test | `editorial_director.listen`, `COLD_VIEWER.md` |
| `google/lyria-3-pro-preview` | Music generation per video, and `music-audition` | OpenRouter | ~$0.08 | used only when the theme has no locked bed (the starter) |
| Grounding DINO tiny | Focal point per keyframe | local CPU (`vision` extra) | free, ~9 s per image, cached | `production/focus.py` |
| Beat This! (`final0`) | Beats and bars of the music bed | local CPU (`music` extra) | free, once per track | `production/music_map.py` |
| `Xenova/nli-deberta-v3-small` (ONNX) | Faithfulness: line vs. its cited claims | local CPU (`learn` extra) | free, ~20 ms per pair | `story/faithfulness.py` |
| `BAAI/bge-small-en-v1.5` + logistic regression | Taste models that can replace Jev on subjective questions | local CPU (`learn` extra) | free | `learning/` |
| NLTK averaged-perceptron tagger | Finite verbs for the fragment check | local | free | `story/prose.py` |
| `textstat` | Syllable counts | local | free | `pace.syllables` |

Agent-to-model mapping and each model's effort and token limit: `config/config.example.json` (and so each channel's `config.json`)
(`agents`, `models`). Media models and prices: `production` in the same file. Every key:
[configuration.md](configuration.md).

## The Five Agents (Language Models)

Each agent is a folder with `agent.py` and `prompt.md` (its runtime instructions); its structured
output). Providers translate to OpenRouter in `providers/openrouter.py`. Every chat request sends
a strict schema and `provider.require_parameters: true`; temperature is never sent (reasoning
models reject it, and `require_parameters` would then match no endpoint). `max_output_tokens` is
a ceiling, 32k, because script revisions have used up to 27k.

| Agent | Model | Writes | Quirks seen |
|---|---|---|---|
| Fact Researcher | auditor | `ResearchPack`: classified claims (verified, reported, disputed, inference, unsupported), sources, safe wording | Only agent allowed web search. Research can take minutes. Integrity issues get one automatic repair. |
| Editorial Director | architect | `EditorialBrief` with the story ledger (beats with roles and what the listener knows; claims with story roles and meanings); `Critique`; `StoryDecisions` after the listener test | The plan is the control plane; plan review is off by default. As critic (on the `writer` model since 2026-10-04) it reads the whole script or storyboard against the theme and returns findings, never replacement wording. The cold viewer runs on the `listener` model. |
| Script Writer | writer; editor for line edits | `ScriptPackage`: units with arc phase, transition, claim IDs; `LineEditPackage`: new text for named lines | Given both a person's note and automatic findings, it acted on both and rewrote approved passages (on one script, v7). Now gets only the person's note on a person's revision, and a note on lines is a line edit: code keeps the other lines. Tends to pad toward the word budget. |
| Fact Checker | auditor; auditor_light for three or fewer changed lines | `FactCheckReport`: per-claim findings, routing | Incremental: unchanged units reuse their audit; a few changed lines get the light audit, confirmed at full effort if it finds anything. Raises `missing_context` notes every round (advisory). Returns constraints only (issue, evidence boundary, required qualification, forbidden implication, severity); before 2026-10-04 it wrote replacement sentences that made the prose legalistic. Marked a faithful plain paraphrase "exaggerated" until told not to. |
| Visual Director | writer | `VisualPackage`: scenes with anchor, `focus`, camera, motion, morph bridge, references | Often names the room before the subject in the anchor; hence the explicit `focus` field. A revision asked for three scenes may reword others. |

**Swapping a model:** change the alias in your channel's `config.json`. Structured output must be
supported; run one real topic and compare at each sign-off. The deterministic tests use
`providers/fake.py` and never touch these.

## Jev (System 1 Judge)

**What:** a small judge model answering fixed questions about a piece of state, through
OpenRouter's alpha Decisions API (`POST /alpha/decisions`). Each answer is one of:

- `noul` (yes/no): a probability of yes;
- `choice`: one option, with a confidence and per-option probabilities;
- `score`: 0–2 on described levels, with probabilities.

**How answers become routes** (`routing.answer_outcome`, thresholds in `decisions`):

- yes/no: pass at ≥ 0.6, fail at ≤ 0.2, unsure between;
- choice and score: unsure below 0.5 confidence;
- **blocking** questions (listed in `decisions.blocking`) route: a confident fail sends a
  targeted correction to the owner; unsure goes to the critic; advisory ones are recorded only;
- **measurements** (`claim_worth`, `claim_connection`, `unit_reaction`, `unit_intensity`,
  `script_voice`) never pass or fail; code reads them.

**The 39 questions** (`judging/questions.py`), by stage:

| Stage | Questions |
|---|---|
| Research and plan | `research_core`, `claim_worth`, `claim_connection`, `plan_curiosity`, `plan_payoff` |
| Script | `opening_hook`, `opening_orients`, `unit_pace`, `unit_supported`, `unit_plain`, `unit_clear`, `unit_meaning` (understood, not necessarily explained), `unit_spoken` (would a storyteller say it aloud; advice until validated), `unit_new`, `unit_reaction`, `unit_intensity`, `transition_tension`, `transition_why`, `script_payoff`, `script_story`, `script_voice` |
| Listener test | `beat_heard` (per beat: did the listener come away knowing `audience_knows_after`?), `story_heard` (could they retell the story chain?) |
| Storyboard | `scene_duplication`, `scene_meaning`, `scene_concrete`, `bridge_shared`, `visual_flow` |
| References | `reference_relevant`, `reference_matches` |
| Keyframes | `keyframe_matches_anchor`, `keyframe_on_theme`, `keyframe_shows_story`, `keyframe_framing`, `keyframe_clean` |
| Morphs | `segment_keeps_style`, `segment_shift`, `segment_holds_anchor`, `segment_morph` |

**Quirks (measured, keep in mind when reading flags):**

- **Often unsure.** Many answers land at 30–60% confidence. Blocking doubts go to the critic,
  which settles most; the remaining ones reach a review as "Jev was not confident".
- **Attributed claims:** `unit_supported` doubts lines that report what someone said
  ("The council answers that…"). These produced the false "state only what the claims
  support" notes on one script (v7).
- **It judges text, not pixels.** Keyframe and morph questions are answered from Gemini's
  description of the frames. A good image described oddly can fail (one scene's framing "fail
  20%" on a frame that looked right); a refused or empty frame described confidently can pass.
- **Segment questions are noisy:** "hold the anchor longer" and "make the morph gradual" came back
  on most of a first production's morphs at 28–59% confidence.
- **`script_voice` said "on voice" at 80–93%** on scripts a person heard as soulless; it is a
  measurement only since.

**Cost and speed:** a few hundredths of a cent per question batch; runs in parallel per stage.

**Learning:** every Jev answer is stored as an example (the theme's `learning/examples.jsonl`; about 1,200 after a first production's runs).
For subjective questions (`learning.local_questions`) a local model can replace Jev once it agrees
with the person's own labels at least as well; none is promoted yet (no person labels). Details:
[machine-learning.md](machine-learning.md#taste-models-the-self-learning-loop).

**Replacing or tuning:** thresholds are global (0.6, 0.2, 0.5) and hand-set. With about 8 person
labels per question they could be fitted per question (Phase 3 in machine-learning.md).

## Narration and Transcription

Detailed in [narration.md](narration.md). In short:

- **seed-audio** clones a designed voice from a 20 s reference; no seed, so every
  take differs (71–171 wpm). Re-taken when more than 1.2× off pace; about $0.09 a take, not
  reported in the API's usage, so `cost.csv` lists it as unpriced.
- **Whisper** transcribes each stretched take for word timestamps. It punctuates by guess (the
  listen check's "fragment" flags are mostly false) and may hear the script's word even when the
  voice slurs it ("clients").

## Pictures

### Seedream (keyframes)

- One still per scene, 2K, prompt built by `theme.keyframe_prompt` from the scene's anchor, the
  theme's style, and the scene's emotional field. Public figures are drawn from reference photos
  (Wikimedia) in the theme's way (`visual.figure`); a refused or garbled portrait is redrawn as a
  silhouette (`visual.silhouette`).
- **Signature** (cache key): model, resolution, prompt, theme reference digests, and the digests
  of the chosen reference photos. Any change redraws (paid). Saved runs keep their chosen photos.
- **Checks after drawing:** colour and brightness against the field's targets (measured in code),
  then Jev on Gemini's description. A failing keyframe is redrawn once (`keyframe_attempts` 2).
- **Quirks:** tends brighter and more colourful than the theme; the lamp-lit S3 measured 61
  against a limit of 55. Illustrated likenesses of real people are good from references.

### Veo 3.1 Lite (morphs)

- A 4 s video from one keyframe to the next, prompted with both anchors, the morph bridge, the
  camera, and the theme's morph style (`visual.morph`, `segment_template`).
- **Starts and ends almost exactly on the keyframes** (mean squared difference 1–8 on 0–65,025),
  so stitching problems are ours, not Veo's.
- **Refuses lifelike close-ups of real people** as input images ("violates usage guidelines").
  One scene's portrait was refused twice; drawn in shadow it passed. Refusals are now cached so
  a resume does not pay to be refused again.
- **Follows the morph prompt literally:** effect words ("hallucinatory",
  "kaleidoscope") produced neon synthwave on first attempts; "a grid of panels that flip"
  produced exactly that.
  Retries with fix notes came back on palette.
- Cost: $0.03 per second; a 4 s take is $0.12; failures retry once (`segment_attempts` 2).

### Gemini Flash (perception)

- Describes each keyframe, sampled morph frames, and reference photos as structured
  `Observation`s (subject, setting, composition, rendering style, colours, text, artefacts,
  framing, focus). Jev judges these descriptions.
- Cheap and fast. Its descriptions are the weak link in visual judging: Jev can only be as right
  as the description.

### Grounding DINO (focal point)

See [machine-learning.md](machine-learning.md#focal-point-grounding-dino-2026-10-03). Local,
free, cached; 11 of 11 keyframes right on a first production with a named `focus`; standing figures land on the
chest.

## Music

- **Lyria** can generate a bed from `music.prompt`, but the theme locks `music/bed.mp3` (generated
  once, auditioned, locked), so Lyria is not called in runs.
- **Beat This!** maps the locked bed once (`music-lock`) into beats, bars and four-bar phrases
  (`music/bed.map.json`, hand-editable). See machine-learning.md.

## Local Checks That Are Not Models

Signal processing and rules, listed so nobody mistakes them for learning: EBU R128 loudness
(`checks.integrated_loudness`), `signalstats` brightness/saturation/warmth, scene-cut detection,
word error rate, subtitle alignment (`difflib`), the reference narrator profile
(`narration_analysis.py`).

## Adding or Replacing a Model

Follow the playbook in [machine-learning.md](machine-learning.md#playbook-improving-a-component):
name the problem as researchers do, look for a published model first, check it runs on this CPU
under Python 3.14, contain it in an optional extra with cached results, keep tests deterministic
(fake or centre fallbacks), measure before and after on a real run, then update this register.
