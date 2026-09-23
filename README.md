# ▮ Token Tariff

Token Tariff is an LLM API cost calculator. You describe your workload once, and
it tells you what that workload would cost on every model and which model gives
you the most capability for the money.

**[Open the app → token-tariff.streamlit.app](https://token-tariff.streamlit.app/)**

It has three modes:

- **RECOMMEND** — "What should I use?" Pick a use case, adjust the workload, say
  whether you care most about quality, price or speed, and get one recommended
  model with a cheaper and a more capable alternative beside it.
- **MATCH** — "Can I get the same for less?" Name the model you use today and see
  which models score as well or better, cheapest first.
- **LOOK UP** — "What does this model cost?" Search the whole catalog, including
  models that have no benchmark score.

Every setting is saved in the URL, so any comparison can be shared as a link.
Prices and scores come from live sources and refresh every hour; nobody
maintains the model list by hand.

<table>
<tr>
<td width="50%" valign="top">
<b>① RECOMMEND</b><br/>
<sub>One recommended model with its reasons, the alternatives, a cost-ranked table, and a price-vs-score chart.</sub><br/>
<a href="screenshots/01-verdict.png"><img src="screenshots/01-verdict.png" alt="Recommendation, alternatives, ranked table, and price-vs-score chart"/></a>
</td>
<td width="50%" valign="top">
<b>② MATCH</b><br/>
<sub>Only models that score at least as well as the one you name, cheapest first. Here: claude-opus-4-8's score for 3.3× less.</sub><br/>
<a href="screenshots/02-anchor.png"><img src="screenshots/02-anchor.png" alt="Match mode: the cheapest model that scores as well as claude-opus-4-8"/></a>
</td>
</tr>
<tr>
<td width="50%" valign="top">
<b>③ Use-case presets</b><br/>
<sub>One click sets the workload, the score to rank by, and the priorities. Shown: the coding-agent preset, ranked on the coding score.</sub><br/>
<a href="screenshots/03-coding.png"><img src="screenshots/03-coding.png" alt="Coding-agent preset ranked on the coding score"/></a>
</td>
<td width="50%" valign="top">
<b>④ Full price sheet, in USD or INR</b><br/>
<sub>Click any row for its complete pricing: cache and batch rates, context window, capabilities, and real daily usage.</sub><br/>
<a href="screenshots/04-detail-inr.png"><img src="screenshots/04-detail-inr.png" alt="Full pricing for one model, shown in INR"/></a>
</td>
</tr>
</table>

## Features

- **Use-case presets.** Chatbot, coding agent, agent, summarize and extraction.
  Each one sets a typical workload size, which score to rank by (general
  intelligence, coding or agentic), a sensible range of model sizes, the
  capabilities you need, and your priorities. You can change anything
  afterwards; a "PRESET MODIFIED" label appears with a way back. A built-in
  guide explains every mode.
- **Optimize for.** Choose balanced, smartest, cheapest or fastest. Behind this
  are three weights (smart, cheap, fast) that you can also set by hand under
  ADVANCED. Each model gets a FIT score from 0 to 100, built from how it ranks
  on score, price and speed among the models on screen. Using ranks rather than
  raw numbers stops one extreme model from dominating.
- **A recommendation with two alternatives.** A cheaper option, which costs less
  and gives up at most 5 points of score, and a more capable option, which is at
  least 3 points better at the lowest extra cost. Each only appears if a model
  qualifies.
- **Price-vs-score chart.** Every model plotted by score against the cost of your
  workload, with a line connecting the best-value models. Anything below the
  line is beaten on both price and score by something on it.
- **Three score types.** General intelligence, coding and agentic. Specialized
  models rank very differently depending on which you pick.

## Where the data comes from

| Data | Source |
|---|---|
| Prices: per-token input and output, cache, batch, context window, capabilities, retirement dates | [LiteLLM's pricing catalog](https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json) |
| Scores: intelligence, coding and agentic | [Artificial Analysis](https://artificialanalysis.ai/), through [OpenRouter's model list](https://openrouter.ai/api/v1/models) (no key needed, about 90 models, and the only source of the agentic score) and the [Artificial Analysis API](https://artificialanalysis.ai/documentation) (free key, 500+ models) |
| Speed: output tokens per second and time to first token | Artificial Analysis API |
| Usage: tokens per day actually sent to each model, 7-day average | [OpenRouter's usage data](https://openrouter.ai/data) (needs a key). This is real traffic, not popularity on benchmarks. |

Each source is fetched at most once an hour and saved to a local file
(`model_prices_and_context_window.json`, `benchmark_scores.json`,
`aa_models.json`, `usage_rankings.json`). If a source is unavailable or you have
no key, the app uses the last saved copy.

The model list is built automatically:

- By default you see every model that has both a price and a score, about 110.
  LOOK UP adds about 120 more that have a price but no score.
- A model sold through several providers (its maker's own API, OpenRouter, Groq
  and so on) appears once. The maker's own price wins, or failing that the
  cheapest.
- Dated versions of a model are merged into the base model. Retired and free
  entries are dropped.
- Size tiers (FRONTIER, ADVANCED, CAPABLE, BUDGET) are the four quarters of the
  intelligence score across all scored models, so they move as new models
  arrive.
- Model names don't always match between sources. `score_overrides.json` and
  `aa_overrides.json` are small lookup tables that link them. A model that can't
  be matched shows blanks rather than a guess.

## How cost is calculated

Cost per model = (input tokens × input price + output tokens × output price) ×
number of calls, adjusted for three settings:

- **Cache hit rate.** The share of input served from a prompt cache is charged
  at that model's cache price. Models that don't publish a cache price get no
  discount, so at high hit rates, models with cheap caching pull well ahead.
- **Reasoning multiplier.** Reasoning models charge their thinking as output
  tokens. The multiplier increases output tokens for reasoning models only.
- **Batch pricing.** Where a model publishes batch prices (usually about half
  price), they replace the normal ones.

Some limits to keep in mind:

- Cache cost counts reads only. Writing to the cache is a one-time cost per
  prompt and is left out.
- Token counts come from OpenAI's tokenizer, so they are approximate for other
  vendors' models.
- The same task can use very different numbers of tokens on different models,
  especially reasoning models at high effort. A lower price per token can still
  mean a higher cost per finished task.
- Benchmark scores are a starting point, not a guarantee.

Use the ranking to build a shortlist, then test that shortlist on your own
prompts before switching.

## Run it locally

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # skip if you already have uv
uv run streamlit run app.py
```

The first run installs everything listed in `pyproject.toml` (versions pinned in
`uv.lock`). There is no `requirements.txt`.

### Optional API keys

Both keys are free, and the app calls each source at most once an hour. Put them
in `.streamlit/secrets.toml`, which git ignores, or set them as environment
variables:

```toml
# .streamlit/secrets.toml
AA_API_KEY = "your-key"          # https://artificialanalysis.ai/ (free, 1,000 requests a day)
OPENROUTER_API_KEY = "your-key"  # https://openrouter.ai/ (for usage data)
```

- `AA_API_KEY` keeps speed figures and the wider score coverage current.
- `OPENROUTER_API_KEY` keeps the daily usage figures current.

Without keys the app still works. It shows the last saved data and hides
anything it has no data for.

## URL parameters

Every setting is stored in the URL.

| Parameter | Meaning | Example |
|---|---|---|
| `mode` | RECOMMEND, MATCH or LOOK UP | `?mode=MATCH` |
| `preset` | Use-case preset (RECOMMEND) | `?preset=CODING+AGENT` |
| `q` | Model search (LOOK UP) | `?q=kimi` |
| `prov` | Provider filter (repeatable) | `?prov=Anthropic&prov=Google` |
| `tiers` | Size-tier filter (repeatable) | `?tiers=FRONTIER` |
| `input_tokens` | Input tokens per call | `?input_tokens=50000` |
| `output_tokens` | Output tokens per call | `?output_tokens=3000` |
| `api_calls` | Number of calls | `?api_calls=1000` |
| `cache` | Cache hit rate (%) | `?cache=80` |
| `rmult` | Reasoning multiplier | `?rmult=3.0` |
| `batch` | Use batch pricing | `?batch=true` |
| `opt` | Optimize for (any other weights show as CUSTOM) | `?opt=CHEAPEST` |
| `w_smart` / `w_cheap` / `w_fast` | Priority weights, 0–5 (what `opt` sets) | `?w_fast=5` |
| `anchor` | The model to match (MATCH) | `?anchor=claude-opus-4-8` |
| `tol` | How many points below it still counts as a match | `?tol=3` |
| `axis` | Which score to rank by | `?axis=CODE` |
| `caps` | Required capabilities (repeatable) | `?caps=VISION&caps=TOOLS` |
| `ccy` | Currency | `?ccy=INR` |

## The WAGER page

The app has a second page, WAGER: a bet I made with myself in August 2026.

**How it started.** I was talking with a friend about Claude Fable 5, the
strongest model at the time, and said something like: this is the worst it will
ever be. Every model from here on only gets better and cheaper. Around the same
time I compared o1, OpenAI's first reasoning model from late 2024, with GPT-5.6
Luna, OpenAI's cheapest model in mid-2026. Luna beat it on both price and
benchmark scores. So the obvious next question was: how long until Fable 5's
level shows up in the cheapest models too?

**The idea.** The page looks back at how this has played out before. Within
months of a top model's release, some vendor's cheapest model reaches the same
benchmark score for a small fraction of the price. Then it commits to a date for
the next time. There's no money and no one on the other side. To keep it fun
and honest, the repo emails me on three fixed dates so I have to check whether I
was right.

**The prediction.** By June 27, 2027, one of the cheapest models from Anthropic,
OpenAI or Google will score as well as Claude Fable 5 did at launch. Fable 5 was
the strongest model in June 2026. The cheap model must also cost no more than a
tenth of Fable 5's price.

### How it is judged

- **The score** is the [Artificial Analysis](https://artificialanalysis.ai/)
  intelligence index, a combined score across several benchmarks. Artificial
  Analysis sometimes changes how the index is calculated, which rescales every
  model. So the cheap model and Fable 5 are always compared using the same
  version of the index. When I made the prediction, Fable 5 scored 59.9. After a
  change in September 2026 (index version 4.3), it scores 49.6. The target is
  the same; only the scale changed.
- **The price** must be at most $2.00 per million tokens, a tenth of Fable 5's
  $20. Prices are compared as a 3:1 mix of input and output tokens, which is how
  this page turns two prices into one number. It must be the vendor's own
  published list price. A temporary promotion, or a reseller's cheaper price,
  doesn't count.
- **"Cheapest model"** means the model a vendor sells as the cheapest in its
  current lineup: Claude Haiku, OpenAI's mini, nano or Luna, and Gemini
  Flash-Lite. An older model that happens to cost less doesn't change which one
  that is. If a vendor renames the line, the new name takes its place.
- **Both conditions**, score and price, must be met by the same model at the
  same time, and it must be public by 23:59 UTC on June 27, 2027. Evidence
  (the score and the price page) can be saved up to 14 days after that.

If no model qualifies by the deadline, the prediction was wrong.

### When I expect it

I gave two estimates, each based on a different trend:

| Estimate | Date | Based on |
|---|---|---|
| Price trend | 2027-01-10 | [Epoch AI](https://epoch.ai/data-insights/llm-inference-price-trends) found that the price of a given level of AI capability falls about 50× a year (median). At that rate a tenfold drop takes about seven months from Fable 5's release. |
| Past catch-ups | 2027-03-08 | Looking back, cheap models took a median of 8.9 months to match each new top model. |
| Deadline | 2027-06-27 | The slowest price decline Epoch measured, 9× a year. If even that pace holds, the target should be reached by this date. |

These are rough estimates, not a precise forecast, and both rest on the same
underlying trend. So the fact that they land close together isn't extra
evidence. Missing January to March doesn't lose the bet; missing the deadline
does.

The table shows the dates as I first recorded them. After the September 2026
index change, the past-catch-up estimate moved to 2027-04-20, with a median of
10.4 months. The page shows the original and updated dates side by side instead
of quietly replacing them.

### Where it stands (checked 2026-09-23)

- **Price: met.** GPT-6 Luna costs $0.20 per million tokens, well under the
  $2.00 limit.
- **Score: not yet.** The best cheap model scores 37.3 against Fable 5's 49.6,
  12.3 points short.

The page itself always shows the latest figures.

### What it doesn't show

- **A matching score doesn't mean an equal model.** The index is a set of
  exam-style tests. It doesn't measure long-document handling or how reliably a
  model completes long tasks on its own.
- **Price per token isn't cost per task.** A wordy cheap model can use far more
  tokens than an expensive one, and end up costing more per finished job.
- **Both halves at once is the hard part.** Of the 9 past catch-ups with known
  prices, 3 matched the score but were less than 10× cheaper than the model they
  matched (2 on the current index), so they would have failed this bet's price
  condition.
- **The sample is small.** Those past catch-ups come from only 5 cheap model
  releases (6 on the current index), because one release often matches several
  top models at once.
- **METR, a second check, can't be used yet.** [METR](https://metr.org/time-horizons/)
  measures how long a task a model can complete on its own. It hasn't tested
  Fable 5 or any cheap model, so it's tracked on the page but doesn't decide
  anything. Its results also depend heavily on the success rate used: an early
  Fable-family model manages 1,044.8-minute tasks half the time, but only
  185.9-minute tasks 80% of the time.
- **Open-weight models are tracked, but don't count.** The page also follows
  the strongest downloadable models, the pattern DeepSeek R1 started. They show
  another way top-level capability spreads. They can't settle the bet, because
  they have no single official price and often come from labs outside the three
  vendors.

### Data and upkeep

Unlike the calculator, this page runs on a hand-curated file, `timeline.csv`.
It has one row per model, and every row links to its source. Anything that
couldn't be verified is left blank rather than estimated. `wager.py` calculates
everything else from that file: which top models set new records, how long cheap
models took to catch up, both estimates, and whether the prediction has come
true.

| Data | Source |
|---|---|
| Intelligence scores | [Artificial Analysis](https://artificialanalysis.ai/) API. Every row is read from the same download, saved in `data/history/`. Where a model has several settings (for example, reasoning on or off), the highest-scoring one is used, for every model. |
| Task-length measurements | [METR](https://metr.org/time-horizons/)'s published results file (`benchmark_results_1_1.yaml`) |
| Price-decline rate | [Epoch AI](https://epoch.ai/data-insights/llm-inference-price-trends): 9× to 900× a year, median 50× |
| Prices and release dates | Vendor announcements and pricing pages, archived where the vendor blocks automated access |

`data/history/<date>/` keeps each raw download and is never edited afterwards.
That matters because Artificial Analysis rescores old models when it changes its
index, and its data carries no version number.

To refresh the data, about once a quarter:

```bash
uv run python scripts/timeline_fetch.py   # download fresh data and list what changed
```

Then run the `/timeline-refresh` Claude Code skill. It turns that list into
proposed `timeline.csv` changes, each with a source, and recalculates the
estimates.

`wager.json` holds the prediction exactly as I made it. It is deliberately not
updated when the data changes. The page flags any difference between the
original and the latest numbers instead. The current version is 2. On
2026-08-03 I clarified the wording: I added the deadline, made METR a secondary
check, defined "cheapest model" by product line rather than price, and stated
the price limit as a dollar figure. What has to happen didn't change. The
original wording is in git history.

### The scheduled emails

A GitHub Actions workflow (`.github/workflows/wager-email.yml`) sends three
emails through [Resend](https://resend.com/):

- **2026-10-21**, a halfway check-in
- **2027-01-10**, the letter, on the earlier estimated date
- **2027-06-28**, the morning after the deadline, to record the result

The workflow runs on the 10th, 21st and 28th of every month, matching those
dates, and does nothing until one is due. After sending, it opens a GitHub issue
as a record, which also stops the same email from going out twice.

**GitHub turns off scheduled workflows after 60 days with no repository
activity.** The quarterly data refresh commit keeps it running. If the repo goes
quiet for two months, turn the workflow back on from the Actions tab.

```bash
uv run python scripts/wager_check.py --dry-run --as-of 2027-01-10   # preview an email
uv run pytest -q                                                    # run the tests
```

**Privacy and secrets.** The recipient address and the Resend key are stored only
as GitHub Actions secrets (`WAGER_EMAIL_TO`, `RESEND_API_KEY`) and never appear in
the repo. With Resend's default test sender, emails can only go to the Resend
account's own address; to send elsewhere, verify a domain and set a `RESEND_FROM`
secret. The email text is impersonal, and the GitHub issues contain only status,
not the address or the letter. Because the refresh saves raw downloads into a
public repo, a `gitleaks` workflow scans every push for secrets, and the refresh
skill checks the changes again before each commit.

## Design

Dark gray background, blue only where it carries meaning, JetBrains Mono
throughout, square corners. The whole look (colors, font, table styling and chart
palette) is set in `.streamlit/config.toml`, with no custom CSS.

## Credits

Intelligence, coding and agentic scores are from [Artificial
Analysis](https://artificialanalysis.ai/), through OpenRouter's model list and
the Artificial Analysis API. Speed figures are from the Artificial Analysis API.
Usage figures are from OpenRouter. Prices are from LiteLLM's community-maintained
catalog. Exchange rates are from exchangerate-api.com.

## The original version

<details>
<summary>Screenshots of the first version, a plain cost calculator, before it became Token Tariff.</summary>

[LLM API Cost Calculator demo.webm](https://github.com/user-attachments/assets/b7bd21b6-ade2-4d56-b008-203e0724a464)

![image](https://github.com/user-attachments/assets/7921cef2-507e-4521-8647-8ad7b76cd141)

![image](https://github.com/user-attachments/assets/1ebec78f-61ce-4250-865a-00ed96a73b2c)

![image](https://github.com/user-attachments/assets/ae342797-8d7b-48af-bf8f-91568afc3b9d)

</details>
