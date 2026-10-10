# Runs and Review: How a Video Gets Made With You in Charge

You direct; the assistant and the pipeline handle the rest. You bring a rough idea; the assistant
comes back once with recommendations (format, length, scenes, angle, with costs), and from your
answers the run takes off. It stops for you only at its sign-offs, each before money is spent
on the next step, and a window opens on your screen when it does.

Last reviewed: 2026-10-10.

## One Channel, Several Shapes of Video

The channel (the theme) fixes the look, the voice and the music. Each video chooses its shape:

| Choice | Flag | Default | Notes |
|---|---|---|---|
| Format | `--format short` or `long` | the theme's (`short`) | `short`: 9:16, 40 s–3 min, for Shorts, TikTok, Reels. `long`: 16:9, 2–30 min, for YouTube, with a Story plan sign-off. Defined in the theme's `formats` ([themes.md](themes.md)) |
| Length | `--seconds 480` | the config's default, within the format | the planned length; the story may run up to 30% over (`choices.LENGTH_ALLOWANCE`), never past the format's limit |
| Scenes | `--scenes 24` | as the story and budget need | each scene is a picture and a morph into the next; fewer scenes hold longer and cost less |
| Cap | `--max-usd 15` | `production.max_usd` ($5 in a new channel) | the most the whole run may spend; long form needs more |

They are saved in `.work/choices.json`, so every resume makes the same video. A run carries on
in the format, length and scenes it started with; reopen with `--at` to change them. The cap may
change at any resume.

**Before choosing**, see what the options cost, free:

```bash
.venv/bin/content estimate --format long --seconds 480 --config themes/my-channel/config.json
```

It prints scene counts (a picture every 5, 8, 12, 20 or 30 s, and the recommended one: every
12 s in a short, every 20 s in long form), what the pictures and morphs cost, the whole video's
range, and whether it fits the cap. Writing costs are measured on short stories and scaled by
length for long form (an estimate until a long video is measured).

## Starting and Resuming

```bash
.venv/bin/content "The topic, or the whole idea in plain words" \
  --brief path/to/brief.md --format short --seconds 90 --config themes/my-channel/config.json
.venv/bin/content --resume runs/<topic>                 # carry on from where it stopped
.venv/bin/content --resume runs/<topic> --at fact_check # reopen an earlier review
.venv/bin/content "A new angle" --research runs/<earlier>/building-blocks/research.json
                                                         # start from research already paid for
.venv/bin/content ... --fresh-research                  # research again, even if cached
.venv/bin/content ... --detach                          # stop at each review, don't wait
.venv/bin/content review runs/<topic>                   # serve a waiting review's page
```

- A new run makes `runs/<topic>/` (the first six words of the topic) and stops at **Start**.
- `--brief` (a text or Markdown file: angle, story points in order, must-includes, things to
  avoid; see `fixtures/example_brief.md`) and `--sources` (facts and documents you already have,
  as JSON; see `fixtures/example_input.json`) are optional evidence and direction, never limits.
- A run already in that folder is never overwritten; resume it instead.
- `--research <file>` starts from a research pack an earlier run paid for (its
  `building-blocks/research.json`) and goes straight to the plan: no research is paid for. Use
  it for a new angle, length or format on a story already researched. Without it, research
  with exactly the same request (topic, brief, sources, model and prompt) comes from the cache
  for free anyway; `--fresh-research` asks again regardless.
- Every step of the run is saved as it finishes (`.work/steps.jsonl`). `--resume` carries on
  exactly where the run stopped: at the review it was waiting for (taking the answer if you
  already gave it), or by redoing the step it failed in. Nothing finished is made or paid for
  again. A closed terminal, a crash or a killed process loses at most the step in progress.
- `--at <stage>` reopens an earlier review instead, from `.work/resume.json` (the saved state at
  the latest review, written before each review is asked), and starts a new step file.
- Resuming continues in the same folder: no versioned copies. Everything paid for is reused from
  `.cache/`; only what changed is paid again.
- If the OpenRouter key holds less than the run's cap (`production.max_usd`; $5 in a new channel), the cap
  comes down to the balance less $0.25, and the run says so. Below about $1 it refuses.

## The Sign-offs

| # | Sign-off | You see | Approving unlocks | Costs about |
|---|---|---|---|---|
| 1 | Start | topic, brief, the video's format, length and scenes, and the cost table | research and writing | $1.50–2.50 for a short; scaled by length |
| – | Story plan (long form) | the story chain and the beats, with each beat's planned length | the script | writing and checks |
| 2 | Script | the fact-checked script, line by line, with fact-check notes on their lines, and what a first-time listener took from it beside the story the plan meant to tell | narration | about $0.12 a passage: 1.3 takes on average at $0.09 (the voice's measured share of re-takes; [narration.md](narration.md#3-recording)) |
| 3 | Narration | the narration over the music, passage by passage, with pace notes | pictures | about $0.08 a picture, redraws included |
| 4 | Pictures | the animatic and every scene's picture with its line (a staged scene: its rendered still, and a quick draft of its shot in the animatic) | morphs | about $0.17 a morph, retries included |
| 5 | Final cut | the finished video, scene by scene | the finished package | nothing |

Configured in `review.SIGN_OFF_STAGES`; the Script sign-off is `workflow.review_script` (on in
`config.example.json` and so in every new channel, off in the offline configs). The Story plan sign-off comes with a format
whose `review_plan` is on (long form), or `workflow.review_plan`; a plan the checks doubt is
always put to you. When the assistant runs the video, your answers to its intake questions are
your Start decision.

## When You're Needed

- A window opens by itself (Chromium in app mode, or your default browser), with a desktop
  notification: "Your video needs you: Script". Nothing opens for the assistant's reviews.
- The page shows one decision:
  - **You're deciding:** the question, in one sentence.
  - **Why it matters:** what approving sets in motion and roughly what it costs.
  - **Look for:** what to check, in plain words.
  - **The material:** the script as one reading column; the narration with its player pinned
    above the passages ("▶ Play from here" on each); the pictures and the cut with the video
    beside the scene cards.
  - **Changed:** on a second look, anything that changed since you last saw it is outlined and
    badged.
  - **Flags:** what the checks noticed, on the card it concerns, in plain words.
  - **Handled for you:** what the assistant already dealt with, folded away.
- **Comment** on any card: say what should change and why. You never need to write the wording.
  Each comment is sent as a targeted note ("S4: …", "U3: …"), which the pipeline routes to the
  right agent. "Anything else?" takes a note on the whole thing.
- On the Script sign-off, **Edit** puts a line in your own words: they go in exactly as typed,
  and no later rewrite may change them. Comments on lines change only those lines (a small
  model rewrites them; every other line is kept exactly). A note on the whole thing, or ticking
  **Rewrite the whole script around my notes**, rewrites the whole script instead
  ([architecture.md](architecture.md#revision-scopes)).
- On the Narration sign-off, each comment says what kind of problem it is: the words, a
  pronunciation (write `word = how to say it`), a pause or emphasis, or the voice itself. Only
  that passage is recorded again; only a note on the words goes back to the writer
  ([narration.md](narration.md#the-narration-sign-off-notes-by-kind)).
- Each script line says who last changed it and why ("Your words, revision 2"; "Line edit,
  revision 3: …").
- The button reads **Approve** with no comments, **Send changes** with some. **Save and stop**
  saves the run to resume later. After you answer, the window closes itself.
- Comments save as you type: in the browser, and to `.work/reviews/draft-N.json` while the page
  is served. Reopening the page brings them back.
- If nothing is listening when you press a button, the page says so and shows your answer,
  ready to copy into chat; the assistant answers the review for you with your words. Or run
  `content review runs/<topic>` and press the button again.

## Leaving a Review for Later (`--detach`)

With `--detach` the run does not wait at a review: it saves, prints how to answer, and exits.
At a sign-off it also starts `content review runs/<topic>` on its own, which serves the page
until you answer and then exits. Answer on the page or in chat, then
`content --resume runs/<topic> --detach` carries on with your answer. The assistant always
runs with `--detach`: its tools cannot keep a process waiting for you.

A review left open keeps its number: the resumed run finds `request-N.json` still open (no
answer yet, or a `detached-N` marker beside the answer) and uses `response-N.json` rather than
asking again.

## What the Assistant Does

- Never answers a sign-off: a response marked `"assistant"` is set aside as
  `response-N.refused.json` and the run keeps waiting for you. The code cannot tell who wrote
  `"person"`, so the assistant writes it only to pass on your decision from chat. Never dismisses a fact-check
  finding on your behalf; it puts it to you.
- Answers every review that is not a sign-off: research gaps, the writer's automatic stops,
  the visual plan, and fact fixes within the script it shows you.
- Marks its answers `assistant`; only your own decisions are recorded as `person`, and only
  those teach the learning models.
- Turns your comments into targeted notes; never rewrites passages you did not comment on.
- Never approves a sign-off for you.

## The Run Folder

```text
runs/<topic>/
├── review.html       the current review (served at http://127.0.0.1:8765/review.html)
├── brief.md          the topic and your brief
├── 1-script.md       the script at the Script sign-off
├── 2-narration.m4a   the narration over the music
├── 3-scenes/         S1.png…, animatic.mp4, story-sheet/
├── 4-final.mp4       the finished video
├── building-blocks/  each stage's output, readable (.md) and exact (.json): research, plan,
│                     script, fact-check, storyboard; written at every sign-off and at the end
├── decisions.md      every review answered, by whom, in order
├── cost.csv          what each session spent, by stage (opens in any spreadsheet)
├── calls.csv         every call: session, stage, what it made, model, seconds, tokens, cost
└── .work/            steps.jsonl (every step, to carry on from), resume.json (the state at
                      the latest review), reviews/request-N, response-N, draft-N and
                      detached-N, seen.json, session traces and call logs
```

The page is served while the run waits for a review, or by `content review` for a run that
stopped at one; afterwards `review.html` still opens from the folder and shows the last answer.

When the run finishes after the Final cut sign-off, its signed-off files (not the previews, the
review page or `.work/`) are kept in the cloud bucket, if the configuration names one
([storage.md](storage.md)).

## Answering From Chat or by File

A review is `runs/<topic>/.work/reviews/request-N.json` (with `"sign_off": true` on yours). The
run waits for `response-N.json`:

```json
{"action": "approve" | "revise" | "stop", "feedback": "S4: …", "decided_by": "person",
 "edits": {"U3": "the person's own words for the line"}, "scope": "lines" | "script" | null}
```

`edits` and `scope` are optional: `edits` only at the Script sign-off; `scope` unset lets the
notes decide (lines when every note names its lines).

The page writes this for you. The assistant writes it when you answer in chat (with your words
and `"person"`), or for its own reviews (`"assistant"`).

## Costs and Caching

- Every paid generation is cached by its full request in `.cache/` (gitignored; deleting it
  means paying again): pictures, voices, video, and every agent's text answer (research, plan,
  script, fact check, storyboard, critic, listener) under `.cache/text/<operation>/`. Asking
  the same thing again, in this run or another, costs nothing; any change to the request (the
  topic, the brief, the model, the prompt) is a new request.
- `.cache/INDEX.csv` lists everything that was paid for, one line each: when, what (scene S4
  keyframe attempt 1 and its prompt, passage P2 take 0 and its words, research), which model,
  the cost, and the file. Open it in any spreadsheet.
- With a bucket, the run so far is kept at every sign-off (`runs/in-progress/<topic>/`), and
  moves to `runs/finished/<topic>/` at the end ([storage.md](storage.md)).
- A resume reuses: every finished step (from `steps.jsonl`, or research and writing from
  `resume.json` with `--at`), chosen reference photos, every
  narration take, keyframe, morph and refusal with an unchanged request.
- Before approving the Pictures sign-off on a resumed run, unchanged keyframes mean unchanged
  morphs; a redrawn keyframe re-makes its two morphs.
- The listener test after each verified script costs about $0.01; each oral revision round it
  triggers costs about $0.15–0.40 (a writer revision, Jev, the fact check of changed lines,
  another listener test), at most two rounds. These are estimates; `cost.csv` shows the real
  spend under `writing` and `checks`.
- `cost.csv` is a table with one row per session (each start or resume of the run, counting
  only that session's calls) and a
  total row. Columns: when it finished, where it stopped, calls, then dollars by stage
  (`writing`: every text model; `checks`: Jev and the vision model; `narration`, `pictures`
  with reference downloads, `morphs`, `music`), the priced total, unpriced calls, and an
  estimate for unpriced narration takes (the provider does not price them; about $0.09 each).
  The rows are kept in `.work/costs.jsonl`; stages are mapped by `spend.cost_stage`. Across all
  runs and tools, with what is left on each service: `content spend` ([spending.md](spending.md)).
- `calls.csv` breaks the same spend down per call (one row each, appended per session), so a
  costly or slow artifact can be found: `made` is the operation (`research`, `plan`, `script`,
  `script_line_edit`, `fact_check_light`, `critique_script`, `narration`, `keyframe`…). Each
  session's trace (`.work/session-N.trace.json`) also lists every line edit with its author and
  reason.
