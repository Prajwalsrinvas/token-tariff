---
name: timeline-refresh
description: Refresh the trickle-down wager's data spine — pull new snapshots of OpenRouter, METR and Artificial Analysis, find binding-tier models, non-binding open-weights high-water marks and price events the timeline is missing, propose sourced timeline.csv edits, and recompute both wager predictions. Use when asked to refresh, update, or re-check the WAGER page, timeline.csv, or the wager predictions, and roughly quarterly.
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

Set `AA_API_KEY` first — it lives in `.streamlit/secrets.toml` (gitignored),
which the script does not read on its own. Pass it without printing it:

```bash
AA_API_KEY="$(python3 -c "import tomllib;print(tomllib.load(open('.streamlit/secrets.toml','rb'))['AA_API_KEY'])")" \
  uv run python scripts/timeline_fetch.py
```

Without it the Artificial Analysis API is skipped, and the OpenRouter listing
alone cannot re-read the column: it carries no score for the older and delisted
models (GPT-4, o1, o3, Opus 4.x, the 3.x family) the milestones rest on. The
raw API payload also names each configuration and checkpoint, which is how
step 3's configuration rule gets applied. Do not source `aa_intel` from the
OpenRouter route: its `cohere/command-a` score turned out to be Command A+'s.

### 2. Search for what the feeds do not carry

The feeds show prices and scores. They do not show announcements. Search the
web for, since the previous snapshot's date:

- **New entry-level models.** The slot a major vendor designates as its cheapest
  in its current lineup — Claude Haiku, OpenAI's mini / nano / Luna slot, Gemini
  Flash-Lite. A vendor renaming the slot counts, and the new name inherits it; a
  vendor adding a tier below the old slot counts, and the old slot stops being
  the entry level. An older, cheaper model still on sale does not take the slot.
- **New frontier models**, and whether each set a new high on the AA index.
- **New open-weights flagship high-water marks.** This is a non-binding channel
  of downloadable flagship weights approaching closed frontier models — the
  DeepSeek-R1-versus-o1 pattern — not a vendor's budget models. Add a candidate
  only if it beats every earlier `open` row on the AA index and its exact score
  exists in one of this repo's committed AA feeds. A hosted route does not give
  open weights a canonical price: all four price cells stay blank. These rows
  settle nothing.
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
  snapshot's own Fable 5 figure rather than 59.9. Re-read **every** row from the
  new payload — never patch the rows that happen to be covered — and re-check
  the open channel's high-water sequence, since the rescale is not uniform and
  earlier marks can stop being marks. v4.2/v4.3 (2026-09-04/07) was the first
  such change: Fable 5 went 59.9 → 49.6.

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

- `tier` — `frontier`, `bottom`, or `open`. The slot, not the price. A cheap
  frontier model is still frontier. `bottom` is the entry-level slot: the value
  is data and stays, but nothing a reader sees says "lineup bottom". `open` is
  the non-binding open-weights flagship high-water channel, never an open
  vendor's cheapest tier.
- `metr_key` — the model's key in METR's YAML, or blank. The p50 and p80 cells
  must match that key exactly; `timeline_fetch.py` checks both.
- `metr_source` — always the v1.1 URL. Never mix suite versions in one column:
  the same model scores differently under v1.0.
- `aa_version` — the `data/history/` snapshot the AA figure was read from, the
  only version key either feed offers. It is the same on every row:
  `test_every_index_is_read_from_one_snapshot` fails otherwise, because
  milestones compare scores across rows.
- `notes` — anything a reader would otherwise get wrong.

For every `open` row, verify the release date and use the vendor's announcement
or official model card as `source_url`. Keep launch and current price columns
blank and say in `notes` that the row is a non-binding open-weights high-water
mark with no canonical price.

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

`open` rows must be inert here. `milestones()` and `method_a()` select only
`frontier` and `bottom`; `resolution()` selects only eligible `bottom` rows; and
the price-decline dates depend only on the frozen constants and baseline. If an
open row moves any prediction, milestone, resolution field or frozen date, stop
and fix the filtering before accepting the refresh.

`tests/test_wager.py` pins the live recomputation separately from the frozen
document: `LIVE_*`, `EXPECTED_OPEN` and the live-status test move on every
refresh that changes a milestone, deliberately, while `FROZEN_*` and the
timeline-independent dates (Method B, slowest trend, deadline, sends) never do.
Running the tests boots the rate card, which rewrites the app's root caches
(`aa_models.json`, `benchmark_scores.json`, `model_prices_and_context_window.json`)
— restore them with `git checkout --` unless refreshing the app's fallback is
part of the change.

If it is re-frozen, three more things must move with it: the `FROZEN_*` pins;
the `cron` in `.github/workflows/wager-email.yml`, whose day-of-month values are
the day numbers of the new due dates; and the README table. `uv run pytest -q`
fails until they agree.

The page's prose recomputes from `timeline.csv` — the contender, the gap and the
price ceiling are f-strings over the derivation, not sentences to hand-edit. The three HOW IT WENT acts are the exception to watch: their headlines name
specific catch-ups ("Haiku takes o1"), so when a refresh reassigns a milestone,
read the acts on the rendered page and make any claim that no longer holds
conditional on the data, as Act 1 does for GPT-4o mini.

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
