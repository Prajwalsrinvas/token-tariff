# Provenance — 2026-09-23

Raw sources for `timeline.csv`, fetched by `scripts/timeline_fetch.py` on
2026-09-23. Append-only: never edit a snapshot after the fact — a corrected figure
belongs in the next one, so that a source silently changing its own history
stays visible.

| File | Source | Fetched |
|---|---|---|
| `openrouter_models.json` | https://openrouter.ai/api/v1/models | 2026-09-23 |
| `metr_benchmark_results_1_1.yaml` | https://metr.org/assets/benchmark_results_1_1.yaml | 2026-09-23 |
| `metr_benchmark_results_1_0.yaml` | https://metr.org/assets/benchmark_results_1_0.yaml | 2026-09-23 |
| `metr_release_dates.yaml` | https://raw.githubusercontent.com/METR/eval-analysis-public/main/data/external/release_dates.yaml | 2026-09-23 |
| `aa_models.json` | https://artificialanalysis.ai/api/v2/data/llms/models | 2026-09-23 |

`aa_models.json` is present only when the fetch ran with `AA_API_KEY` set.

Artificial Analysis publishes no index-version field in either the OpenRouter
listing or its own API, and re-scores older models when the index changes. The
snapshot date is therefore the version key for every AA figure drawn from it.

METR figures come from METR-Horizon-v1.1 unless a row says otherwise; the same
model scores differently under v1.0, so the two suites must not be mixed.
