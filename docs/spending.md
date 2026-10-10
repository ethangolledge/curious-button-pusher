# Spending: What Has Been Spent, and What Is Left

Last reviewed: 2026-10-10

Every dollar is tracked in one place per channel: `themes/<name>/spend.sqlite`, a small
database kept with the channel (private, and saved to the bucket with it). `content spend
--config themes/<name>/config.json` shows it all; the assistant runs it before every video and
whenever you ask "how much have I got left?".

## What is tracked, and how

| What | Where it comes from | When |
|---|---|---|
| **Every paid call**: what made it (research, a keyframe, a narration take…), its stage, the model, tokens, seconds and cost | the provider's reply to each call | at the end of every run session; after every channel tool (`voice-audition`, `voice-design`, `music-audition`), `eval` and `train` |
| **What you said you have** on each service: credit added, a key's limit, a monthly alert | you, once, and whenever it changes: `content spend budget openrouter 20 --config …` | when you set it up, or top up |
| **OpenRouter's own figures**: credit added and used on the account, the key's limit and what it may still spend, and when the key stops working | OpenRouter (free to read) | at the start of every run, and each time `content spend` runs |
| **Google Cloud storage**: what the bucket holds, and this month's cost beyond the free 5 GB | the bucket itself | each time `content spend` runs |

Not tracked: your Claude subscription (Claude Code itself), which is billed by Anthropic.

The tables, for anyone who wants to look inside (any SQLite viewer opens it): `calls` (one row
per paid call), `budgets` (one row per service), `balances` (one row per reading).
`src/content/spend.py` is the whole of it.

## Calibration: what nobody priced

Some calls are charged but not priced in the reply: narration takes, mostly. The ledger counts
them separately. Between two OpenRouter readings, OpenRouter's used figure goes up by exactly
what was spent; the ledger compares that with what it priced in the same window. The
difference is what it could not see, and when unpriced takes explain it, it gives the real
cost of a take (the report says "calibrated"; until then it uses the estimate of $0.09 a take
and says "estimated"). A difference with no unpriced takes means spend from elsewhere: another
machine, or the website.

## What is left, and the limits

- **OpenRouter:** what can still be spent is the account's balance, or less if the key's limit
  is lower. Every run reads it first; a run never plans to spend more than it (its cap comes
  down to fit, less $0.25, and it refuses below about $1).
- **The run's cap** (`production.max_usd`; $5 in a new channel) limits one video.
- **Warnings** in the report: less left than one video's cap; the key stopping within 30 days;
  the bucket near its free 5 GB.

## Commands

| You want | Run, or ask the assistant |
|---|---|
| everything: what is left, what was spent, by stage and by run, and warnings | `content spend --config themes/<name>/config.json` |
| record what you have | `content spend budget openrouter 20 --config …` (`--kind credit`, the default: added to the account; `limit`: a key's cap; `monthly`: an alert or allowance) |
| Google Cloud's alert | `content spend budget google-cloud 1 --kind monthly --config …` |
| one run's calls, in a spreadsheet | that run's `cost.csv` (by session and stage) and `calls.csv` (by call), in its folder |
| what each paid file in the cache is | `.cache/INDEX.csv` |
