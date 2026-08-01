# Provenance — 2026-08-01

Raw sources for `timeline.csv`, fetched by `scripts/timeline_fetch.py` on
2026-08-01. Append-only: never edit a snapshot after the fact — a corrected figure
belongs in the next one, so that a source silently changing its own history
stays visible.

| File | Source | Fetched |
|---|---|---|
| `openrouter_models.json` | https://openrouter.ai/api/v1/models | 2026-08-01 |
| `metr_benchmark_results_1_1.yaml` | https://metr.org/assets/benchmark_results_1_1.yaml | 2026-08-01 |
| `metr_benchmark_results_1_0.yaml` | https://metr.org/assets/benchmark_results_1_0.yaml | 2026-08-01 |
| `metr_release_dates.yaml` | https://raw.githubusercontent.com/METR/eval-analysis-public/main/data/external/release_dates.yaml | 2026-08-01 |

`aa_models.json` is present only when the fetch ran with `AA_API_KEY` set.

Artificial Analysis publishes no index-version field in either the OpenRouter
listing or its own API, and re-scores older models when the index changes. The
date a figure was read is therefore its version key.

METR figures come from METR-Horizon-v1.1 unless a row says otherwise; the same
model scores differently under v1.0, so the two suites must not be mixed.

## The two AA feeds are not the same vintage

`aa_models.json` in this snapshot was **not** fetched on 2026-08-01. It was
copied from the repository root, where it is the app's own committed Artificial
Analysis API payload, last written 2026-07-05. It carries no GPT-5.6 models and
no Opus 5 — both of which shipped after it — so its true vintage is no later
than **2026-07-05**, and the 16 `timeline.csv` rows whose `aa_source` is the AA
API record that date in `aa_version` rather than the snapshot date.

Those 16 rows are the models OpenRouter has retired from its listing, which the
OpenRouter pull therefore cannot score — the older half of the timeline. The
comparison the wager actually turns on, Fable 5 at 59.9 against GPT-5.6 Luna at
51.2, is entirely inside the fresh 2026-08-01 OpenRouter feed.

The two feeds are not interchangeable. Across the 60 models both carry an index
for, **16 disagree** — sometimes by a lot: `kimi-k2-thinking` at 17.3 on
OpenRouter against 32.7 in the AA payload, `claude-sonnet-4-6` at 47.2 against
35.9, `command-a` at 22.5 against 7.7. Most of these gaps are the two feeds
reporting different configurations of one model rather than a different index
generation, but nothing in either payload says which configuration a number
refers to, so the disagreement cannot be resolved from the data alone.

For the **8 models both feeds carry that `timeline.csv` tracks** — GPT-5, Claude
Haiku 4.5, GPT-5.4, GPT-5.4 nano, Claude Opus 4.7, GPT-5.5, Claude Opus 4.8 and
Claude Fable 5 — the two agree to the decimal, once each model is read at its
highest-scoring published configuration, which is the rule `timeline.csv`
applies everywhere. That is why a row may be drawn from either feed. It is a
statement about those 8 rows only, not evidence that the two feeds are one index
version.
