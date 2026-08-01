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
             OpenRouter's rankings dataset when a key is set. Pick a use-case
             preset to configure the workload in one click, weight
             SMART/CHEAP/FAST priorities for a ranked verdict, or anchor on a
             model to find cheaper equals. Every control is URL-bound, so any
             comparison is a shareable link.
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
                    cache=30, rmult=1.0, axis="INT", need_t=False,
                    tiers=["FRONTIER", "ADVANCED", "CAPABLE"],
                    w_smart=3, w_cheap=4, w_fast=3)),
    "CODING AGENT": dict(
        desc="An AI pair-programmer or autonomous coder (Claude Code, Cursor) "
             "— it re-reads a large repo context every call (high cache hits) "
             "and burns thinking tokens. Priorities: coding skill first, "
             "cost second.",
        values=dict(input_tokens=40_000, output_tokens=4_000, api_calls=200,
                    cache=80, rmult=3.0, axis="CODE", need_t=True,
                    tiers=["FRONTIER"],
                    w_smart=5, w_cheap=2, w_fast=1)),
    "AGENT": dict(
        desc="A multi-step tool-using workflow (research, browsing, "
             "operations) — long contexts carried across many steps, judged "
             "on the agentic index rather than raw chat quality. Priorities: "
             "capability first.",
        values=dict(input_tokens=25_000, output_tokens=3_000, api_calls=300,
                    cache=75, rmult=2.0, axis="AGENT", need_t=True,
                    tiers=["FRONTIER"],
                    w_smart=4, w_cheap=2, w_fast=1)),
    "SUMMARIZE": dict(
        desc="Long documents in, short summaries out, pipeline-style — "
             "big one-shot prompts with nothing worth caching. Priorities: "
             "the cheapest model that reliably reads long inputs.",
        values=dict(input_tokens=30_000, output_tokens=800, api_calls=100,
                    cache=0, rmult=1.0, axis="INT", need_t=False,
                    tiers=list(TIER_LABELS),
                    w_smart=2, w_cheap=5, w_fast=1)),
    "EXTRACTION": dict(
        desc="Pulling structured fields (JSON, entities, tables) out of short "
             "texts at volume — needs tool/schema support and consistency "
             "more than brilliance. Priorities: cheap, accurate, quick.",
        values=dict(input_tokens=4_000, output_tokens=400, api_calls=1_000,
                    cache=40, rmult=1.0, axis="INT", need_t=True,
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
    axis="INT", input_tokens=10_000, output_tokens=3_000, api_calls=100,
    cache=0, rmult=1.0, batch=False, need_r=False, need_v=False, need_t=False,
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
            st.session_state.setdefault(k, v)


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
        has_batch = df["batch_in_per_m"] > 0
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
        "**1 · PICK A USE CASE** — the pills up top (CHATBOT, CODING AGENT, "
        "…) set a typical workload shape, the right score axis, a sensible "
        "tier range, and the priority weights in one click. Each shows a "
        "description of what it models. Everything a preset sets stays "
        "editable.\n\n"
        "**2 · READ THE VERDICT** — the **▸ model** line is the "
        "recommendation. Its FIT score (0–100) blends how each model ranks "
        "in the current view on SMART (benchmark score), CHEAP (your "
        "workload's cost), and FAST (measured speed), weighted by the "
        "sidebar PRIORITIES sliders. The four cuts below — CHEAPEST, BEST "
        "VALUE, SMARTEST, FASTEST — are single-dimension pointers.\n\n"
        "**3 · SHAPE THE WORKLOAD** — the WORKLOAD popover holds tokens per "
        "call, number of calls, prompt-cache hit rate (cache math counts "
        "reads only — write premiums are a one-time cost), reasoning output "
        "multiplier, and Batch API pricing; the chips under the presets show "
        "what is currently applied. ESTIMATE FROM TEXT counts tokens from "
        "pasted samples.\n\n"
        "**4 · NARROW THE FIELD** — sidebar: providers, tiers (quartiles of "
        "the scored field — FRONTIER is the current top quarter), required "
        "capabilities, and the AXIS the scores use (general intelligence, "
        "coding, or agentic). ALL MODELS adds unscored models.\n\n"
        "**5 · ANCHOR** — pick a reference model and the view keeps only "
        "models scoring within MATCH WITHIN points of it, ranked by your "
        "workload's cost: *who matches this model's intelligence for "
        "less?*\n\n"
        "**6 · SEARCH & SHARE** — the search box finds any model across the "
        "full catalog, ignoring filters. Every control lives in the URL — "
        "copy it and the exact same comparison opens for anyone."
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
# Section 6: UI — presets, sidebar filters, top strip
# =============================================================================


def preset_row():
    """Use-case pills. Selecting one writes the preset's values into the bound
    widgets' session state — which is why this must run before the sidebar and
    workload widgets are instantiated. On a first load, values already pinned
    in the URL win over the preset so shared links reproduce exactly."""
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
            # copy list values — session state must never alias preset config
            st.session_state[k] = list(v) if isinstance(v, list) else v
    st.session_state["_preset_applied"] = sel
    if sel:
        st.caption(PRESETS[sel]["desc"])


def sidebar_filters() -> Tuple[pd.DataFrame, dict]:
    """Sidebar: catalog scope, provider/tier/capability filters, axis,
    priorities, anchor.

    The catalog is loaded right after the scope toggle, so the provider pills
    and anchor options always reflect the active catalog.
    """
    with st.sidebar:
        full = st.toggle("ALL MODELS", key="all", bind="query-params",
                         help="Include models without benchmark scores. The default view shows only models that have both a price and an Artificial Analysis score.")
        df_catalog = load_catalog(full=full)
        if df_catalog.empty:
            return df_catalog, {}

        makers = sorted(df_catalog["maker"].unique(), key=str.lower)
        # Seed the selection unless the URL carries one; URL-restored values
        # may reference makers absent from the active catalog scope — drop
        # those before the widget renders.
        if "prov" not in st.query_params:
            st.session_state.setdefault(
                "prov", [m for m in DEFAULT_MAKERS if m in makers] or makers)
        if "prov" in st.session_state:
            st.session_state.prov = [
                m for m in st.session_state.prov if m in makers]
        sel_makers = st.pills(
            "PROVIDERS", makers, selection_mode="multi",
            key="prov", bind="query-params",
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
                 "FRONTIER is the top quarter of the current field. "
                 "Narrowing tiers hides unscored models.",
        )

        axis = st.segmented_control(
            "AXIS", list(AXES),
            key="axis", bind="query-params",
            help="Which score drives the verdict, anchor, chart, and score "
                 "column: general intelligence, coding, or agentic.",
        )

        st.caption("PRIORITIES",
                   help="Weights for the FIT score behind the verdict: how much "
                        "the recommendation should care about the score axis, "
                        "the workload cost, and output speed.")
        w_smart = st.slider("SMART", 0, 5, key="w_smart", bind="query-params")
        w_cheap = st.slider("CHEAP", 0, 5, key="w_cheap", bind="query-params")
        w_fast = st.slider("FAST", 0, 5, key="w_fast", bind="query-params")

        scored_models = sorted(df_catalog.dropna(subset=["intelligence"])["model"])
        anchor = st.selectbox(
            "ANCHOR MODEL", scored_models, index=None,
            placeholder="MATCH INTELLIGENCE OF ...",
            key="anchor", bind="query-params",
            help="Keep only models scoring at least as high as this one "
                 "(minus the tolerance), ranked by your workload's cost.",
        )
        tolerance = st.slider(
            "MATCH WITHIN", 0, 10, format="%d pts",
            key="tol", bind="query-params",
            help="How many points below the anchor's score still count as equal.",
        ) if anchor else 0

        st.caption("CAPABILITIES")
        need_reasoning = st.toggle("REASONING", key="need_r", bind="query-params")
        need_vision = st.toggle("VISION", key="need_v", bind="query-params")
        need_tools = st.toggle("TOOLS", key="need_t", bind="query-params")

    return df_catalog, {
        "sel_makers": sel_makers,
        "sel_tiers": sel_tiers,
        "axis": axis or "INT",
        "weights": (w_smart, w_cheap, w_fast),
        "anchor": anchor,
        "tolerance": tolerance,
        "need_reasoning": need_reasoning,
        "need_vision": need_vision,
        "need_tools": need_tools,
    }


def top_strip() -> dict:
    """Top strip: title, search, workload editor, currency."""
    top = st.container(horizontal=True, vertical_alignment="bottom", gap="medium")
    with top:
        st.markdown("### ▮ TOKEN TARIFF")
        query = st.text_input(
            "SEARCH", key="q", bind="query-params",
            placeholder="FIND A MODEL ...", label_visibility="collapsed",
            help="Searches the whole catalog by model, maker, or litellm key — "
                 "sidebar filters are bypassed while a search is active.",
        )
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
        "query": (query or "").strip(),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "api_calls": api_calls,
        "cache_hit_pct": cache_hit_pct,
        "reasoning_mult": reasoning_mult,
        "batch": batch,
        "currency": currency or "USD",
    }


def apply_filters(df: pd.DataFrame, f: dict) -> pd.DataFrame:
    # The anchor's score is resolved against the whole catalog, before any
    # narrowing — "match the intelligence of X" must keep working when X's
    # own provider or tier is filtered out of view.
    anchor_rows = df[df["model"] == f["anchor"]] if f["anchor"] else df.iloc[:0]
    df = df[df["maker"].isin(f["sel_makers"])]
    if set(f["sel_tiers"]) != set(TIER_LABELS):
        df = df[df["tier"].isin(f["sel_tiers"])]
    for flag, col in [("need_reasoning", "reasoning"), ("need_vision", "vision"),
                      ("need_tools", "tools")]:
        if f[flag]:
            df = df[df[col]]
    if not anchor_rows.empty:
        axis_col = AXES[f["axis"]]
        if pd.notna(anchor_rows.iloc[0][axis_col]):
            floor = anchor_rows.iloc[0][axis_col] - f["tolerance"]
            df = df[df[axis_col] >= floor]
    return df


def search_catalog(query: str) -> pd.DataFrame:
    """Name/maker/key lookup across the full catalog, ignoring filters — the
    'is model X in here and what does it cost' path."""
    base = load_catalog(full=True)
    q = query.lower()
    mask = (base["model"].str.lower().str.contains(q, regex=False)
            | base["maker"].str.lower().str.contains(q, regex=False)
            | base["key"].str.lower().str.contains(q, regex=False))
    return base[mask]


# =============================================================================
# Section 7: UI — results
# =============================================================================


def hero(df: pd.DataFrame, f: dict, currency: str, fx: float):
    """The verdict: one recommended model and the reason, as the page's lead."""
    axis_col = AXES[f["axis"]]
    scored = df.dropna(subset=[axis_col])

    if f["anchor"]:
        if scored.empty:
            return
        winner = scored.iloc[0]  # cheapest at/above the anchor floor
        st.markdown(f"## ▸ {winner['model']}")
        anchor_rows = df[df["model"] == f["anchor"]]
        if anchor_rows.empty:
            # The anchor set the score floor but is itself filtered out of
            # view, so there is no anchor cost to compare against.
            st.markdown(
                f"**VERDICT** · Matches **{f['anchor']}** within "
                f"{f['tolerance']} pts on {f['axis']} at "
                f"**{md_money(winner['total_usd'], currency, fx)}** — "
                f"{f['anchor']} itself is outside the current filters."
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
        return

    if df["fit"].notna().any():
        pick = df.loc[df["fit"].idxmax()]
        w_smart, w_cheap, w_fast = f["weights"]
        why = f"Best fit for SMART {w_smart} · CHEAP {w_cheap} · FAST {w_fast}"
    else:  # all priority weights at zero
        pick = best_value(df)
        why = "Best value in view (set PRIORITIES for a weighted pick)"
    if pick is None:
        return

    st.markdown(f"## ▸ {pick['model']}")
    bits = [why]
    if pd.notna(pick["fit"]):
        bits[0] += f" — FIT {pick['fit']:.0f}/100"
    bits.append(pick["tier"] if pick["tier"] != "—" else "UNSCORED")
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


def quick_chips(df: pd.DataFrame, axis_col: str, currency: str, fx: float):
    """Secondary strip of named cuts under the hero — pointers, not the lead."""
    cheapest = df.iloc[0]
    bv = best_value(df)
    scored = df.dropna(subset=[axis_col])
    fast = df.dropna(subset=["speed"])
    chips = [
        ("CHEAPEST", md_money(cheapest["total_usd"], currency, fx),
         cheapest["model"], None),
        ("BEST VALUE",
         md_money(bv["total_usd"], currency, fx) if bv is not None else "—",
         f"{bv['model']} · {bv['tier']}" if bv is not None else "NO SCORED MODELS",
         "Cheapest model in the highest tier present in the current view."),
        ("SMARTEST",
         f"{scored[axis_col].max():.1f}" if not scored.empty else "—",
         scored.loc[scored[axis_col].idxmax(), "model"] if not scored.empty else "—",
         None),
        ("FASTEST",
         f"{fast['speed'].max():.0f} TOK/S" if not fast.empty else "—",
         fast.loc[fast["speed"].idxmax(), "model"] if not fast.empty
         else "SET AA_API_KEY FOR SPEED DATA",
         "Median output tokens per second, measured by Artificial Analysis."),
    ]
    for col, (label, value, sub, tip) in zip(st.columns(4), chips):
        with col:
            st.caption(label, help=tip)
            st.markdown(f"#### {value}")
            st.caption(sub)


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
    event = st.dataframe(
        view[columns],
        hide_index=True,
        height=min(480, 35 * (len(view) + 1) + 3),
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "model": st.column_config.TextColumn("MODEL", width="medium"),
            "tier": st.column_config.TextColumn("TIER", width="small"),
            axis_col: st.column_config.NumberColumn(
                axis_label[axis_col], format="%.1f", width="small"),
            "speed": st.column_config.NumberColumn(
                "TOK/S", format="%.0f", width="small",
                help="Median output tokens/sec (Artificial Analysis)"),
            "usage_b": st.column_config.NumberColumn(
                "USE B/D", format="%.0f", width="small",
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


def main():
    seed_defaults()
    fx = get_exchange_rate()
    head = st.container()  # rendered above the preset row, filled after it —
    # the preset pills must EXECUTE first so their session-state writes land
    # before the sidebar and workload widgets they configure are instantiated.
    preset_row()
    df_catalog, f = sidebar_filters()
    if df_catalog.empty:
        st.error("No pricing data available (fetch failed and no local fallback).")
        return
    with head:
        p = top_strip()

    searching = bool(p["query"])
    if searching:
        pool = search_catalog(p["query"])
        f = {**f, "anchor": None}  # a lookup, not a comparison — no anchor
    else:
        pool = apply_filters(df_catalog, f)
    axis_col = AXES[f["axis"]]

    df = compute_costs(
        pool,
        p["input_tokens"], p["output_tokens"], p["api_calls"],
        p["cache_hit_pct"], p["reasoning_mult"], p["batch"],
    )
    df = add_fit(df, axis_col, f["weights"])

    if df.empty:
        if searching:
            st.info(f"No model, maker, or key matches \"{p['query']}\" — "
                    "the search covers the full catalog, including unscored models.")
        elif not f["sel_makers"]:
            st.info("No providers selected — pick at least one PROVIDERS pill "
                    "in the sidebar.")
        elif not f["sel_tiers"]:
            st.info("No tiers selected — pick at least one TIER pill in the sidebar.")
        else:
            st.info("No models match the current filters — widen the tiers, "
                    "providers, or capabilities, or clear the anchor.")
        return

    # The applied-settings strip: what is currently shaping every number on
    # the page, as chips. Blue = the workload, violet = a view rewrite
    # (search/anchor), gray = modifiers. Edit them in WORKLOAD / the sidebar.
    chips = [("blue", f"{p['input_tokens']:,} IN / {p['output_tokens']:,} OUT "
                      f"× {p['api_calls']:,} CALLS")]
    if p["cache_hit_pct"]:
        chips.append(("gray", f"CACHE HIT {p['cache_hit_pct']}%"))
    if p["reasoning_mult"] > 1:
        chips.append(("gray", f"REASONING OUT ×{p['reasoning_mult']:g}"))
    if p["batch"]:
        chips.append(("gray", "BATCH"))
    if searching:
        chips.append(("violet", f"SEARCH \"{p['query']}\" — FILTERS BYPASSED"))
    elif f["anchor"]:
        chips.append(("violet",
                      f"ANCHOR {f['anchor']} −{f['tolerance']} PTS ({f['axis']})"))
    if p["currency"] == "INR":
        chips.append(("gray", f"FX USD→INR {fx:.2f}"))
    chips.append(("gray", f"{len(df)} MODELS"))
    st.markdown(" ".join(f":{color}-badge[{text}]" for color, text in chips))
    st.divider()

    hero(df, f, p["currency"], fx)
    st.caption(
        "COST IS PER-TOKEN AT THE COUNTS YOU ENTER, IDENTICAL FOR EVERY MODEL "
        "— TOKENIZERS AND VERBOSITY DIFFER, SO A CHEAPER RATE CAN COST MORE "
        "PER FINISHED TASK (ESPECIALLY REASONING MODELS AT HIGH EFFORT). "
        "BENCHMARKS MAY NOT REFLECT YOUR USAGE — TEST ON YOUR OWN PROMPTS "
        "BEFORE SWITCHING"
    )
    quick_chips(df, axis_col, p["currency"], fx)
    st.space()

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
