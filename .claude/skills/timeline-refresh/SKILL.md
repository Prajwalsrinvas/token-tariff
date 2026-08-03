---
name: timeline-refresh
description: Refresh the trickle-down wager's data spine — pull new snapshots of OpenRouter, METR and Artificial Analysis, find models and price events the timeline is missing, propose sourced timeline.csv edits, and recompute both wager predictions. Use when asked to refresh, update, or re-check the WAGER page, timeline.csv, or the wager predictions, and roughly quarterly.
---

# Refreshing the trickle-down wager

`timeline.csv` is the only hand-curated file in this repo. Everything else on the
WAGER page is computed from it. This skill adds rows and corrects cells — each
one carrying a source URL — without ever inventing a number.

The whole job is judgement about which facts are real. The fetching is already
automated; do not re-derive it by hand.

## The rule that outranks the others

**A cell with no source URL stays blank.** A blank is a true statement about
what could be verified. An estimate that looks like a measurement is not, and it
will be read as one by everything downstream — the lag table, both prediction
methods, and the letter that gets emailed on the resolution date.

If a fact seems obviously true but no page states it, it is still blank.

## Steps

### 1. Snapshot and diff

```bash
uv run python scripts/timeline_fetch.py
```

This writes `data/history/<today>/` and prints new models, delisted models,
price changes, AA index changes, new METR measurements, and any `timeline.csv`
cell that disagrees with the fresh snapshot. Read that output before anything
else — it is the agenda.

Set `AA_API_KEY` first if you have it; without it the Artificial Analysis API is
skipped and only the models OpenRouter routes carry AA scores.

### 2. Search for what the feeds do not carry

The feeds show prices and scores. They do not show announcements. Search the
web for, since the previous snapshot's date:

- **New entry-level models.** The slot a major vendor designates as its cheapest
  in its current lineup — Claude Haiku, OpenAI's mini / nano / Luna slot, Gemini
  Flash-Lite. A vendor renaming the slot counts, and the new name inherits it; a
  vendor adding a tier below the old slot counts, and the old slot stops being
  the entry level. An older, cheaper model still on sale does not take the slot.
- **New frontier models**, and whether each set a new high on the AA index.
- **Price events** — cuts, rises, promotional rates ending, intro pricing
  expiring.
- **METR publications.** A new blog post, a new suite version, or new models in
  `benchmark_results_1_1.yaml`. Watch specifically for METR measuring any
  entry-level model, which would make the wager's secondary check readable for
  the first time. It is non-binding: the index arm is what resolves the wager.
- **Artificial Analysis index version changes.** AA re-scores older models when
  the index changes and tags no version in either feed. If the whole column has
  shifted, say so loudly — every lag pair and the wager's 59.9 threshold are
  read on one snapshot, and a version change means comparing against the
  snapshot's own Fable 5 figure rather than 59.9.

### 3. Distinguish the official price from the route price

OpenRouter lists what a route charges, which is not always what the vendor
charges. At the last freeze, `openai/gpt-5.6-luna` showed $0.10/$0.60 against an
official $0.20/$1.20, and `openai/gpt-5.6-terra` $1/$6 against an official
$2/$12 — exactly half in both cases, with no stated cause. Budgeting on the
route price would have been wrong by 2×. Record what the vendor publishes and
note the route price; do not invent a reason for the gap.

`current_price_in` / `current_price_out` record the **vendor's published
price**. Note a materially different route price in `notes`. `timeline_fetch.py`
flags the disagreement; deciding which is canonical is this step's job.

Watch the same way for introductory pricing with an end date.

Where a model publishes several configurations — thinking and non-thinking,
reasoning and not, adaptive, low/medium/high effort — `timeline.csv` records the
**highest-scoring published configuration**, for every row without exception,
and names the configuration in `notes`. This is not a per-row judgement call:
which releases count as milestones depends on it, so a row read at its base
configuration while its neighbour is read at its thinking configuration
manufactures and erases milestones. Where a model has dated checkpoints, use the
checkpoint matching the row's `release_date` rather than the rolling alias,
which reflects later checkpoints.

### 4. Propose edits

Present every proposed addition and correction as a table before writing
anything: model, the cells changing, old value, new value, source URL. Then
apply the accepted ones to `timeline.csv`.

Column notes:

- `tier` — `frontier` or `bottom`. The slot, not the price. A cheap frontier
  model is still frontier. `bottom` is the entry-level slot: the value is data
  and stays, but nothing a reader sees says "lineup bottom".
- `metr_key` — the model's key in METR's YAML, or blank. The p50 and p80 cells
  must match that key exactly; `timeline_fetch.py` checks both.
- `metr_source` — always the v1.1 URL. Never mix suite versions in one column:
  the same model scores differently under v1.0.
- `aa_version` — the date the AA figure was read, which is the only version key
  either feed offers. It is **not** automatically the snapshot date: the
  committed `aa_models.json` is older than the OpenRouter pull, and rows sourced
  from it carry its vintage (`≤2026-07-05` at the last freeze). If a refresh
  fetches the AA API with a key, the rows it sources move to that date.
- `notes` — anything a reader would otherwise get wrong.

### 5. Recompute and reconcile

```bash
uv run python -c "import wager; p = wager.predictions(wager.load_timeline()); \
print(p['a']['date'], p['b']['date'], p['a']['median_lag_months'])"
```

The page recomputes live from `timeline.csv`, so it moves on its own.
`wager.json` is the **frozen** prediction the emails were built around and
should not be edited to match — the page already shows a badge when live data
has moved away from it, and that divergence is information. Only rewrite
`wager.json` if the wager itself is being restated, and say so in the commit.

If it is re-frozen, three things must move with it: `tests/test_wager.py`, which
pins every number; the `cron` in `.github/workflows/wager-email.yml`, whose
day-of-month values are the day numbers of the new due dates; and the README
table. `uv run pytest -q` fails until they agree.

The page's prose recomputes from `timeline.csv` — the contender, the gap and the
price ceiling are f-strings over the derivation, not sentences to hand-edit.

If an entry-level model has reached the baseline's index at or under a tenth of
its cost, the wager has resolved early. Say so plainly and check it is not an
artefact of an AA index version change before treating it as real.

### 6. Scan the diff before committing — mandatory

```bash
git add -A
git diff --cached | grep -nEi '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|(sk|rk|re)_[A-Za-z0-9]{16,}|AIza[0-9A-Za-z_-]{20,}|ghp_[A-Za-z0-9]{20,}|bearer [A-Za-z0-9._-]{20,}|api[_-]?key'
```

This repo is public and this step pulls raw API payloads into it. Snapshots are
committed verbatim, so anything a feed happens to include gets published.

Expect zero matches. Investigate every hit before committing — including ones
that look like documentation, because `api_key` in an example is how a real one
gets pasted next to it. The `gitleaks` workflow runs on push as the backstop,
not the first line.

Never commit `.streamlit/secrets.toml` (already gitignored), a recipient
address, or anything resembling a credential. `WAGER_EMAIL_TO` and
`RESEND_API_KEY` live only as Actions secrets.

### 7. Commit

One commit, present tense, describing what changed in the data:

```
refresh timeline: add gemini-4-flash-lite, correct luna route price
```

**The commit matters beyond its contents.** GitHub disables scheduled workflows
after 60 days without repository activity, and the wager email is a scheduled
workflow. This quarterly refresh is what keeps it alive. If the repo has been
quiet for two months, check the Actions tab for a disabled-workflow notice
before assuming the email will fire.
