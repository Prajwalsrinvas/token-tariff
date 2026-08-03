"""
TOKEN TARIFF · RATE CARD — a live LLM API cost calculator and model-comparison
tool. Run through app.py, which registers it as the default page.
Author: Prajwal Srinivas
Description: Compare what a workload actually costs across LLM APIs — and which
             model is the smartest buy. Prices come live from LiteLLM's pricing
             catalog; intelligence, coding, and agentic scores are Artificial
             Analysis indices, from OpenRouter's public model listing plus the
             AA API itself (which scores far more models) when a key is set;
             speed comes from the AA API; real usage (tokens/day routed) from
             OpenRouter's rankings dataset when a key is set. One mode per
             visitor intent: RECOMMEND names a model for a use case, MATCH
             finds cheaper equals of a model you already run, LOOK UP searches
             the whole catalog. Every control is URL-bound, so any comparison
             is a shareable link.
"""

# =============================================================================
# Section 1: Imports and configuration
# =============================================================================
import datetime as dt
import json
import math
import os
import re
from typing import Dict, Optional, Tuple

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

st.set_page_config(page_title="TOKEN TARIFF", page_icon="▮", layout="wide")

PRICES_URL = "https://raw.githubusercontent.com/BerriAI/litellm/refs/heads/main/model_prices_and_context_window.json"
PRICES_FILE = "model_prices_and_context_window.json"
SCORES_URL = "https://openrouter.ai/api/v1/models"
SCORES_FILE = "benchmark_scores.json"
AA_URL = "https://artificialanalysis.ai/api/v2/data/llms/models"
AA_FILE = "aa_models.json"
USAGE_URL = "https://openrouter.ai/api/v1/datasets/rankings-daily"
USAGE_FILE = "usage_rankings.json"
EXCHANGE_RATE_URL = "https://api.exchangerate-api.com/v4/latest/USD"
FALLBACK_FX = 88.0
CACHE_TTL = 60 * 60  # seconds

DEFAULT_MAKERS = ["Anthropic", "Google", "OpenAI"]

# One mode per visitor intent. A control belongs to exactly one of them: the
# presets and priorities to RECOMMEND, the anchor to MATCH, the search box to
# LOOK UP — so no mode ever asks a question its answer does not use.
MODES = ["RECOMMEND", "MATCH", "LOOK UP"]

# OPTIMIZE FOR stands in for the three priority weights: one decision instead
# of three sliders. The sliders survive under ADVANCED, and any weights that
# spell none of these four read as CUSTOM.
OPTIMIZE_FOR = {
    "BALANCED": (3, 3, 1),
    "SMARTEST": (5, 2, 1),
    "CHEAPEST": (2, 5, 1),
    "FASTEST": (2, 2, 5),
}
CUSTOM = "CUSTOM"
WEIGHT_KEYS = ("w_smart", "w_cheap", "w_fast")

# Capability requirements, keyed by the label a visitor picks from.
CAPABILITIES = {"REASONING": "reasoning", "VISION": "vision", "TOOLS": "tools"}

# How far an alternative may sit from the recommendation and still be worth
# naming: a cheaper option may give up 5 index points, a more capable one has
# to gain 3. Both are index points, so they read the same on any axis.
CHEAPER_DROP = 5
CAPABLE_GAIN = 3

# Score, performance, and usage lookups are by normalized model name. A few
# litellm keys need an explicit OpenRouter id (scores) or Artificial Analysis
# slug (speed/scores) because their names diverge — Groq's route-specific
# Llama names, AA's "claude-4-5-haiku" word order. Kept in JSON files;
# unmatched models simply show blanks, so a stale entry can never break the
# app.
OVERRIDES_FILE = "score_overrides.json"
AA_OVERRIDES_FILE = "aa_overrides.json"

# Tier bands are quartiles of the intelligence index across currently scored
# models, so they track the field as it moves — no fixed thresholds to go stale.
TIER_LABELS = ["FRONTIER", "ADVANCED", "CAPABLE", "BUDGET"]

# Which Artificial Analysis index each axis reads.
AXES = {"INT": "intelligence", "CODE": "coding", "AGENT": "agentic"}

# Use-case presets: a plain-language description plus the workload shape,
# score axis, tier range, capability filter, and priority weights it
# configures in one click. Product config (typical traffic shapes and what
# buyers of that use case care about), not model data — every value stays
# editable after. Tier floors keep quality-sensitive use cases from being
# won on price by bottom-quartile models: rank-based FIT compresses score
# gaps, so without a floor the cheapest model in view beats a far smarter
# one even under a high SMART weight — a failure mode confirmed by blind
# expert comparison, which never shortlists bottom-tier models for these.
PRESETS = {
    "CHATBOT": dict(
        desc="A conversational assistant answering user messages — short "
             "prompts, brief replies, high volume. Priorities: cheap and "
             "fast, smart enough to hold a conversation.",
        values=dict(input_tokens=2_000, output_tokens=300, api_calls=1_000,
                    cache=30, rmult=1.0, axis="INT", caps=[],
                    tiers=["FRONTIER", "ADVANCED", "CAPABLE"],
                    w_smart=3, w_cheap=4, w_fast=3)),
    "CODING AGENT": dict(
        desc="An AI pair-programmer or autonomous coder (Claude Code, Cursor) "
             "— it re-reads a large repo context every call (high cache hits) "
             "and burns thinking tokens. Priorities: coding skill first, "
             "cost second.",
        values=dict(input_tokens=40_000, output_tokens=4_000, api_calls=200,
                    cache=80, rmult=3.0, axis="CODE", caps=["TOOLS"],
                    tiers=["FRONTIER"],
                    w_smart=5, w_cheap=2, w_fast=1)),
    "AGENT": dict(
        desc="A multi-step tool-using workflow (research, browsing, "
             "operations) — long contexts carried across many steps, judged "
             "on the agentic index rather than raw chat quality. Priorities: "
             "capability first.",
        values=dict(input_tokens=25_000, output_tokens=3_000, api_calls=300,
                    cache=75, rmult=2.0, axis="AGENT", caps=["TOOLS"],
                    tiers=["FRONTIER"],
                    w_smart=4, w_cheap=2, w_fast=1)),
    "SUMMARIZE": dict(
        desc="Long documents in, short summaries out, pipeline-style — "
             "big one-shot prompts with nothing worth caching. Priorities: "
             "the cheapest model that reliably reads long inputs.",
        values=dict(input_tokens=30_000, output_tokens=800, api_calls=100,
                    cache=0, rmult=1.0, axis="INT", caps=[],
                    tiers=list(TIER_LABELS),
                    w_smart=2, w_cheap=5, w_fast=1)),
    "EXTRACTION": dict(
        desc="Pulling structured fields (JSON, entities, tables) out of short "
             "texts at volume — needs tool/schema support and consistency "
             "more than brilliance. Priorities: cheap, accurate, quick.",
        values=dict(input_tokens=4_000, output_tokens=400, api_calls=1_000,
                    cache=40, rmult=1.0, axis="INT", caps=["TOOLS"],
                    tiers=list(TIER_LABELS),
                    w_smart=3, w_cheap=4, w_fast=2)),
}

# Route-trust config, not model data: which LiteLLM billing providers count as
# a model's primary price source. Cloud resellers (Bedrock, Azure, Vertex,
# Fireworks, ...) duplicate the same models and are excluded to keep one row
# per model.
DIRECT_PROVIDERS = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "gemini": "Google",
    "deepseek": "DeepSeek",
    "mistral": "Mistral",
    "xai": "xAI",
    "groq": "Groq",
    "moonshot": "Moonshot",
    "openrouter": "OpenRouter",
    "perplexity": "Perplexity",
    "cohere_chat": "Cohere",
}

# Cosmetic display names for org segments inside model keys (e.g. the "z-ai"
# in "openrouter/z-ai/glm-5.1"). Unknown orgs fall back to title case, so new
# makers render fine without a code change.
ORG_NAMES = {
    "anthropic": "Anthropic", "openai": "OpenAI", "google": "Google",
    "meta-llama": "Meta", "mistralai": "Mistral", "deepseek": "DeepSeek",
    "moonshotai": "Moonshot", "x-ai": "xAI", "z-ai": "Z.ai", "qwen": "Qwen",
    "xiaomi": "Xiaomi", "minimax": "MiniMax", "nvidia": "NVIDIA",
}

# Date-stamp suffixes used to collapse snapshot variants onto one base name,
# e.g. gpt-5.2-2025-12-11 -> gpt-5.2, claude-opus-4-20250514 -> claude-opus-4.
DATE_SUFFIX_RE = re.compile(
    r"[-@.](20\d{2}[-.]?\d{2}[-.]?\d{2}|\d{4})(?=$|[-@.])"
)

# Initial values for every URL-bound widget that presets (or URL restores) may
# write to. Seeded into session state instead of passed as widget defaults —
# a widget with both a default and a session-state write logs a policy
# warning on every preset click.
WIDGET_DEFAULTS = dict(
    mode="RECOMMEND", axis="INT", input_tokens=10_000, output_tokens=3_000,
    api_calls=100, cache=0, rmult=1.0, batch=False, caps=[],
    w_smart=3, w_cheap=3, w_fast=0, tol=3, ccy="USD",
)


def seed_defaults():
    """Runs before any widget is created. Keys the URL supplies are left for
    the query-param binding to hydrate; everything else gets its default.
    CHATBOT starts selected so a first visit lands on a concrete, explained
    use case rather than a blank workload; deselecting it sticks."""
    if "preset" not in st.query_params:
        st.session_state.setdefault("preset", "CHATBOT")
    for k, v in WIDGET_DEFAULTS.items():
        if k not in st.query_params:
            # copy list values — session state must never alias the defaults
            st.session_state.setdefault(k, list(v) if isinstance(v, list) else v)


# =============================================================================
# Section 2: Data fetching
# =============================================================================


@st.cache_data(ttl=CACHE_TTL)
def get_exchange_rate() -> float:
    """Fetch the USD→INR rate, falling back to a constant if the API is down."""
    try:
        response = requests.get(EXCHANGE_RATE_URL, timeout=10)
        response.raise_for_status()
        return float(response.json()["rates"]["INR"])
    except (requests.RequestException, KeyError, ValueError):
        return FALLBACK_FX


def _fetch_json_with_fallback(url: str, path: str, transform,
                              headers: Optional[Dict] = None) -> Dict:
    """Fetch JSON from a URL, keep a local copy, fall back to it when offline."""
    try:
        response = requests.get(url, timeout=30, headers=headers)
        response.raise_for_status()
        data = transform(response.json())
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=1)
        except OSError:
            pass  # read-only filesystem — the in-memory cache still works
        return data
    except (requests.RequestException, ValueError):
        try:
            with open(path) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}


@st.cache_data(ttl=CACHE_TTL)
def fetch_pricing() -> Dict:
    """LiteLLM pricing catalog: litellm_key -> model data."""
    return _fetch_json_with_fallback(PRICES_URL, PRICES_FILE, lambda d: d)


@st.cache_data(ttl=CACHE_TTL)
def fetch_scores() -> Dict:
    """Artificial Analysis indices via OpenRouter: openrouter_id -> scores."""

    def transform(payload):
        out = {}
        for m in payload.get("data", []):
            aa = (m.get("benchmarks") or {}).get("artificial_analysis") or {}
            if aa.get("intelligence_index"):
                out[m["id"]] = {
                    "intelligence": aa["intelligence_index"],
                    "coding": aa.get("coding_index"),
                    "agentic": aa.get("agentic_index"),
                }
        return out

    return _fetch_json_with_fallback(SCORES_URL, SCORES_FILE, transform)


def _secret(name: str) -> str:
    try:
        return st.secrets[name]
    except (KeyError, FileNotFoundError):
        return os.environ.get(name, "")


@st.cache_data(ttl=CACHE_TTL)
def fetch_aa() -> Dict:
    """Per-model data from the Artificial Analysis API
    (https://artificialanalysis.ai/): median output speed, TTFT, and the
    intelligence/coding indices — AA scores far more models than OpenRouter's
    listing carries, so these fill score gaps for models OpenRouter lacks.
    Optional: without an AA_API_KEY the last saved snapshot serves.
    """
    key = _secret("AA_API_KEY")
    if not key:
        return _load_json(AA_FILE)

    def transform(payload):
        out = {}
        for m in payload.get("data", []):
            slug = m.get("slug") or m.get("id") or ""
            ev = m.get("evaluations") or {}
            entry = {
                "speed": m.get("median_output_tokens_per_second"),
                "ttft": m.get("median_time_to_first_token_seconds"),
                "intelligence": ev.get("artificial_analysis_intelligence_index"),
                "coding": ev.get("artificial_analysis_coding_index"),
            }
            if slug and any(v for v in entry.values()):
                out[slug] = entry
        return out

    return _fetch_json_with_fallback(
        AA_URL, AA_FILE, transform, headers={"x-api-key": key}
    )


@st.cache_data(ttl=CACHE_TTL)
def fetch_usage() -> Dict:
    """Average tokens/day routed per model over the last 7 days, from
    OpenRouter's rankings dataset (top-50 models per day by token volume).
    Real production traffic — popularity, not quality. Optional: without an
    OPENROUTER_API_KEY the last saved snapshot serves.
    """
    key = _secret("OPENROUTER_API_KEY")
    if not key:
        return _load_json(USAGE_FILE)

    def transform(payload):
        rows = payload.get("data", [])
        days = sorted({r["date"] for r in rows})[-7:]
        totals: Dict[str, int] = {}
        for r in rows:
            if r["date"] not in days:
                continue
            # permaslugs are dated ids ("deepseek/deepseek-v4-flash-20260423");
            # dated snapshots of one model collapse onto its base name.
            base = _norm(DATE_SUFFIX_RE.sub("", r.get("model_permaslug", "")))
            if not base or base == "other":
                continue
            totals[base] = totals.get(base, 0) + int(r["total_tokens"])
        return {k: v / len(days) for k, v in totals.items()} if days else {}

    return _fetch_json_with_fallback(
        USAGE_URL, USAGE_FILE, transform,
        headers={"Authorization": f"Bearer {key}"},
    )


# =============================================================================
# Section 3: Catalog building
# =============================================================================


def _norm(name: str) -> str:
    """Normalize a model name for cross-catalog matching."""
    return re.sub(r"[.\s_]", "-", name.lower().split("/")[-1])


def _norm_sorted(name: str) -> str:
    """Word-order-insensitive form of _norm — catalogs disagree on token
    order for the same model (litellm claude-4-sonnet vs OpenRouter
    claude-sonnet-4, AA claude-4-5-haiku)."""
    return "-".join(sorted(_norm(name).split("-")))


def _index_by_norm(d: Dict) -> Tuple[Dict, Dict]:
    """Two lookup indexes over a feed: exact normalized name, and a
    word-order-insensitive fallback. Fallback entries whose sorted form is
    ambiguous (two different source models) are dropped rather than guessed."""
    exact = {_norm(k): v for k, v in d.items()}
    fallback: Dict = {}
    ambiguous = set()
    for k, v in d.items():
        s = _norm_sorted(k)
        if s in fallback:
            ambiguous.add(s)
        fallback[s] = v
    for s in ambiguous:
        del fallback[s]
    return exact, fallback


def _lookup(indexes: Tuple[Dict, Dict], name: str) -> Dict:
    exact, fallback = indexes
    return exact.get(_norm(name)) or fallback.get(_norm_sorted(name)) or {}


def _fmt_ctx(n: Optional[int]) -> str:
    if not n:
        return "—"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.0f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def _is_active(model_data: Dict) -> bool:
    """False for models whose published deprecation date has passed."""
    date_str = model_data.get("deprecation_date")
    if not date_str:
        return True
    try:
        return dt.date.fromisoformat(date_str) >= dt.date.today()
    except ValueError:
        return True


def _load_json(path: str) -> Dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _maker(key: str, provider: str) -> str:
    """The model's maker: the org segment of the key when the route embeds one
    (openrouter/z-ai/glm-5.1, groq/meta-llama/llama-4-maverick), else the
    billing provider."""
    segments = key.split("/")
    if len(segments) >= 3:
        org = segments[-2]
        return ORG_NAMES.get(org, org.replace("-", " ").title())
    return DIRECT_PROVIDERS[provider]


def _lookup_first(indexes: Tuple[Dict, Dict], names) -> Dict:
    for n in names:
        hit = _lookup(indexes, n)
        if hit:
            return hit
    return {}


def _row(key: str, name: str, maker: str, m: Dict, score_idx: Tuple[Dict, Dict],
         aa_idx: Tuple[Dict, Dict], usage_idx: Tuple[Dict, Dict],
         overrides: Dict, aa_overrides: Dict) -> Dict:
    per_m = 1e6
    # Try the explicit override, the full litellm key, then the date-stripped
    # display name — dated keys ("claude-4-sonnet-20250514") only match a
    # feed under their base name.
    score = _lookup_first(score_idx, [overrides.get(key, key), name])
    aa = _lookup_first(
        aa_idx, [aa_overrides.get(key) or overrides.get(key, key), name])
    usage = _lookup_first(usage_idx, [overrides.get(key, key), name])
    return {
        "key": key,
        "model": name,
        "maker": maker,
        # OpenRouter's listing first, the AA API filling models it lacks —
        # both carry the same Artificial Analysis indices.
        "intelligence": score.get("intelligence") or aa.get("intelligence"),
        "coding": score.get("coding") or aa.get("coding"),
        "agentic": score.get("agentic"),
        "speed": aa.get("speed"),
        "ttft": aa.get("ttft"),
        "usage": usage or None,
        "ctx": _fmt_ctx(m.get("max_input_tokens")),
        # The same figure the display string formats, kept as a number: whether
        # a model can take the workload's input is a comparison, not a label.
        "ctx_tokens": m.get("max_input_tokens"),
        "in_per_m": (m.get("input_cost_per_token") or 0) * per_m,
        "out_per_m": (m.get("output_cost_per_token") or 0) * per_m,
        "cache_rd_per_m": (m.get("cache_read_input_token_cost") or 0) * per_m,
        "cache_wr_per_m": (m.get("cache_creation_input_token_cost") or 0) * per_m,
        "batch_in_per_m": (m.get("input_cost_per_token_batches") or 0) * per_m,
        "batch_out_per_m": (m.get("output_cost_per_token_batches") or 0) * per_m,
        "reasoning": bool(m.get("supports_reasoning")),
        "vision": bool(m.get("supports_vision")),
        "tools": bool(m.get("supports_function_calling")),
        "pdf": bool(m.get("supports_pdf_input")),
        "deprecates": m.get("deprecation_date") or "",
    }


def _assign_tiers(df: pd.DataFrame) -> pd.DataFrame:
    """Tier = quartile of the intelligence index among scored models."""
    scored = df["intelligence"].dropna()
    if scored.empty:
        df["tier"] = "—"
        return df
    q75, q50, q25 = scored.quantile([0.75, 0.5, 0.25])

    def tier(x):
        if pd.isna(x):
            return "—"
        if x >= q75:
            return "FRONTIER"
        if x >= q50:
            return "ADVANCED"
        if x >= q25:
            return "CAPABLE"
        return "BUDGET"

    df["tier"] = df["intelligence"].map(tier)
    return df


def load_catalog(full: bool) -> pd.DataFrame:
    """Build the model catalog from the live pricing and score feeds.

    Default view: every model that has both a price and a benchmark score —
    new models appear automatically once both feeds list them. Full view adds
    the unscored remainder of the pricing catalog.
    """
    raw = fetch_pricing()
    if not raw:
        return pd.DataFrame()
    score_idx = _index_by_norm(fetch_scores())
    aa_idx = _index_by_norm(fetch_aa())
    usage_idx = _index_by_norm(fetch_usage())
    overrides = _load_json(OVERRIDES_FILE)
    aa_overrides = _load_json(AA_OVERRIDES_FILE)

    # Chat models from direct providers. The same model appears under alias
    # keys ("deepseek-v4-flash", "deepseek/deepseek-v4-flash") and dated
    # snapshots ("gpt-5.2-2025-12-11"), so rows are grouped by provider + base
    # name; the undated alias wins, else the newest snapshot.
    groups: Dict[tuple, tuple] = {}
    for key, m in raw.items():
        if not isinstance(m, dict) or m.get("mode") != "chat":
            continue
        provider = m.get("litellm_provider", "")
        if provider not in DIRECT_PROVIDERS or key.startswith("ft:"):
            continue
        if not _is_active(m):
            continue
        if not (m.get("input_cost_per_token") or m.get("output_cost_per_token")):
            continue  # zero-priced experimental entries distort comparisons
        leaf = key.split("/")[-1]
        base = re.sub(r"-latest$", "", DATE_SUFFIX_RE.sub("", leaf))
        # Alias preference within a group: plain undated key, else the newest
        # dated snapshot, else "-latest". Dated keys rank above "-latest"
        # because the score/speed feeds name models by their dated ids.
        rank = (1 if base == leaf else 0,
                0 if leaf.endswith("-latest") else 1, key)
        group_key = (provider, base)
        prev = groups.get(group_key)
        if prev is None or rank > prev[0]:
            groups[group_key] = (rank, key, m)

    rows = []
    for (provider, base), (_, key, m) in groups.items():
        maker = _maker(key, provider)
        row = _row(key, base, maker, m, score_idx, aa_idx, usage_idx,
                   overrides, aa_overrides)
        # The maker's own API counts as first-party; OpenRouter/Groq routes to
        # someone else's model are resellers.
        row["_first_party"] = DIRECT_PROVIDERS[provider] == maker
        rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # The same model reaches the catalog through several routes (direct API,
    # OpenRouter, Groq), under spelling aliases ("claude-haiku-4.5" vs
    # "claude-haiku-4-5"), and under word-order variants ("claude-4-sonnet"
    # vs "claude-sonnet-4"). Keep one row per (maker, word-order-insensitive
    # name): the first-party route if it exists, else the cheapest reseller.
    df["_sname"] = df["model"].map(_norm_sorted)
    df = (
        df.sort_values(
            ["_first_party", "in_per_m", "out_per_m"],
            ascending=[False, True, True],
        )
        .drop_duplicates(["maker", "_sname"], keep="first")
        .drop(columns=["_first_party", "_sname"])
        .reset_index(drop=True)
    )

    for col in ("intelligence", "coding", "agentic", "speed", "ttft", "usage"):
        df[col] = pd.to_numeric(df[col])  # None -> NaN, so tables show blanks
    if not full:
        df = df.dropna(subset=["intelligence"]).reset_index(drop=True)
    return _assign_tiers(df)


@st.cache_data(ttl=CACHE_TTL)
def maker_colors() -> Dict[str, str]:
    """Stable maker→color assignment shared by both charts, from the theme
    palette — otherwise plotly recolors by trace order on every filter change."""
    palette = (st.get_option("theme.chartCategoricalColors")
               or px.colors.qualitative.Bold)
    makers = sorted(load_catalog(full=True)["maker"].unique(), key=str.lower)
    return {m: palette[i % len(palette)] for i, m in enumerate(makers)}


# =============================================================================
# Section 4: Cost model and fit score
# =============================================================================


def compute_costs(
    df: pd.DataFrame,
    input_tokens: int,
    output_tokens: int,
    api_calls: int,
    cache_hit_pct: int,
    reasoning_mult: float,
    batch: bool,
) -> pd.DataFrame:
    """
    Effective cost per model:
      input  = miss_share x input_price + hit_share x cache_read_price
               (models without published cache pricing get no discount)
      output = output_price x reasoning_mult, applied only to reasoning models
      batch  = published batch prices replace base prices where available
    Cache-write premiums (e.g. Anthropic's 1.25x) are intentionally ignored:
    on steady workloads writes are a one-time cost per prompt prefix.
    """
    df = df.copy()
    in_price = df["in_per_m"].copy()
    out_price = df["out_per_m"].copy()

    if batch:
        # Both halves or neither: substituting on a published batch input price
        # alone bills output at the zero the missing batch price parses as.
        has_batch = (df["batch_in_per_m"] > 0) & (df["batch_out_per_m"] > 0)
        in_price = in_price.where(~has_batch, df["batch_in_per_m"])
        out_price = out_price.where(~has_batch, df["batch_out_per_m"])
        df["batched"] = has_batch
    else:
        df["batched"] = False

    hit = cache_hit_pct / 100.0
    cache_rd = df["cache_rd_per_m"].where(df["cache_rd_per_m"] > 0, in_price)
    in_eff = in_price * (1 - hit) + cache_rd * hit

    out_mult = df["reasoning"].map({True: reasoning_mult, False: 1.0})
    out_eff = out_price * out_mult

    df["total_usd"] = (
        (input_tokens / 1e6) * in_eff + (output_tokens / 1e6) * out_eff
    ) * api_calls

    positive = df.loc[df["total_usd"] > 0, "total_usd"]
    baseline = positive.min() if not positive.empty else 0
    df["rel"] = df["total_usd"] / baseline if baseline else float("nan")

    return df.sort_values("total_usd").reset_index(drop=True)


def add_fit(df: pd.DataFrame, axis_col: str,
            weights: Tuple[int, int, int]) -> pd.DataFrame:
    """FIT 0–100: weighted blend of percentile ranks within the current view —
    score rank, cheapness rank, speed rank. Ranks rather than min-max scaling,
    so one extreme outlier (a near-free model, a frontier price tag) cannot
    dominate the blend. A dimension with no data in view drops out; a model
    missing a value scores 0 on that dimension — being unmeasured is not a
    selling point."""
    df = df.copy()

    def rank_pct(series: pd.Series, invert: bool = False) -> Optional[pd.Series]:
        s = pd.to_numeric(series, errors="coerce")
        if s.notna().sum() == 0:
            return None
        # the best value — highest score, or lowest cost when inverted —
        # lands at percentile 1.0
        return s.rank(ascending=not invert, pct=True).fillna(0.0)

    w_smart, w_cheap, w_fast = weights
    parts, weight_sum = [], 0
    for w, n in ((w_smart, rank_pct(df[axis_col])),
                 (w_cheap, rank_pct(df["total_usd"], invert=True)),
                 (w_fast, rank_pct(df["speed"]))):
        if w and n is not None:
            parts.append(w * n)
            weight_sum += w
    df["fit"] = sum(parts) / weight_sum * 100 if weight_sum else float("nan")
    return df


def money(x: float, currency: str, fx: float) -> str:
    if currency == "INR":
        v = x * fx
        return f"₹{v:,.0f}" if v >= 100 else f"₹{v:,.2f}"
    return f"${x:,.2f}"


def md_money(x: float, currency: str, fx: float) -> str:
    """money() for markdown contexts — two bare $ in one string open a LaTeX
    math span and mangle everything between them."""
    return money(x, currency, fx).replace("$", "\\$")


def best_value(df: pd.DataFrame) -> Optional[pd.Series]:
    """Cheapest model in the highest tier present in the current view."""
    scored = df.dropna(subset=["intelligence"])
    if scored.empty:
        return None
    for label in TIER_LABELS:
        in_tier = scored[scored["tier"] == label]
        if not in_tier.empty:
            return in_tier.iloc[0]  # df is sorted by total_usd ascending
    return None


# =============================================================================
# Section 5: Token estimation dialog
# =============================================================================


@st.dialog("ESTIMATE TOKENS FROM TEXT", width="large", icon="🧮")
def estimate_dialog():
    """Estimate token counts from sample texts with tiktoken (o200k_base)."""
    st.caption(
        "PASTE SAMPLE INPUT/OUTPUT TEXT · ENCODING o200k_base · "
        "OTHER PROVIDERS' TOKENIZERS DIFFER SLIGHTLY — TREAT AS ESTIMATES"
    )
    sample_input = st.text_area("SAMPLE INPUT", height=180)
    sample_output = st.text_area("SAMPLE OUTPUT", height=180)
    if st.button("ESTIMATE AND APPLY", width="stretch"):
        if not sample_input.strip() or not sample_output.strip():
            st.error("Both sample texts are required.")
            return
        try:
            import tiktoken
        except ImportError:
            st.error("tiktoken is not installed — run: pip install tiktoken")
            return
        enc = tiktoken.get_encoding("o200k_base")
        st.session_state.input_tokens = len(enc.encode(sample_input))
        st.session_state.output_tokens = len(enc.encode(sample_output))
        st.rerun(scope="app")


@st.dialog("HOW TO USE", width="large")
def guide_dialog():
    """Walkthrough of every control, in the order a visitor meets them."""
    st.markdown(
        "**Token Tariff** is a live rate card: prices from LiteLLM's catalog, "
        "intelligence / coding / agentic scores from Artificial Analysis, "
        "refreshed hourly. It answers two questions — **what does your workload "
        "cost on every model**, and **which model is the smartest buy for that "
        "money?**"
    )
    st.markdown(
        "**THREE MODES, ONE PER QUESTION.** The control up top picks which "
        "question the page answers; the WORKLOAD, currency and everything "
        "else you set carry across all three.\n\n"
        "**RECOMMEND — *what should I use?*** Three decisions. **① USE CASE**: "
        "the pills (CHATBOT, CODING AGENT, …) set a typical workload shape, "
        "the right score axis, a sensible tier range and the priorities in "
        "one click; change anything and a PRESET MODIFIED chip offers a "
        "reset. **② WORKLOAD**: tokens per call, number of calls, "
        "prompt-cache hit rate (cache math counts reads only — write "
        "premiums are a one-time cost), reasoning output multiplier, Batch "
        "API pricing; ESTIMATE FROM TEXT counts tokens from pasted samples. "
        "**③ OPTIMIZE FOR**: BALANCED, SMARTEST, CHEAPEST or FASTEST — the "
        "SMART/CHEAP/FAST weights behind the ranking, with the individual "
        "sliders under ADVANCED (weights outside the four read as CUSTOM). "
        "REFINE in the sidebar holds providers, tiers, required capabilities "
        "and the score axis.\n\n"
        "**MATCH — *the same for less.*** Pick the model you run today; the "
        "view keeps only models scoring within MATCH WITHIN points of it, "
        "ranked by your workload's cost, and the verdict names the cheapest "
        "and by how much.\n\n"
        "**LOOK UP — *what does X cost?*** Search the whole catalog by model, "
        "maker, or litellm key, including models with no benchmark score. An "
        "empty box lists everything.\n\n"
        "**READ THE VERDICT** — the **▸ model** line is the recommendation, "
        "followed by its tier, score, speed and workload cost. CHEAPER "
        "OPTION and MORE CAPABLE OPTION name the two models worth a second "
        "look, each with what it trades; either is absent when nothing "
        "qualifies. The table's FIT column (0–100) blends how each model "
        "ranks *within the current view* on score, cost and speed — it moves "
        "when the filters do, so the reasons matter more than the number.\n\n"
        "**SHARE** — every control lives in the URL, mode included. Copy it "
        "and the exact same view opens for anyone."
    )
    st.markdown(
        "**READING THE RESULTS** — the table ranks by cost; select a row for "
        "the full rate card (cache and batch prices, context window, "
        "capabilities, deprecation date). USE B/D is billions of tokens/day "
        "routed through OpenRouter — real traffic, which tells you what the "
        "market actually runs, not what benchmarks like. The FRONTIER chart "
        "plots score against cost on a log axis: the dotted line is the "
        "Pareto frontier, and anything below it is beaten on both price and "
        "score.\n\n"
        "**Cost is per-token, computed from the token counts you enter and "
        "applied identically to every model.** Two models rarely spend the "
        "same number of tokens on the same task — tokenizers differ and some "
        "models are far more verbose (reasoning models at high effort "
        "especially), so a lower per-token rate can still mean a *higher cost "
        "per finished task*. Treat the ranking as a screen and confirm "
        "cost-per-task on your own workload.\n\n"
        "Benchmark scores are likewise a screen, not a guarantee — they may "
        "not reflect how a model behaves on your actual prompts, and no feed "
        "here measures provider reliability or language coverage. Evaluate "
        "the shortlist on your own workload before switching models."
    )


# =============================================================================
# Section 6: UI — modes, presets, filters, top strip
# =============================================================================


def mode_control() -> str:
    """The one decision above every other: which question the page answers."""
    return st.segmented_control(
        "MODE", MODES, key="mode", bind="query-params",
        label_visibility="collapsed",
        help="RECOMMEND names a model for a use case · MATCH finds cheaper "
             "equals of a model you already run · LOOK UP searches the whole "
             "catalog, scored or not.",
    ) or "RECOMMEND"


def _apply_preset(name: str):
    for k, v in PRESETS[name]["values"].items():
        # copy list values — session state must never alias preset config
        st.session_state[k] = list(v) if isinstance(v, list) else v


def _preset_diverges(name: str) -> bool:
    """True when a control holds something its preset did not set. A pill that
    still reads as selected after the workload or the filters move would claim
    assumptions the page has stopped using."""
    for k, v in PRESETS[name]["values"].items():
        active = st.session_state.get(k)
        if isinstance(v, list):
            if sorted(active or []) != sorted(v):
                return True
        elif active != v:
            return True
    return False


def preset_weights(name: Optional[str]) -> Optional[Tuple[int, int, int]]:
    """The three priority weights a use case sets, or None when none is
    selected."""
    if name not in PRESETS:
        return None
    values = PRESETS[name]["values"]
    return tuple(values[k] for k in WEIGHT_KEYS)


def preset_row():
    """Use-case pills. Selecting one writes the preset's values into the bound
    widgets' session state — which is why this must run before the sidebar and
    workload widgets are instantiated. On a first load, values already pinned
    in the URL win over the preset so shared links reproduce exactly.

    The reset button restores through a callback, which runs before the script
    does: by the time the widgets are built the preset's values are already in
    place, so no second pass is needed.

    Returns the slot the modified indicator renders into. Whether a preset has
    been edited cannot be answered here: OPTIMIZE FOR and the REFINE filters
    write preset-owned values, and both run after this does."""
    tooltip = "One click configures the workload, score axis, model tiers, " \
              "and priorities. Everything stays editable.\n\n" + "\n".join(
                  f"- **{name}** — {p['desc']}" for name, p in PRESETS.items())
    sel = st.pills("USE CASE", list(PRESETS), key="preset", bind="query-params",
                   help=tooltip)
    if sel and sel != st.session_state.get("_preset_applied"):
        first_load = "_preset_applied" not in st.session_state
        for k, v in PRESETS[sel]["values"].items():
            if first_load and k in st.query_params:
                continue
            st.session_state[k] = list(v) if isinstance(v, list) else v
    st.session_state["_preset_applied"] = sel
    if sel:
        st.caption(PRESETS[sel]["desc"])
    return st.empty()


def preset_notice(slot, name: Optional[str]):
    """The modified indicator, once every control that can move a preset value
    has written. Read any earlier and the run in which OPTIMIZE FOR or a REFINE
    filter is what moved renders the state before it moved — the chip then
    arrives one interaction late, describing the previous click."""
    if not name or name not in PRESETS or not _preset_diverges(name):
        return
    with slot.container(horizontal=True, vertical_alignment="center",
                        gap="small"):
        st.badge("PRESET MODIFIED", color="orange")
        st.button("RESET TO PRESET", on_click=_apply_preset, args=(name,),
                  help=f"Restore every value {name} sets.")


def carried(key: str) -> object:
    """A URL-bound value in a mode that renders no widget for it: session
    state once a widget has run, else the URL, else the default. Query params
    arrive as strings, so the default's type does the parsing."""
    if key in st.session_state:
        return st.session_state[key]
    default = WIDGET_DEFAULTS[key]
    raw = st.query_params.get(key)
    if raw is None:
        return default
    try:
        return type(default)(raw)
    except (TypeError, ValueError):
        return default


def weights_label() -> str:
    """The OPTIMIZE FOR label the active weights spell, or CUSTOM."""
    active = tuple(carried(k) for k in WEIGHT_KEYS)
    for label, weights in OPTIMIZE_FOR.items():
        if weights == active:
            return label
    return CUSTOM


def optimize_row() -> Tuple[int, int, int]:
    """The priority decision, and the sliders it stands for.

    The control and the sliders are two views of one state, so each run starts
    by deciding which of them moved: an untouched control re-reads the weights
    (a preset or a slider drag changed them), a touched one writes its mapping
    into them. The re-read runs on every untouched pass, so neither a preset
    nor a slider drag can leave the control claiming a priority the numbers do
    not spell. A link that pins the weights themselves keeps them; the label
    it carries only fills in weights the link left out.

    A use case brings priorities of its own, and most of them spell none of the
    four named options. While the weights are still the ones it set, the
    control is the preset's to describe: it renders unselected under a line
    naming the owner, rather than reading CUSTOM at a visitor who has
    customised nothing."""
    first_load = "_opt_applied" not in st.session_state
    label = weights_label()
    owned = (preset_weights(st.session_state.get("preset"))
             == tuple(carried(k) for k in WEIGHT_KEYS))
    touched = (not first_load
               and st.session_state.get("opt") != st.session_state["_opt_applied"])
    pinned = (first_load and "opt" in st.query_params
              and not any(k in st.query_params for k in WEIGHT_KEYS))
    if not touched and not pinned:
        st.session_state.opt = None if owned else label
    # CUSTOM is a description of the sliders, not a choice: it is offered only
    # while it is what the weights say and no preset is still standing behind
    # them.
    options = list(OPTIMIZE_FOR)
    if not owned and CUSTOM in (label, st.session_state.get("opt")):
        options.append(CUSTOM)
    sel = st.segmented_control(
        "OPTIMIZE FOR", options, key="opt", bind="query-params",
        help="Weights the ranking behind the verdict. ADVANCED holds the "
             "individual SMART / CHEAP / FAST weights; anything outside these "
             "four combinations reads as CUSTOM, and a use case's own "
             "priorities read as the use case.",
    )
    owner_note = st.empty()
    if sel in OPTIMIZE_FOR and sel != label:
        if not (first_load and any(k in st.query_params for k in WEIGHT_KEYS)):
            for key, value in zip(WEIGHT_KEYS, OPTIMIZE_FOR[sel]):
                st.session_state[key] = value
    st.session_state["_opt_applied"] = sel

    with st.expander("ADVANCED"):
        st.caption("PRIORITIES",
                   help="Weights for the FIT score behind the verdict: how much "
                        "the recommendation should care about the score axis, "
                        "the workload cost, and output speed.")
        w_smart = st.slider("SMART", 0, 5, key="w_smart", bind="query-params")
        w_cheap = st.slider("CHEAP", 0, 5, key="w_cheap", bind="query-params")
        w_fast = st.slider("FAST", 0, 5, key="w_fast", bind="query-params")
    # The sliders are the last thing that can write a weight, so who owns them
    # is settled here and rendered back into the line above them.
    owner = st.session_state.get("preset")
    if sel is None and preset_weights(owner) == (w_smart, w_cheap, w_fast):
        owner_note.caption(f"AS SET BY {owner}")
    return w_smart, w_cheap, w_fast


def refine_sidebar(df_catalog: pd.DataFrame) -> dict:
    """REFINE: the filters a recommendation usually does not need. Collapsed,
    because every one of them narrows a field the presets already shaped."""
    with st.sidebar, st.expander("REFINE"):
        makers = sorted(df_catalog["maker"].unique(), key=str.lower)
        # Seed the selection unless the URL carries one; URL-restored values
        # may reference makers absent from the catalog — drop those before the
        # widget renders.
        if "prov" not in st.query_params:
            st.session_state.setdefault(
                "prov", [m for m in DEFAULT_MAKERS if m in makers] or makers)
        if "prov" in st.session_state:
            st.session_state.prov = [
                m for m in st.session_state.prov if m in makers]
        sel_makers = st.pills(
            "PROVIDERS", makers, selection_mode="multi",
            key="prov", bind="query-params",
            help="The default view is the three major labs. Add the rest to "
                 "compare the whole scored field.",
        )

        if "tiers" not in st.query_params:
            st.session_state.setdefault("tiers", TIER_LABELS)
        if "tiers" in st.session_state:
            st.session_state.tiers = [
                t for t in st.session_state.tiers if t in TIER_LABELS]
        sel_tiers = st.pills(
            "TIER", TIER_LABELS, selection_mode="multi",
            key="tiers", bind="query-params",
            help="Quartiles of the intelligence index across scored models: "
                 "FRONTIER is the top quarter of the current field.",
        )

        caps = st.multiselect(
            "CAPABILITIES", list(CAPABILITIES), key="caps",
            bind="query-params", placeholder="ANY",
            help="Keep only models that support every capability picked here.",
        )

        axis = st.segmented_control(
            "AXIS", list(AXES),
            key="axis", bind="query-params",
            help="Which score drives the verdict, chart, and score column: "
                 "general intelligence, coding, or agentic.",
        )

    return {
        "sel_makers": sel_makers,
        "sel_tiers": sel_tiers,
        "n_makers": len(makers),
        "caps": caps,
        "axis": axis or "INT",
        "anchor": None,
        "tolerance": 0,
    }


def match_row(df_catalog: pd.DataFrame) -> dict:
    """MATCH: one reference model, and how far below its score still counts as
    equal. The tolerance appears only once there is something to be within.

    No provider, tier or capability filter — "who matches this for less" is a
    question about the whole field, and a filter would answer a smaller one.

    The options are the models scored on the axis in force, read from state
    before the axis control is instantiated: a rerun already carries the new
    axis, and asking to match a model that has no score on the axis being
    matched on is a question with no answer. An anchor arriving from a link is
    kept in the list whatever it scores, so the widget and the URL survive long
    enough for the verdict to explain itself."""
    axis_col = AXES.get(carried("axis"), "intelligence")
    scored_models = sorted(df_catalog.dropna(subset=[axis_col])["model"])
    restored = st.session_state.get("anchor") or st.query_params.get("anchor")
    if restored and restored not in scored_models and \
            (df_catalog["model"] == restored).any():
        scored_models = sorted(scored_models + [restored])
    row = st.container(horizontal=True, vertical_alignment="bottom", gap="medium")
    with row:
        anchor = st.selectbox(
            "MATCH THIS MODEL", scored_models, index=None,
            placeholder="THE MODEL YOU RUN TODAY ...",
            key="anchor", bind="query-params",
            help="Keep only models scoring at least as high as this one "
                 "(minus the tolerance), ranked by your workload's cost.",
        )
        axis = st.segmented_control(
            "AXIS", list(AXES), key="axis", bind="query-params",
            help="Which index the match is judged on.",
        )
        tolerance = st.slider(
            "MATCH WITHIN", 0, 10, format="%d pts",
            key="tol", bind="query-params",
            help="How many points below the anchor's score still count as equal.",
        ) if anchor else 0
    return {
        "sel_makers": None,
        "sel_tiers": None,
        "n_makers": 0,
        "caps": [],
        "axis": axis or "INT",
        "anchor": anchor,
        "tolerance": tolerance,
    }


def lookup_row() -> str:
    """LOOK UP: a search box over the whole catalog and nothing else. An empty
    box is the whole catalog, which is the honest answer to "what is in here"."""
    query = st.text_input(
        "SEARCH", key="q", bind="query-params",
        placeholder="FIND A MODEL BY NAME, MAKER, OR LITELLM KEY ...",
        label_visibility="collapsed",
        help="Searches the full catalog, including models with no benchmark "
             "score. An empty box lists everything.",
    )
    return (query or "").strip()


def workload_strip() -> dict:
    """The settings every mode shares: the workload the costs are computed on,
    the display currency, and the guide."""
    with st.container(horizontal=True, vertical_alignment="bottom",
                      gap="medium"):
        with st.popover("WORKLOAD"):
            input_tokens = st.number_input(
                "INPUT TOKENS / CALL", 1, None, step=1000,
                key="input_tokens", bind="query-params",
            )
            output_tokens = st.number_input(
                "OUTPUT TOKENS / CALL", 1, None, step=500,
                key="output_tokens", bind="query-params",
            )
            api_calls = st.number_input(
                "API CALLS", 1, None, step=10,
                key="api_calls", bind="query-params",
            )
            if st.button("ESTIMATE FROM TEXT", icon="🧮", width="stretch"):
                estimate_dialog()
            st.divider()
            st.caption("WORKLOAD DETAILS")
            cache_hit_pct = st.slider(
                "PROMPT-CACHE HIT RATE", 0, 95, step=5, format="%d%%",
                key="cache", bind="query-params",
                help="Share of input tokens served from the provider's prompt cache, billed at the cache-read rate. Models without published cache pricing get no discount. Agentic workloads commonly sit at 70–90%.",
            )
            reasoning_mult = st.slider(
                "REASONING OUTPUT MULTIPLIER", 1.0, 10.0, step=0.5, format="%.1fx",
                key="rmult", bind="query-params",
                help="Reasoning models bill thinking tokens as output. This multiplies output tokens for reasoning-capable models only.",
            )
            batch = st.toggle(
                "BATCH API PRICING", key="batch", bind="query-params",
                help="Use published Batch API prices where available (typically ~50% off). Models without published batch prices keep live prices.",
            )
        currency = st.segmented_control(
            "CCY", ["USD", "INR"],
            label_visibility="collapsed", key="ccy", bind="query-params",
        )
        if st.button("GUIDE", help="How to use this app"):
            guide_dialog()
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "api_calls": api_calls,
        "cache_hit_pct": cache_hit_pct,
        "reasoning_mult": reasoning_mult,
        "batch": batch,
        "currency": currency or "USD",
    }


def apply_filters(df: pd.DataFrame, f: dict) -> pd.DataFrame:
    """Narrow the catalog to the current view. A None filter is a mode that
    does not offer it, which is not the same as one with nothing selected."""
    # The anchor's score is resolved against the whole catalog, before any
    # narrowing — "match the intelligence of X" must keep working when X's
    # own provider or tier is filtered out of view.
    anchor_rows = df[df["model"] == f["anchor"]] if f["anchor"] else df.iloc[:0]
    if f["sel_makers"] is not None:
        df = df[df["maker"].isin(f["sel_makers"])]
    if f["sel_tiers"] is not None and set(f["sel_tiers"]) != set(TIER_LABELS):
        df = df[df["tier"].isin(f["sel_tiers"])]
    for cap in f["caps"]:
        df = df[df[CAPABILITIES[cap]]]
    if not anchor_rows.empty:
        axis_col = AXES[f["axis"]]
        if pd.notna(anchor_rows.iloc[0][axis_col]):
            floor = anchor_rows.iloc[0][axis_col] - f["tolerance"]
            df = df[df[axis_col] >= floor]
    return df


def fits_context(df: pd.DataFrame, input_tokens: int) -> Tuple[pd.DataFrame, int]:
    """The models that can take the workload's input, and how many cannot.

    A ranking is a plan to run the workload, and a model whose context window
    is smaller than one call's input cannot run it at any price. Models whose
    context is unknown stay in view: absence of data is not disqualification,
    the same rule every other blank in the catalog follows.
    """
    known = pd.to_numeric(df["ctx_tokens"], errors="coerce")
    too_small = known.notna() & (known > 0) & (known < input_tokens)
    return df[~too_small], int(too_small.sum())


def context_note(n_excluded: int, input_tokens: int) -> str:
    return (f"{n_excluded:,} MODEL{'S' if n_excluded > 1 else ''} OUT OF VIEW · "
            f"CONTEXT WINDOW SMALLER THAN {input_tokens:,} INPUT TOKENS PER CALL")


def search_catalog(base: pd.DataFrame, query: str) -> pd.DataFrame:
    """Name/maker/key lookup across the full catalog — the 'is model X in here
    and what does it cost' path."""
    q = query.lower()
    mask = (base["model"].str.lower().str.contains(q, regex=False)
            | base["maker"].str.lower().str.contains(q, regex=False)
            | base["key"].str.lower().str.contains(q, regex=False))
    return base[mask]


# =============================================================================
# Section 7: UI — results
# =============================================================================


def match_verdict(df: pd.DataFrame, f: dict, currency: str, fx: float):
    """MATCH's verdict: the cheapest model that holds the anchor's level."""
    axis_col = AXES[f["axis"]]
    scored = df.dropna(subset=[axis_col])
    if not f["anchor"] or scored.empty:
        return

    anchor_rows = df[df["model"] == f["anchor"]]
    # An anchor carried in from a link may hold no score on the axis now in
    # force. Nothing is within three points of a blank, so no floor was
    # applied — the field below is the whole catalog, and naming its cheapest
    # model would present an unfiltered ranking as a match.
    if not anchor_rows.empty and pd.isna(anchor_rows.iloc[0][axis_col]):
        st.info(f"{f['anchor']} has no {f['axis']} score, so there is nothing "
                f"to match on this axis — switch axis, or pick another model.")
        return

    winner = scored.iloc[0]  # cheapest at/above the anchor floor
    st.markdown(f"## ▸ {winner['model']}")
    if anchor_rows.empty:
        # The anchor set the score floor but is itself outside the tolerance
        # band, so there is no anchor cost to compare against.
        st.markdown(
            f"**VERDICT** · Matches **{f['anchor']}** within "
            f"{f['tolerance']} pts on {f['axis']} at "
            f"**{md_money(winner['total_usd'], currency, fx)}** — "
            f"{f['anchor']} itself is outside the current view."
        )
    elif winner["model"] != f["anchor"]:
        anchor_cost = anchor_rows.iloc[0]["total_usd"]
        ratio = (anchor_cost / winner["total_usd"]
                 if winner["total_usd"] else float("nan"))
        st.markdown(
            f"**VERDICT** · Matches **{f['anchor']}** within "
            f"{f['tolerance']} pts on {f['axis']} at "
            f"**{md_money(winner['total_usd'], currency, fx)}** — "
            f"**{ratio:,.1f}× cheaper**."
        )
    else:
        st.markdown(
            f"**VERDICT** · Nothing beats **{f['anchor']}** on price at "
            f"this level — it is the cheapest model within "
            f"{f['tolerance']} pts."
        )


def pick_model(df: pd.DataFrame) -> Optional[pd.Series]:
    """The recommendation: best FIT, or the best value in view when every
    priority weight is zero and FIT has nothing to say."""
    if df["fit"].notna().any():
        return df.loc[df["fit"].idxmax()]
    return best_value(df)


def verdict(pick: pd.Series, df: pd.DataFrame, f: dict, opt_label: str,
            currency: str, fx: float):
    """The recommendation and the reasons for it.

    FIT ranks the field but stays out of this sentence and in the table: it is
    a percentile blend over whatever is in view, so the number moves when the
    filters do while the reasons under it hold."""
    axis_col = AXES[f["axis"]]
    st.markdown(f"## ▸ {pick['model']}")
    if pd.isna(pick["fit"]):
        # FIT goes blank for two different reasons, and they are two different
        # findings: nothing was asked of the ranking, or what was asked reads a
        # score no model in view carries.
        lead = ("Best value in view — every priority weight is zero"
                if not any(f["weights"]) else
                f"Best value in view — nothing in view is scored on "
                f"{f['axis']}")
    elif opt_label == CUSTOM:
        lead = ("Best fit for SMART {} · CHEAP {} · FAST {} across "
                "{:,} models in view".format(*f["weights"], len(df)))
    elif opt_label.startswith("AS "):
        lead = (f"Best fit for {opt_label[3:]}'s priorities across "
                f"{len(df):,} models in view")
    else:
        lead = f"Best {opt_label} fit across {len(df):,} models in view"
    bits = [lead, pick["tier"] if pick["tier"] != "—" else "UNSCORED"]
    if pd.notna(pick[axis_col]):
        bits.append(f"{f['axis']} {pick[axis_col]:.1f}")
    if pd.notna(pick["speed"]):
        bits.append(f"{pick['speed']:.0f} TOK/S")
    cost = f"**{md_money(pick['total_usd'], currency, fx)}** per workload"
    if pd.notna(pick["rel"]) and pick["rel"] > 1.05:
        cost += f" ({pick['rel']:,.1f}× the cheapest)"
    bits.append(cost)
    if pick["deprecates"]:
        bits.append(f"⚠ DEPRECATES {pick['deprecates']}")
    st.markdown(f"**VERDICT** · {' · '.join(bits)}.")

    w_fast = f["weights"][2]
    beaten = speed_penalized(df, pick, axis_col, w_fast)
    if beaten is not None:
        st.caption(
            f"{beaten['model']} SCORES HIGHER ON {f['axis']} AND COSTS LESS, "
            f"AND STILL RANKS BELOW: NOBODY HAS PUBLISHED ITS SPEED, WHICH FIT "
            f"SCORES AS ZERO AGAINST A FAST WEIGHT OF {w_fast}".upper())


def alternatives(df: pd.DataFrame, pick: pd.Series,
                 axis_col: str) -> Tuple[Optional[pd.Series], Optional[pd.Series]]:
    """The two models worth a second look: the cheapest near-equal that costs
    less, and the cheapest clear upgrade. Either is None when nothing
    qualifies — an alternative that is not one is noise."""
    if pd.isna(pick[axis_col]):
        return None, None
    scored = df.dropna(subset=[axis_col])
    scored = scored[scored["key"] != pick["key"]]
    score, cost = pick[axis_col], pick["total_usd"]
    # The cheaper option gives ground on score: a model that costs less AND
    # scores higher is an upgrade, and belongs in the other card.
    cheaper = scored[scored[axis_col].between(score - CHEAPER_DROP, score)
                     & (scored["total_usd"] < cost)]
    capable = scored[scored[axis_col] >= score + CAPABLE_GAIN]
    # df arrives sorted by cost, so the first surviving row is the cheapest.
    return (cheaper.iloc[0] if not cheaper.empty else None,
            capable.iloc[0] if not capable.empty else None)


def speed_penalized(df: pd.DataFrame, pick: pd.Series, axis_col: str,
                    w_fast: int) -> Optional[pd.Series]:
    """The cheapest model that beats the pick on both the score axis and cost
    and still ranks below it, losing only where it was never measured.

    A model with no speed figure scores zero on that dimension — the policy is
    deliberate, since being unmeasured is not a selling point, but it can seat
    a dominated model above one that beats it twice over. Naming that model is
    the alternative to letting the ranking assert something the data does not.
    """
    if not w_fast or df.empty or pd.isna(pick[axis_col]):
        return None
    beaten = df[(df["key"] != pick["key"]) & df["speed"].isna()
                & (df[axis_col] > pick[axis_col])
                & (df["total_usd"] < pick["total_usd"])]
    return beaten.iloc[0] if not beaten.empty else None  # df is cost-sorted


def _tradeoff(row: pd.Series, pick: pd.Series, axis_col: str, axis: str,
              w_fast: int) -> str:
    """What the alternative costs and what it costs you, in that order —
    including the FAST weight it is being scored as zero on when nobody has
    measured its speed."""
    delta = row[axis_col] - pick[axis_col]
    if abs(delta) < 0.05:
        score_bit = f"SAME {axis} SCORE"
    else:
        score_bit = (f"{abs(delta):.1f} PTS "
                     f"{'ABOVE' if delta > 0 else 'BELOW'} ON {axis}")
    ratio = (pick["total_usd"] / row["total_usd"]
             if row["total_usd"] else float("nan"))
    if pd.isna(ratio) or 0.95 <= ratio <= 1.05:
        cost_bit = "ABOUT THE SAME COST"
    elif ratio > 1:
        cost_bit = f"{ratio:,.1f}× CHEAPER"
    else:
        cost_bit = f"{1 / ratio:,.1f}× THE COST"
    bits = [score_bit, cost_bit]
    if w_fast and pd.isna(row["speed"]):
        bits.append("SPEED UNMEASURED")
    return " · ".join(bits)


def alternative_cards(df: pd.DataFrame, pick: pd.Series, f: dict,
                      currency: str, fx: float):
    """Two tradeoffs against the recommendation, or nothing. Naming a cut for
    every dimension would put four winners under a one-winner verdict."""
    axis_col = AXES[f["axis"]]
    cheaper, capable = alternatives(df, pick, axis_col)
    cards = [
        ("CHEAPER OPTION", cheaper,
         f"Cheapest model that costs less than the pick and gives up at most "
         f"{CHEAPER_DROP} index points."),
        ("MORE CAPABLE OPTION", capable,
         f"Lowest-cost model scoring at least {CAPABLE_GAIN} points above "
         f"the pick."),
    ]
    cards = [c for c in cards if c[1] is not None]
    if not cards:
        return
    # Two columns even for one card — a lone alternative stretched across the
    # page would read as a second verdict.
    for col, (label, row, tip) in zip(st.columns(2), cards):
        with col, st.container(border=True):
            st.caption(label, help=tip)
            st.markdown(
                f"**{row['model']}** · {md_money(row['total_usd'], currency, fx)}")
            st.caption(_tradeoff(row, pick, axis_col, f["axis"],
                                 f["weights"][2]))


def frontier_chart(df: pd.DataFrame, f: dict, currency: str, fx: float,
                   colors: Dict[str, str]):
    """Score vs. workload cost, log-x, with the Pareto frontier drawn."""
    axis_col = AXES[f["axis"]]
    scored = df.dropna(subset=[axis_col]).copy()
    if scored.empty:
        st.info("No scored models in view — the frontier needs Artificial Analysis coverage.")
        return
    scored["total"] = scored["total_usd"] * (fx if currency == "INR" else 1)

    fig = px.scatter(
        scored, x="total", y=axis_col, color="maker",
        hover_name="model", log_x=True, color_discrete_map=colors,
    )
    fig.update_traces(marker=dict(size=9))

    # Pareto frontier: walking up the cost axis, keep models that raise the
    # best score seen so far. Everything below the line is dominated.
    frontier = []
    best = -1.0
    for _, r in scored.sort_values("total").iterrows():
        if r[axis_col] > best:
            best = r[axis_col]
            frontier.append(r)
    fdf = pd.DataFrame(frontier)
    fig.add_scatter(
        x=fdf["total"], y=fdf[axis_col], mode="lines",
        line=dict(color=st.get_option("theme.primaryColor") or "#4DA6FF",
                  width=1, dash="dot"),
        name="FRONTIER", hoverinfo="skip",
    )
    last_labeled = None
    n_labels = 0
    for _, r in fdf.iterrows():
        # Label frontier points, skipping any within 2 score points of the
        # previous label, and alternating label side — clusters otherwise
        # render as overlapping text.
        if last_labeled is not None and r[axis_col] - last_labeled < 2:
            continue
        last_labeled = r[axis_col]
        left = n_labels % 2 == 0
        n_labels += 1
        # On a log axis, plotly annotation x-coordinates are log10 values.
        fig.add_annotation(
            x=math.log10(r["total"]), y=r[axis_col], text=r["model"],
            showarrow=False, xanchor="left" if left else "right",
            xshift=8 if left else -8,
            font=dict(size=10, color=st.get_option("theme.textColor") or "#CFE0F4"),
        )

    axis_name = {"INT": "INTELLIGENCE", "CODE": "CODING", "AGENT": "AGENTIC"}
    fig.update_layout(
        height=480, margin=dict(l=0, r=0, t=8, b=0),
        xaxis_title=f"WORKLOAD COST ({currency}, LOG)",
        yaxis_title=f"{axis_name[f['axis']]} INDEX",
        legend=dict(orientation="h", y=-0.18, title=None),
        font=dict(family="JetBrains Mono, monospace", size=11),
    )
    st.plotly_chart(fig, width="stretch")


def totals_chart(df: pd.DataFrame, currency: str, fx: float,
                 colors: Dict[str, str]):
    chart_df = df.head(40).copy()
    chart_df["total"] = chart_df["total_usd"] * (fx if currency == "INR" else 1)
    fig = px.bar(
        chart_df, x="total", y="model", color="maker", orientation="h",
        color_discrete_map=colors,
    )
    fig.update_layout(
        height=480, margin=dict(l=0, r=0, t=8, b=0),
        xaxis_title=f"TOTAL ({currency})", yaxis_title=None,
        yaxis=dict(categoryorder="total descending"),
        legend=dict(orientation="h", y=-0.15, title=None),
        font=dict(family="JetBrains Mono, monospace", size=11),
    )
    st.plotly_chart(fig, width="stretch")
    if len(df) > 40:
        st.caption(f"CHART: 40 CHEAPEST OF {len(df)} — TABLE HAS ALL")


def ledger(df: pd.DataFrame, axis_col: str, currency: str, fx: float) -> Optional[int]:
    """The cost table. Returns the selected row position, if any."""
    view = df.copy()
    for col in ("in_per_m", "out_per_m"):
        view[col] = view[col] * (fx if currency == "INR" else 1)
    view["total_disp"] = view["total_usd"].apply(lambda x: money(x, currency, fx))
    unit = "₹" if currency == "INR" else "$"
    axis_label = {"intelligence": "INT", "coding": "CODE", "agentic": "AGENT"}
    # Decision columns (FIT, TOTAL, score, speed) come first — the table
    # shares its row with the chart, and anything past ~5 columns is behind
    # a horizontal scroll.
    view["usage_b"] = view["usage"] / 1e9
    columns = ["model", "fit", "total_disp", axis_col, "speed", "tier",
               "usage_b", "in_per_m", "out_per_m"]
    for col, src in (("speed", "speed"), ("usage_b", "usage")):
        if view[src].isna().all():
            columns.remove(col)  # feed absent — don't show a dead column

    # A float NaN reaches the data grid as the literal word "None". Not every
    # model is scored on every axis, and AA has measured the speed of only some
    # of them, so the display frame formats those cells itself and the grid
    # never sees a blank. Ranking, FIT and the charts read the numeric columns
    # on df, which this copy does not touch.
    for col, fmt in ((axis_col, "{:.1f}"), ("speed", "{:.0f}"),
                     ("usage_b", "{:.0f}")):
        if col in columns:
            view[col] = view[col].map(
                lambda v, fmt=fmt: fmt.format(v) if pd.notna(v) else "—")
    event = st.dataframe(
        view[columns],
        hide_index=True,
        height=min(480, 35 * (len(view) + 1) + 3),
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "model": st.column_config.TextColumn("MODEL", width="medium",
                                                 pinned=True),
            "tier": st.column_config.TextColumn("TIER", width="small"),
            axis_col: st.column_config.TextColumn(
                axis_label[axis_col], width="small", alignment="right"),
            "speed": st.column_config.TextColumn(
                "TOK/S", width="small", alignment="right",
                help="Median output tokens/sec (Artificial Analysis)"),
            "usage_b": st.column_config.TextColumn(
                "USE B/D", width="small", alignment="right",
                help="Billions of tokens/day routed through OpenRouter, "
                     "7-day average — real traffic, i.e. popularity, "
                     "not quality. Blank = outside OpenRouter's daily "
                     "top 50."),
            "total_disp": st.column_config.TextColumn("TOTAL", width="small"),
            "fit": st.column_config.ProgressColumn(
                "FIT", format="%.0f", min_value=0, max_value=100, width="small",
                help="Weighted SMART/CHEAP/FAST score from the sidebar priorities"),
            "in_per_m": st.column_config.NumberColumn(
                "IN /1M", format=f"{unit}%.2f", width="small"),
            "out_per_m": st.column_config.NumberColumn(
                "OUT /1M", format=f"{unit}%.2f", width="small"),
        },
    )
    rows = event.selection.rows
    return rows[0] if rows else None


def detail_card(row: pd.Series, currency: str, fx: float):
    """Full rate card for the model selected in the table."""
    with st.container(border=True):
        line = st.container(horizontal=True, gap="small")
        with line:
            st.markdown(f"**{row['model']}** · {row['maker']}")
            if row["tier"] != "—":
                st.badge(row["tier"], color="blue")
            for flag, label in [("reasoning", "REASONING"), ("vision", "VISION"),
                                ("tools", "TOOLS"), ("pdf", "PDF")]:
                if row[flag]:
                    st.badge(label, color="gray")
            if row["deprecates"]:
                st.badge(f"DEPRECATES {row['deprecates']}", color="red")

        def rate(x):
            return md_money(x, currency, fx) if x else "—"

        batch = (
            f"{rate(row['batch_in_per_m'])}/{rate(row['batch_out_per_m'])}"
            if row["batch_in_per_m"] else "—"
        )
        score_bits = [f"{label} {row[col]:.1f}"
                      for label, col in [("INT", "intelligence"),
                                         ("CODE", "coding"),
                                         ("AGENT", "agentic")]
                      if pd.notna(row[col])]
        perf_bits = []
        if pd.notna(row["speed"]):
            perf_bits.append(f"{row['speed']:.0f} TOK/S")
        if pd.notna(row["ttft"]):
            perf_bits.append(f"TTFT {row['ttft']:.2f}S")
        if pd.notna(row["usage"]):
            perf_bits.append(f"{row['usage'] / 1e9:.0f}B TOK/DAY ROUTED")
        st.caption(
            f"{' · '.join(score_bits) or 'UNSCORED'}"
            + (f" · {' · '.join(perf_bits)}" if perf_bits else "")
            + f" · IN {rate(row['in_per_m'])}/1M · OUT {rate(row['out_per_m'])}/1M · "
            f"CACHE RD {rate(row['cache_rd_per_m'])} · CACHE WR {rate(row['cache_wr_per_m'])} · "
            f"BATCH {batch} · CTX {row['ctx']} · KEY `{row['key']}`"
        )


# =============================================================================
# Section 8: Main
# =============================================================================


def applied_chips(p: dict, f: dict, mode: str, opt_label: str, query: str,
                  n_models: int, fx: float):
    """What is currently shaping every number on the page, as chips. Blue =
    the workload, violet = the mode's own question, gray = modifiers."""
    # The workload chip reads as a sentence: how many calls, then what one call
    # looks like. The token counts are per call, and an "×" between two figures
    # invites reading them as a total.
    chips = [("blue", f"{p['api_calls']:,} CALLS · ~{p['input_tokens']:,} IN / "
                      f"{p['output_tokens']:,} OUT TOKENS EACH")]
    if p["cache_hit_pct"]:
        chips.append(("gray", f"CACHE HIT {p['cache_hit_pct']}%"))
    if p["reasoning_mult"] > 1:
        chips.append(("gray", f"REASONING OUT ×{p['reasoning_mult']:g}"))
    if p["batch"]:
        chips.append(("gray", "BATCH"))
    if mode == "RECOMMEND":
        chips.append(("gray", f"OPTIMIZE {opt_label}"))
        # Catalog scope is part of the verdict's claim, so it is stated
        # whenever the field the ranking sees is not the whole scored one.
        if len(f["sel_makers"]) < f["n_makers"]:
            chips.append(("gray", f"{len(f['sel_makers'])} OF "
                                  f"{f['n_makers']} PROVIDERS"))
        if f["caps"]:
            chips.append(("gray", " + ".join(f["caps"])))
    elif mode == "MATCH" and f["anchor"]:
        chips.append(("violet",
                      f"ANCHOR {f['anchor']} −{f['tolerance']} PTS ({f['axis']})"))
    elif mode == "LOOK UP" and query:
        chips.append(("violet", f"SEARCH \"{query}\""))
    if p["currency"] == "INR":
        chips.append(("gray", f"FX USD→INR {fx:.2f}"))
    chips.append(("gray", f"{n_models} MODELS"))
    st.markdown(" ".join(f":{color}-badge[{text}]" for color, text in chips))


def empty_view(mode: str, f: dict, query: str):
    """Why the view is empty, in the vocabulary of the mode that emptied it."""
    if mode == "LOOK UP":
        st.info(f"No model, maker, or key matches \"{query}\" — the search "
                "covers the full catalog, including unscored models.")
    elif mode == "MATCH":
        st.info(f"Nothing scores within {f['tolerance']} pts of "
                f"{f['anchor']} — widen MATCH WITHIN.")
    elif not f["sel_makers"]:
        st.info("No providers selected — pick at least one PROVIDERS pill "
                "under REFINE.")
    elif not f["sel_tiers"]:
        st.info("No tiers selected — pick at least one TIER pill under REFINE.")
    else:
        st.info("No models match the current filters — widen the tiers, "
                "providers, or capabilities under REFINE.")


def main():
    seed_defaults()
    fx = get_exchange_rate()
    strip = st.container(horizontal=True, vertical_alignment="bottom",
                         gap="medium")
    with strip:
        st.markdown("### ▮ TOKEN TARIFF")
        mode = mode_control()
    # Unscored models are LOOK UP's business alone; every other mode ranks,
    # and a model with no score cannot be ranked.
    df_catalog = load_catalog(full=mode == "LOOK UP")
    if df_catalog.empty:
        st.error("No pricing data available (fetch failed and no local fallback).")
        return

    # The mode's own controls EXECUTE here, above the shared workload strip:
    # the preset pills write their values into session state, and everything
    # they configure has to be instantiated after that lands. The strip is
    # re-entered below, so it still renders at the top of the page.
    query, opt_label = "", CUSTOM
    if mode == "RECOMMEND":
        preset_slot = preset_row()
        weights = optimize_row()
        # Preset-owned weights read as the use case, not as CUSTOM — the chip
        # has to agree with the unselected control above it.
        owner = st.session_state.get("preset")
        opt_label = (f"AS {owner}" if preset_weights(owner) == weights
                     else weights_label())
        f = refine_sidebar(df_catalog)
    elif mode == "MATCH":
        weights = tuple(carried(k) for k in WEIGHT_KEYS)
        f = match_row(df_catalog)
    else:
        weights = tuple(carried(k) for k in WEIGHT_KEYS)
        query = lookup_row()
        f = {"sel_makers": None, "sel_tiers": None, "n_makers": 0, "caps": [],
             "axis": carried("axis"), "anchor": None, "tolerance": 0}
    f["weights"] = weights
    with strip:
        p = workload_strip()
    # The workload widgets are the last controls that can move a preset value,
    # so the modified indicator is read only after they hydrate — a shared URL
    # whose workload matches the preset must not flash PRESET MODIFIED.
    if mode == "RECOMMEND":
        preset_notice(preset_slot, st.session_state.get("preset"))

    pool = (search_catalog(df_catalog, query) if query
            else apply_filters(df_catalog, f))
    # A lookup is a catalog question, so it answers for every model. RECOMMEND
    # and MATCH rank models to run this workload on, and one that cannot hold a
    # call's input is not a candidate for it.
    n_over_context = 0
    if mode != "LOOK UP":
        pool, n_over_context = fits_context(pool, p["input_tokens"])
    axis_col = AXES[f["axis"]]

    df = compute_costs(
        pool,
        p["input_tokens"], p["output_tokens"], p["api_calls"],
        p["cache_hit_pct"], p["reasoning_mult"], p["batch"],
    )
    df = add_fit(df, axis_col, f["weights"])

    if df.empty:
        empty_view(mode, f, query)
        return

    applied_chips(p, f, mode, opt_label, query, len(df), fx)
    if n_over_context:
        st.caption(context_note(n_over_context, p["input_tokens"]))
    st.divider()

    if mode == "RECOMMEND":
        pick = pick_model(df)
        if pick is not None:
            verdict(pick, df, f, opt_label, p["currency"], fx)
            alternative_cards(df, pick, f, p["currency"], fx)
    elif mode == "MATCH":
        match_verdict(df, f, p["currency"], fx)
    if mode != "LOOK UP":
        st.caption(
            "COST IS PER-TOKEN AT THE COUNTS YOU ENTER, IDENTICAL FOR EVERY MODEL "
            "— TOKENIZERS AND VERBOSITY DIFFER, SO A CHEAPER RATE CAN COST MORE "
            "PER FINISHED TASK (ESPECIALLY REASONING MODELS AT HIGH EFFORT). "
            "BENCHMARKS MAY NOT REFLECT YOUR USAGE — TEST ON YOUR OWN PROMPTS "
            "BEFORE SWITCHING"
        )
    st.space()

    if mode == "LOOK UP":
        # A lookup is a question about one model, so the table gets the full
        # width and the charts — which compare a field — sit this one out.
        selected = ledger(df, axis_col, p["currency"], fx)
        if selected is not None:
            detail_card(df.iloc[selected], p["currency"], fx)
    else:
        colors = maker_colors()
        left, right = st.columns([11, 9], gap="large")
        with left:
            selected = ledger(df, axis_col, p["currency"], fx)
            if selected is not None:
                detail_card(df.iloc[selected], p["currency"], fx)
        with right:
            frontier_tab, totals_tab = st.tabs(["FRONTIER", "TOTALS"])
            with frontier_tab:
                frontier_chart(df, f, p["currency"], fx, colors)
            with totals_tab:
                totals_chart(df, p["currency"], fx, colors)

    st.caption(
        "SCORES & SPEED: [ARTIFICIAL ANALYSIS](https://artificialanalysis.ai/) "
        "· PRICES: LITELLM · USAGE: OPENROUTER · "
        "SELECT A ROW FOR THE FULL RATE CARD · URL IS SHAREABLE · "
        "METHODOLOGY IN THE GUIDE"
    )


main()
