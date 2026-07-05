# ▮ Token Tariff

**A live LLM API cost calculator and model-picker.** Describe your workload once and Token Tariff answers two questions at a glance: **what does it cost on every model**, and **which model is the smartest buy for that money?**

**▸ [Live app — token-tariff.streamlit.app](https://token-tariff.streamlit.app/)**

Pick a use-case preset (chatbot, coding agent, summarization, …) or dial in your own workload — tokens per call, number of calls, cache-hit rate, reasoning overhead, batch pricing. A **verdict** at the top names one model and why; below it, a ranked ledger with scores, speed, and real usage, an efficient-frontier chart, and quick cuts (cheapest / best value / smartest / fastest). Every control lives in the URL, so any comparison is a shareable link. Prices and scores refresh hourly from live feeds — nothing is hand-maintained.

<table>
<tr>
<td width="50%" valign="top">
<b>① Verdict-led picking</b><br/>
<sub>One recommended model with its reasons, four single-metric cuts, a cost-ranked ledger, and the efficient frontier.</sub><br/>
<a href="screenshots/01-verdict.png"><img src="screenshots/01-verdict.png" alt="Verdict, quick cuts, ranked ledger, and efficient-frontier chart"/></a>
</td>
<td width="50%" valign="top">
<b>② Anchor — same smarts, less money</b><br/>
<sub>Pick a reference model; the view keeps only models that match or beat it and names the cheapest. Here: claude-opus-4-8's intelligence for 2.5× less.</sub><br/>
<a href="screenshots/02-anchor.png"><img src="screenshots/02-anchor.png" alt="Anchor mode: cheapest model matching claude-opus-4-8 within tolerance"/></a>
</td>
</tr>
<tr>
<td width="50%" valign="top">
<b>③ Use-case presets</b><br/>
<sub>One click reshapes the whole comparison — workload, score axis, tiers, and priorities. Shown: the coding-agent preset on the coding index.</sub><br/>
<a href="screenshots/03-coding.png"><img src="screenshots/03-coding.png" alt="Coding-agent preset with the coding-index frontier"/></a>
</td>
<td width="50%" valign="top">
<b>④ Full rate card, any currency</b><br/>
<sub>Select any row for its complete rate card — cache/batch prices, context, capabilities, real tokens/day. USD or INR throughout.</sub><br/>
<a href="screenshots/04-detail-inr.png"><img src="screenshots/04-detail-inr.png" alt="Per-model rate card detail with INR pricing"/></a>
</td>
</tr>
</table>

## How it helps you decide

- **Use-case presets** — CHATBOT / CODING AGENT / AGENT / SUMMARIZE / EXTRACTION each set a typical workload shape, the matching score axis (intelligence, coding, or agentic), a sensible tier range, the tools filter, and the priority weights in one click — with a plain-language note on what they model. Everything stays editable, and an in-app **GUIDE** walks through every control.
- **Priorities → verdict** — SMART / CHEAP / FAST sliders produce a **FIT** score (0–100) per model, and the verdict names the best fit and its reasons. FIT is a weighted blend of *percentile ranks* within the current view — score rank, cheapness rank, speed rank — so one extreme outlier can't dominate.
- **Anchor query** — pick a reference model and the field narrows to models that match or beat its score (within your tolerance), ranked by workload cost: *"who matches this model's intelligence for less?"*
- **Efficient frontier** — score vs. workload cost on a log axis with the Pareto frontier drawn; everything below the line is beaten on both price and score.
- **Search** — look up any model by name, maker, or LiteLLM key across the full catalog, bypassing the filters.
- **Axis toggle** — general intelligence, coding, or agentic index; specialized models rank very differently.

## Where the data comes from

Everything is derived at runtime from live feeds, so new models appear automatically once the feeds list them — there is no hand-maintained model list.

| Data | Source |
|---|---|
| **Prices** — per-token in/out, cache, batch, context windows, capability flags, deprecation dates | [LiteLLM pricing catalog](https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json) |
| **Scores** — intelligence, coding, and agentic indices | [Artificial Analysis](https://artificialanalysis.ai/), via [OpenRouter's model listing](https://openrouter.ai/api/v1/models) (keyless, ~90 models, only source of the agentic index) plus the [AA API](https://artificialanalysis.ai/documentation) (free key, 500+ models) filling the gaps |
| **Speed** — median output tokens/sec and time-to-first-token | Artificial Analysis API |
| **Usage** — tokens/day actually routed per model, 7-day average | [OpenRouter rankings dataset](https://openrouter.ai/data) (needs an OpenRouter key) — real production traffic, not benchmark popularity |

Every fetch is cached for an hour and written to a local JSON snapshot (`model_prices_and_context_window.json`, `benchmark_scores.json`, `aa_models.json`, `usage_rankings.json`) that serves as an offline fallback — so keyless runs still render the last snapshotted scores, speed, and usage. The only stored mappings are `score_overrides.json` and `aa_overrides.json` — small crosswalks for models whose names diverge between feeds; an unmatched model simply shows blanks.

**The catalog is computed, not curated:**

- **Default view** — every model with both a price and a score (~110 across all major makers).
- **ALL MODELS** — adds the unscored remainder of the pricing catalog (~250 more).
- Duplicate routes (direct API vs. OpenRouter vs. Groq) and spelling/word-order aliases collapse to one row per model — the maker's own API wins, else the cheapest route.
- Dated snapshots collapse onto their base model; deprecated and zero-priced entries are dropped.
- **Tiers** (FRONTIER / ADVANCED / CAPABLE / BUDGET) are live quartiles of the intelligence index across scored models, so they track the field as it moves.

## The cost model

Total cost per model = (input tokens × effective input price + output tokens × effective output price) × calls, where:

- **Prompt-cache hit rate** — the cached share of input tokens is billed at each model's cache-read rate. Models with no published cache pricing get no discount — which is the point: at an 80% hit rate, models with cheap cache reads pull far ahead.
- **Reasoning multiplier** — reasoning models bill thinking tokens as output; the multiplier applies to reasoning-capable models only.
- **Batch API** — published batch prices replace live prices where available (typically ~50% off).

Assumptions: cache math counts reads only (write premiums are a one-time cost per prompt prefix); tokenizers differ across providers, so `tiktoken` estimates are approximate for non-OpenAI models. **Benchmark scores are a screen, not a guarantee** — always evaluate a shortlist on your own prompts before switching models.

## Run it locally

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv --python 3.11
source .venv/bin/activate
uv pip install -r requirements.txt
streamlit run app.py
```

### Optional API keys

Both keys are free-tier, and the app makes at most one request per hour per feed. Set them in `.streamlit/secrets.toml` (gitignored) or as environment variables:

```toml
# .streamlit/secrets.toml
AA_API_KEY = "your-key"          # https://artificialanalysis.ai/ — free, 1,000 req/day
OPENROUTER_API_KEY = "your-key"  # https://openrouter.ai/ — datasets API
```

- `AA_API_KEY` keeps speed (TOK/S, FASTEST cut, TTFT, the FAST priority) and the expanded score coverage live.
- `OPENROUTER_API_KEY` keeps usage (USE B/D, tokens/day on the rate card) live.

Without a key, each feed serves its committed snapshot — everything still renders, it just ages until the next keyed refresh; elements with no data hide gracefully.

## URL parameters

Every control is bound to the URL, so any view is a shareable link.

| Parameter | Meaning | Example |
|---|---|---|
| `preset` | Use-case preset | `?preset=CODING+AGENT` |
| `q` | Model search (bypasses filters) | `?q=kimi` |
| `prov` | Provider filter (repeatable) | `?prov=Anthropic&prov=Google` |
| `tiers` | Tier filter (repeatable) | `?tiers=FRONTIER` |
| `input_tokens` | Input tokens per call | `?input_tokens=50000` |
| `output_tokens` | Output tokens per call | `?output_tokens=3000` |
| `api_calls` | Number of calls | `?api_calls=1000` |
| `cache` | Prompt-cache hit rate (%) | `?cache=80` |
| `rmult` | Reasoning output multiplier | `?rmult=3.0` |
| `batch` | Batch API pricing | `?batch=true` |
| `w_smart` / `w_cheap` / `w_fast` | Priority weights (0–5) | `?w_fast=5` |
| `anchor` | Anchor model (its catalog name) | `?anchor=claude-opus-4-8` |
| `tol` | Anchor tolerance (points) | `?tol=3` |
| `axis` | Score axis | `?axis=CODE` |
| `all` | Include unscored models | `?all=true` |
| `ccy` | Display currency | `?ccy=INR` |
| `need_r` / `need_v` / `need_t` | Require reasoning / vision / tools | `?need_v=true` |

## Design

The interface is a dark graphite ledger — neutral dark gray, blue used only where it means something, JetBrains Mono throughout, square corners. The entire look lives in `.streamlit/config.toml`: theme colors, webfont, dataframe styling, and the categorical palette that colors the charts. There is no custom CSS.

## Attribution

Intelligence, coding, and agentic scores are [Artificial Analysis](https://artificialanalysis.ai/) indices, served via OpenRouter's model API and the Artificial Analysis API; speed metrics come from the Artificial Analysis API; usage data from OpenRouter's rankings dataset. Prices are from LiteLLM's community-maintained catalog. Exchange rate from exchangerate-api.com.

## The original version

<details>
<summary>Screenshots of this app's first incarnation — a plain cost calculator, before the rate-card redesign that became Token Tariff.</summary>

[LLM API Cost Calculator demo.webm](https://github.com/user-attachments/assets/b7bd21b6-ade2-4d56-b008-203e0724a464)

![image](https://github.com/user-attachments/assets/7921cef2-507e-4521-8647-8ad7b76cd141)

![image](https://github.com/user-attachments/assets/1ebec78f-61ce-4250-865a-00ed96a73b2c)

![image](https://github.com/user-attachments/assets/ae342797-8d7b-48af-bf8f-91568afc3b9d)

</details>
