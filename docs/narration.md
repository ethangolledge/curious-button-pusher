# Narration: From Planned Words to the Finished Mix

The narration is the spine of every video: it is written first, recorded first, and everything
else (scene lengths, music edit, subtitles, morph timing) is laid against it. This document
traces it end to end: every number, every check, why each exists, and what moves when you
change something. Every number marked as a theme setting comes from the theme
([themes.md](themes.md)); values quoted are examples of what a setting could be, and the
measurements come from a first long-form production made with this pipeline.

Last reviewed: 2026-10-09.

## The Path at a Glance

```text
Plan (Editorial Director)       beats with planned words → sized against the music
  ↓  target_seconds, word_budget, longest_seconds, music peak
Script (Script Writer)          units grouped into passages (one per arc phase)
  ↓  free checks: length, robotic writing, faithfulness (NLI); Jev's narration questions
Fact check → Script sign-off    the person approves the words before any audio is paid for
  ↓
Recording (production)            one take per passage, cloned voice, its beat's direction
  ↓  measure natural pace → stretch towards 160 wpm, at most 1.2× → re-take only if short
Transcription (Whisper)         word timestamps; listen checks; word error rate
  ↓
Timing                          shortest music edit that holds it; breaths; turn on the peak;
                                passages start on beats; scenes inherit unit windows
  ↓
Subtitles (local)               script words on heard timings, 3-word phrases, no overlaps
Mix (local)                     voice compression, music 15 dB under and ducked, -14 LUFS
  ↓
Narration sign-off              the person listens before any picture is paid for
```

## 1. Planning the Length

**Code:** `story/weights.allot_words`, `workflow/gates.size_story`, `story/pace.planned_seconds`,
`pace.story_seconds`, `pace.word_budget`.

The Editorial Director plans 4–7 beats (arc phases) and gives each claim a story role; code gives
each beat its words from those roles ([Time by story role](#time-by-story-role)), then turns
words back into seconds at the voice's **measured rate** (`VoiceSpec.rate`, below):
`seconds = 60 × words ÷ 143` on the reference voice (the first beat at the hook pace, × 0.92),
adds a typical breath between beats (the mean of the four pause values, 0.59 s) and the tail
(1.5 s).

**The measured rate.** Each take is stretched towards the target (160 wpm) but no more than
1.2×, so what a narration comes out at depends on the voice's own speed. After every run,
`learning.after_run.record_narration` measures every recorded take (trimmed seconds, words)
into the theme's `learning/narration.jsonl`; when the configuration loads,
`theme.with_measured_voice` takes this voice's takes (same model, voice and reference clip)
and `theme.measure_voice` sets:

| `VoicePace` | Meaning | Reference voice (46 takes, 2026-10-04) |
|---|---|---|
| `natural_median` | its own speed, before any stretch | 119 wpm |
| `delivered` | the median pace a take reaches within the stretch limit: this is `rate` | 143 wpm |
| `short` | share of takes more than `length_tolerance` (15%) below `delivered`, which are re-taken | 0.24 |

With fewer than 8 takes (`MIN_MEASURED_TAKES`), or without a learning store (the offline
configs), the rate is the target, 160.

That estimate picks the nearest **edit of the music** (`score.choose`). The music bed is cut only
on whole four-bar phrases, so only certain lengths exist. The edit's length minus the middle of
the outro allowance becomes `target_seconds`. The writer gets:

| Input to the writer | Meaning | Hard? |
|---|---|---|
| `target_seconds`, `word_budget` | the planned length and roughly how many words fill it | guide |
| `longest_seconds`, `longest_words` | the longest music edit under 3:00, minus the shortest outro | **hard** |
| `music.peak_starts_at` | when the music peaks, to place the turn near it | guide |

Sized at 160 wpm, scripts overran once recorded (the first production (v13): predicted 167.5 s, recorded
174 s; the re-cut: 171 s against 168 s). Sized at the measured rate, a typical take lands on the
estimate; a narration still varies by a few seconds either way, which the music edit absorbs.

## 2. Writing for the Ear

**Code:** `agents/script_writer/` (model alias `writer`: Claude Sonnet), its `prompt.md`.

### The standard: understanding per minute

The narration is judged by how much a first-time listener understands, hearing it once, not by
how much information it holds. Research is complex; the finished story should not feel
complex. Every passage answers three questions: **what just happened, why it matters, and why
the listener is hearing this next.** Cutting for time removes repetition, secondary names,
dates and side details, never the sentences that explain.

A first production's final cut taught this the hard way: strong research came out as a "slurry
of facts", with terms nobody explained, the same sum said twice as if two events, and an ending
the story never set up.
The drafting chain builds understanding in at every stage, under one authority structure:
truth defines the evidence boundary, the Story Architect decides what matters, the writer
owns every word, a first-time listener tests whether it was understood, and Jev and code only
judge ([architecture.md](architecture.md#who-decides-what)).

```text
plan + ledger → writer → free checks → Jev → (critic on doubt) → fact check (constraints)
  → cold viewer (narration only) → Jev: heard vs ledger → audience verdict
      heard                        → Script sign-off, with the listener's report
      stumbled on a required claim → story decisions (Architect) → writer
      term, lost thread, missed beat → oral revision (writer) → … fact check of changed lines → listener again
```

| Stage | What it does for understanding |
|---|---|
| Research | plain background claims for every term, institution or deal the story turns on; the correct reading of figures that are easy to misread; safe wording in everyday words |
| Plan (Story Architect) | the `story_chain` first; the ledger: each beat's role, purpose, what the listener knows after it, the question it answers and leaves, why the next follows; each claim's story role, job and meaning; `explain` for terms; `required_context` only where its absence would mislead |
| Code | each beat's time from its claims' story roles ([below](#time-by-story-role)); blocks a sentence bringing in five or more new names and figures (`prose.dense_issues`) |
| Writer | the research summary, the ledger and every fact constraint; explains or cuts every term, gives every number its meaning, introduces a fact once, leads with the event; cuts fluff before connective tissue; in the oral revision, rewrites the whole narration as spoken language; a note on named lines is a line edit of those lines only ([architecture.md](architecture.md#revision-scopes)) |
| Jev | `unit_clear`, `unit_meaning` and `transition_why` for the plan's audience; after the listener test, `beat_heard` and `story_heard` compare what was heard with the ledger |
| Critic | checks first whether a listener could retell the story chain |
| Fact checker | constraints only, never wording; a faithful plain paraphrase passes; checks what a listener would conclude from a number |
| Cold viewer | `google/gemini-3.8-flash`, given only the narration: what it is about, what happened and why, why it matters, the facts that stuck, the question, what is unresolved, where it was confused, what seemed unrelated, which terms needed prior knowledge, where it lost the thread |
| Story decisions | a stumble on a required claim goes to the Architect: keep, move, simplify, merge, demote, or cut. Only the Architect may change what the story requires, and the change is recorded in the plan |
| Sign-off | the Script sign-off shows the listener's account beside the story chain; only the person can answer it (`review.FileReviewer`) |

Oral revisions spend the script's revision allowance (`workflow.max_revisions.script`, 2). When
it is spent and the listener still stumbles, the Script sign-off shows what is left.

### Time by story role

Code gives each beat its words (`story/weights.allot_words`). Each claim's story role sets a band
of seconds (theme `writing.weights.role_seconds`; both themes: spine 12–25, essential context
5–10, supporting evidence 3–6, colour 0–4, expendable 0). Within its band a claim sits higher the
stronger its score and the more claims rest on it (`supports_claim`). A beat gets its claims'
seconds plus `transition_seconds` (2), never less than `beat_floor_seconds` (4). When the story
runs past the longest video, colour goes first, then supporting evidence and essential context
shrink to their band minimum; the spine is never squeezed. Important moments slow down;
bridges pass quickly.

### Regression: `content eval`

A channel's `themes/<name>/examples/<story>/negative.json` holds a script a person rejected, with every failure they
named pinned to its line; `positive.json`, once it exists, the version they approved. `eval`
runs the listener, Jev's comprehension questions and the free checks on each, and prints which
failures were caught and by what (paid: one listener call and a few dozen Jev calls per
fixture, about $0.01). A blocking Jev answer that comes back unsure is shown as a doubt: in a
real run it goes to the critic.

The first production's negative fixture pinned seven: an institution with no stated
significance (U2), "the route" with no route set up (U3), report language (U6), fees with no
meaning (U8), a side deal that strayed from the hook (U10), "recusal" untranslated (U15), and an
ending never set up (U16). Measured 2026-10-04, three runs: all seven caught every time. The
starter kit's `examples/` has a small made-up sample of the format.

- The listener caught U2, U10 and the ending (U16) every run, and terms of art (due diligence,
  the Public Investment Fund) most runs. A model knows "recusal" itself, so the listener is told
  to judge as a typical viewer, not as itself; before that it missed both "recusal" and the
  ending.
- Jev's `unit_clear` failed U2, U3, U6, U8 and U10 outright, and was unsure on "recusal" (U15)
  and on most other lines of this script, so a script this dense sends many doubts to the critic.
- Jev's `script_payoff` passes the ending even when asked about chronology (0.88–0.92): the
  listener owns that catch.
- Not yet measured: false alarms on a script the director approved. Add it as
  `positive.json` beside the negative one.

Offline, only the free overload check fires (on U8).

### Units and passages

- Units are one or two sentences, each tagged with its arc phase, transition (`build`, `hold`,
  `release`, `turn`) and claim IDs.
- **Consecutive units in the same phase form one passage, recorded in one take**
  (`pace.passages`). This is the most important narration decision: one take per passage lets the
  narrator's own intonation carry sentence to sentence. Before 2026-09-27, each unit was its own
  take, and the intonation reset 11 times ("a school presentation").
- The theme's rhythm guide (`writing.rhythm`) gives the sentence-length profile measured on Map
  Men (mean 15.6 words, a quarter short, a third long). It is advice, not a check.
- The lexicon (`voice.lexicon`, e.g. `BBC → B-B-C`) is applied to the text the voice reads
  (`theme.spoken_text`). The subtitles always show the script's own spelling.

### Free checks on the text (before any money)

| Check | Code | Blocks? | What it catches |
|---|---|---|---|
| Length | `pace.length_issues` | past `longest`: structural (forces a rewrite); else advisory | narration past the longest video, or more than 15% off the plan |
| Verbless fragments | `prose.fragment_issues` | yes | "The minister's brother, speaking in Geneva." read as a dramatic statement. Over 5 words, or more than 2 short ones |
| Set-up questions | `prose.setup_question_issues` | yes | "And the day job?" answered by the next sentence |
| Too many questions | `prose.question_issues` | yes | more than 2 questions (`MAX_QUESTIONS`) before the ending passage: a presenter building suspense. The ending's own question never counts. Its note names its lines, so the fix is a line edit |
| Stock phrases | `prose.stock_phrase_issues` | no (advisory) | phrases that sound generated or borrowed (`STOCK_PHRASES`: "does not add up", "does not sit right", "the plot thickens"…), contractions expanded. Advice until a phrase list is shown not to flag earned uses |
| Ending that repeats | `prose.repetition_issues` | yes | the ending restating a phrase already heard (names and bare number words excluded after false alarms) |
| Overloaded sentences | `prose.dense_issues` | yes | one sentence bringing in five or more new names and figures (`MAX_NEW_DETAILS` 4); names heard earlier and small counts do not count. On the first production's final it flags only the fees sentence (seven) |
| Faithfulness | `story/faithfulness.py`, NLI (`Xenova/nli-deberta-v3-small`) | no (advisory) | a sentence that every cited claim contradicts (contradiction ≥ 0.8) |

### Jev's narration questions

Jev (`typesafe/jev-1.13`) answers fixed questions per unit and per script
(`judging/questions.py`). The ones that shape narration:

| Question | Asks | Kind | Effect |
|---|---|---|---|
| `opening_hook` | how strongly the opening makes a listener keep listening | score 0–2 | blocking |
| `opening_orients` | is the listener oriented by ~8 s | yes/no | blocking |
| `unit_clear` | would the plan's audience, hearing it once, understand every term, name and number, and why it is told | yes/no | blocking (new 2026-10-04) |
| `unit_meaning` | would the listener understand what the line's facts show (from the ledger), said outright or plain from the telling: understood, not necessarily explained | yes/no | blocking (softened 2026-10-04: it pushed the writer to explain every fact) |
| `unit_spoken` | would a storyteller say it aloud as written: no question inserted for drama, stock phrase, judgement beyond the claims, officialese or page-built clauses | yes/no | advisory until validated (new 2026-10-04) |
| `unit_pace` | too slow / right / overloaded, for the audience | choice | advisory |
| `unit_plain` | not portentous (it does not check jargon; `unit_clear` does) | yes/no | advisory |
| `unit_new` | moves the listener on: a new fact, or what something already told means | yes/no | blocking |
| `unit_supported` | supported by its claims | yes/no | blocking |
| `transition_tension` | build / hold / release vs. the previous unit | choice | checked against the plan |
| `transition_why` | does the listener know why this comes next (the plan's `leads_to_next` given) | yes/no | blocking (new 2026-10-04) |
| `beat_heard`, `story_heard` | after the listener test: did they come away knowing what each beat should leave them with, and could they retell the story chain | yes/no | blocking (new 2026-10-04) |
| `unit_reaction`, `unit_intensity` | lean in / brace / recoil / settle, and how strongly | measurement | sets each scene's emotional field (visuals) |
| `script_story` | one person telling a story, or a list | yes/no | advisory, read by the critic |
| `script_voice` | on voice / flat / overdone / unfair, against the theme's `writing.voice` | choice | measurement only (it said "on voice" on scripts heard as soulless) |

**Quirk:** before `unit_clear`, nothing asked about the listener. On the first production's final, Jev rated
every line's pace "right" and wording "plain", including "The route began…" and "due-diligence
gaps"; `unit_new` even failed explanations as restating. Unit and transition questions now see
the plan's audience.

**Quirk:** Jev is often unsure (30–60% confidence) on `unit_supported` for attributed claims.
Those doubts go to the critic, not straight to the writer. On one script (v7), the "U11–U14 state only what
the claims support" notes were such false alarms; see the sign-off rule below.

### The Script sign-off

The person approves the fact-checked script before narration is paid for. Only the person can:
a sign-off response marked `"assistant"` is set aside as `response-N.refused.json`, and the run
keeps waiting. The field is self-declared, so the assistant writes `"person"` only to relay the
person's own decision. Fact-check findings (`exaggerated`, `missing_context`) are shown on
their lines; the assistant never dismisses them on the person's behalf. A revision there sends
the writer **only the person's note** (`graph.request_human_review` clears `revision_notes`), and
the writer's `prompt.md` says to change exactly that and keep every other sentence word for word.

## 3. Recording

**Code:** `production/stages/narration.py` (`narration_tasks`, `narrate_passage`, `_take`),
`production/media.py` (`OpenRouterMediaProvider.speech`), `theme.py` (`VoiceSpec`).

### The voice

The theme's `voice` section chooses it. Two ways:

- **A preset voice** (`voice.voice`, no `reference_audio`): the starter theme uses Google's
  `gemini-3.8-flash-tts` voice "Algenib", with provider-style direction.
- **A cloned voice** (`reference_audio`): every request carries the theme's `voice/master.*` and
  its transcript as `input_references`, so any cloning model speaks the same narrator. The
  first production cloned a designed voice (about 20 s) with `bytedance-seed/seed-audio-1-0`.

- **Direction:** `direction_style` says how the model takes it (`inline` prepends it to the text,
  `google` and `openai` use provider options; `media._directed`). Each passage gets its own,
  from the script (`theme.narration_direction`): the writer's `voice_direction.tone`, then its
  beat's `voice_direction.beats[phase]` (or the script's `delivery`), then any pause or
  emphasis the person asked for at the Narration sign-off. The theme's `voice.direction` is used
  only for a script that gives none. The writer is told never to ask for drama or intrigue.
- **No seed:** each request is a fresh performance. The same passage has come out at 113 and 147
  wpm on two takes.
- **Cost:** not priced by OpenRouter's response (`Usage` has no cost). Measured from the key
  balance on 2026-10-03: about **$0.09 per take**. A passage needs `VoiceSpec.expected_takes`
  on average: one, and another for each that falls short (1.3 on the reference voice, from its
  measured `short` share; every allowed take, 3, before a voice is measured). When takes had to
  reach 160 wpm, a passage needed about three (19 for 6 passages on 2026-10-03, 8 for 3 on
  2026-10-04). `cost.csv` lists takes as unpriced calls.
- **Choosing one:** `voice-audition`, `voice-design`, `voice-lock` ([themes.md](themes.md#tools)).

### Pace: one take, stretched, re-taken only when short

The voice model's speed varies wildly from take to take: 88–148 wpm across the reference voice's
46 takes (median 119). So pace is **measured, then adjusted**:

1. **Trim silence** from both ends (`assemble.TRIM_SILENCE`, −45 dB).
2. **Measure** the take's natural rate: `words ÷ seconds × 60`.
3. **Target:** 160 wpm (`voice.words_per_minute`); the first passage 147 wpm (`hook_pace` 0.92).
4. **Stretch** towards the target with ffmpeg `atempo` (pitch kept), clamped to `tempo_range`
   (0.9–1.2×).
5. **Keep it** unless it still falls more than `length_tolerance` (15%) below the rate the
   script was sized at (143 wpm, so below about 122). Only then is it re-taken, up to `retakes`
   (2) more; the take needing the least stretch is kept (`|log(target/natural)|`). The first
   take keeps its original cache key, so takes already paid for are reused. A passage slow on
   every take is flagged at the Narration sign-off.

**Why 160 and 1.2×:** on the first production v12 the director listened to three versions: as rendered
(stretched to 160, up to 1.6×), untouched (too slow, "very very slow"), and a gentle weighted
stretch. Verdict: 160 is right; only the passages stretched 1.48–1.6× lurched. The cap is 1.2×
since then. **The consequence:** this voice, at its own median of 119 wpm, reaches about 143
within the cap, not 160; re-taking until 160 cost about three takes a passage and still fell
short. Since 2026-10-04 the narration is sized at the 143 it delivers and takes are kept unless
clearly short. Reaching 160 reliably needs a faster voice or a higher cap: evidence for the
voice decision, which is the director's.

**Quirk, words vs. syllables:** the rate is measured in words, so a passage dense with long
words ("Congressional", "relationships", 1.8 syllables per word) looks slow and gets sped up
more than a light one (1.4). Measured in syllables, one passage's (P5) third take was as brisk as P3.
A syllable-based target would even out perceived speed. It is not built; see Levers below.

**Quirk, a passage can be slow by nature:** One passage (P4, a return after a pause in the story) came out at
103–108 wpm on all three takes. The narrator reads that content with weight. Re-takes do not fix
it; either the words are trimmed or the passage stays slower.

### Cache and money

- Each take is cached by its full request (model, voice, reference digest, text, direction,
  take number) in `.cache/speech/`. Changing **any** of those re-records that passage (paid).
- Unchanged passages are never paid for twice. A one-word script change re-records only its
  passage (the first production (v13): 2 of 6 passages).
- Changing the script's `voice_direction` (tone, a beat's direction), `voice/master.wav`, or the
  model re-records the passages it touches; a script without a direction falls back to the
  theme's `voice.direction`, which then re-records everything.

### The Narration sign-off: notes by kind

Each passage's comment says what kind of problem it is; each is fixed with the least work, and
only its passage is recorded again (`director.narration_fixes`, in `apply_director_notes`):

| Kind | Written as | Fixed by | Re-done |
|---|---|---|---|
| The words | `P3: …` or `P3 [wording]: …` | a note on the passage's lines (`U5, U6: …`), a line edit | the line edit, its checks, the Script sign-off, that passage |
| Pronunciation | `P3 [pronunciation]: Eniac = EN-ee-ack` | the script's `voice_direction.say_as`, applied after the theme's lexicon | that passage only, nothing re-judged |
| A pause or emphasis | `P3 [pause]: a beat before the number` | added to that passage's direction (`passage_directions`) | that passage only |
| The voice itself | `P3 [voice]: …` | a fresh take, numbered past the rejected ones (`retakes_asked`) | that passage only; the note stays in `decisions.md` as evidence about the voice |

A pronunciation note that does not read `word = how to say it` becomes a direction instead. A
pause or emphasis note has no effect on voices that take no direction.

## 4. Transcription and Listen Checks

**Code:** `media.transcribe` (OpenRouter `openai/whisper-large-v3-turbo`, effectively free),
`checks.listen_issues`, `checks.word_error_rate`.

Each stretched clip is transcribed for word timestamps (cached by audio digest). From them:

| Check | Threshold | Shown as | Reliability |
|---|---|---|---|
| Fragment: the voice ended a sentence where the script runs on | Whisper put `.?!` mid-script-sentence | advisory at Narration | **noisy**: Whisper punctuates by guess; most flags were false |
| Unmarked pause | ≥ 0.45 s where the script has no punctuation | advisory | fairly reliable; sometimes a deliberate beat ("And then… he came back") |
| Word error rate | > 20% of words differ | advisory | reliable for missing or garbled lines |
| Stretch limit | passage needed more than 1.2× | advisory | reliable |

**Quirk, words Whisper "corrects":** subtitles always show the script's words, and Whisper may
hear what the script says even when the voice slurs it. One script's "clients" sounded like
"client" to the director; Whisper heard "clients". Only a person's ear catches this.

## 5. Timing: Music First, Narration Inside It

**Code:** `production/stages/narration.py` (`time_scenes`), `production/score.py`, `production/timing.py`,
`production/music_map.py`.

**The music comes first and the story fits inside it,** the way a producer edits a track: whole
phrases only, joined on bar lines. All code, deterministic and free per video.

- **Locking a bed** (`music-lock <track>`, once per theme): the track is copied into the theme,
  mapped by Beat This! (a pretrained beat and downbeat model, CPU, seconds) into bars and
  four-bar phrases named by loudness (intro, build, peak, outro), and saved as
  `music/bed.map.json`, readable and correctable by hand. The command prints every length the
  track can be edited to and renders a voice-over preview.
- **Arrangements:** the track as written; shorter, with whole build phrases taken out; longer,
  with builds and the peak repeated. The track always keeps its own opening and ending; joins fall
  on a downbeat with a one-beat equal-power crossfade; the edit renders as 32-bit float so a hot
  track never clips at a join. A 75 BPM, 20-bar bed, for example, offers 40.6–117.4 s as
  written, longer by repeating phrases up to the theme's `format.max_seconds`.
- **Without a locked bed** (the starter theme), music is generated per video at the narration's
  length from `music.prompt` by `production.music_model` (none if that is unset), with no beat
  sync.

With a mapped bed:

1. **Speech length** = Σ passage durations + breaths + tail (1.5 s). Breaths come from each
   passage's opening transition: build 0.35 s, hold 0.5, release 0.7, turn 0.8.
2. **Fit:** the shortest music edit that holds the speech plus the shortest outro (`score.fit`).
   If none fits, the run goes back to the script with "cut a beat" (structural). This is the
   **168 s ceiling** on the first production: the longest edit under 180 s, minus the outro.
3. **Spare time** goes first to the breaths (up to +0.4 s each), then to a lead-in before the
   first word (up to 1.5 s); the rest lets the music play out.
4. **The turn on the peak:** the passage holding the story's turn (the first `reveal`, else the
   first `turn`) is moved onto the peak's first bar when it is within 1.5 s, by spreading the
   difference over the breaths before it (`score.land`).
5. **Passages on beats:** each passage start is nudged by up to 0.25 s onto a beat
   (`score.on_beat`), never shrinking a breath below 0.05 s, and only if the whole still fits.
   Inside a passage the narrator's timing is never touched.
6. **Unit and scene windows:** script words are aligned to the heard words (`subtitles.align`);
   each unit spans its first word to its last, and each scene spans from its first unit's start
   to the next scene's (`timing.scene_timings`). The narration is the clock for the pictures.

## 6. Subtitles

**Code:** `production/subtitles.py`, theme `subtitles`.

- Words are the **script's**, timed by what was heard; unmatched words are spread evenly
  between matched neighbours (so "B-B-C" spoken shows as "BBC").
- Phrases of at most 3 words (`max_words`), broken at punctuation or after 1.8 s.
- One event per word: the phrase shown, the current word highlighted (`#F2D335`), Archivo Black
  78 px, uppercase, 640 px above the bottom.
- **No overlaps:** each event ends where the next begins. Aligned timings overlapped by up to
  0.4 s before 2026-10-03, and libass stacked two lines (the first production, v15).

## 7. The Mix

**Code:** `assemble.narration_track`, `assemble.mix_audio`, theme `music`.

1. Passages placed at their start times on one 48 kHz mono track (`adelay`, padded to the video).
2. Voice: gentle compression (threshold 0.1, ratio 3, attack 5 ms, release 150 ms, +1.5 makeup).
3. Music: set **15 dB below** the voice's measured loudness, then **ducked** under speech by a
   sidechain compressor (threshold 0.02, ratio 2, attack 200 ms, release 1.5 s).
4. Two-pass `loudnorm` to **−14 LUFS**, true peak −1 dB (social platform targets); AAC 320 kbps.

The Narration sign-off plays exactly this mix (`2-narration.m4a`).

## 8. What Changes What

| If you change… | Then… | Costs |
|---|---|---|
| a word in one unit | that passage re-records; timing, subtitles, mix rebuild | ~$0.09–0.27 |
| a beat's direction (`voice_direction.beats`) or the script's tone | the passages it touches re-record | ~$0.09–0.12 per passage |
| `voice.direction` | only scripts that give no direction use it | per passage |
| `voice/master.wav` or `voice.model` | every passage re-records; re-audition first | ~$0.55+ |
| `words_per_minute` | every stretch changes (free); the measured rate may change; longer or shorter video | free |
| `tempo_range` / `retakes` | the measured rate and the share of takes re-taken change | ~$0.09 per re-take |
| new runs with the voice | more takes measured; the rate settles | free |
| `pauses`, `tail_seconds` | timing and length change; music edit may change | free |
| `lexicon` | affected passages re-record | per passage |
| music bed (`music-lock`) | new beat map; all edits and lengths change; the 168 s ceiling moves | free (if the bed exists) |
| `subtitles.*` | only the final encode reruns | free |
| `music.below_voice_db`, ducking, loudness | only the mix reruns | free |

## 9. Measured Facts Worth Keeping

- Seed-audio natural pace with the reference clip: 88–148 wpm over 46 takes, median 119; within
  the 1.2× cap a take delivers a median 143 wpm, and 24% fall more than 15% short. The same text
  varies by up to 30% between takes. Syllables per word across passages: 1.41–1.82.
- The first production's reference clip (`master.wav`) ran at 139 wpm.
- The first production's untouched narration: 211 s; at 160 wpm with up to 1.6×: 165 s; with the 1.2× cap and
  re-takes: 173 s (then cut by 15 words to fit 168 s).
- Internal pauses over 0.3 s total 2–8 s per long passage; trimming them to 0.45 s would save
  1–3 s per slow take. Rejected for now because those pauses carry the delivery.

## 10. Levers for Optimising

In rough order of value:

1. **Syllable-based targets.** Bring every passage to the same syllables per second, so dense
   passages are not over-stretched. The planner's estimate would need to count syllables too.
2. **Weighted stretch inside a passage.** Prototyped 2026-10-03 (rubberband, per line, supporting
   lines up to the cap, hook, reveal and ending untouched). The director preferred the plain cap.
3. **A better stretcher.** ffmpeg's `rubberband` filter is installed and preserves formants;
   `atempo` is used today. Untested by ear in the full mix.
4. **Fix the listen checks' noise.** The "fragment" check flags Whisper's punctuation, not the
   voice; most flags were false. Consider requiring a pause after the period too.

## 11. Known Gaps

- A take is re-taken only for pace. A misread (high word error) or a clipped question ending is
  flagged at the sign-off, not re-taken automatically.
- Narration cost is unpriced; budgets count it at past averages, which are zero when no priced
  history exists.
- The hook pace (147 wpm) is applied as a target, but a hook take that comes out fast is slowed
  only to 0.9×.
