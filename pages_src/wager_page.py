"""
THE TRICKLE-DOWN WAGER — how long the frontier stays the frontier.

Frontier intelligence keeps arriving at the bottom of every vendor's lineup a
few months later, at a fraction of the price. This page shows that history from
sourced data, then stakes a falsifiable claim on the next repetition: by when
will a lineup-bottom model match Claude Fable 5?

The arithmetic lives in wager.py and runs against timeline.csv, so the numbers
here move when the data does. wager.json holds the frozen prediction the
scheduled email was built around; the page flags any drift from it.
"""

# =============================================================================
# Section 1: Imports and configuration
# =============================================================================
import datetime as dt
import math
import pathlib
import sys

import pandas as pd
import plotly.express as px
import streamlit as st

# `streamlit run app.py` puts the repo root on the path, but a test harness or
# a direct run of this file does not — and wager.py lives at the root.
ROOT = str(pathlib.Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import wager  # noqa: E402

st.set_page_config(page_title="WAGER — TOKEN TARIFF", page_icon="▮",
                   layout="wide")

# Two series, two jobs: where the frontier is, and where the cheap seats are.
# Both hues come from the app-wide theme palette so the page reads as part of
# the same ledger.
TIER_LABELS = {"frontier": "FRONTIER", "bottom": "LINEUP BOTTOM"}
TIER_ORDER = ["FRONTIER", "LINEUP BOTTOM"]

# The two things a model can be measured on, one axis at a time. METR counts
# minutes of autonomous work and spans six orders of magnitude, so it reads on
# a log axis; the AA index is a bounded score and reads linear.
YARDSTICKS = {
    "METR HORIZON": dict(
        col="metr_horizon_min_p50", log=True, title="50% TIME HORIZON (MIN, LOG)",
        help="Task length at which a model succeeds half the time, measured by "
             "METR. Blank for every model METR has not run — including every "
             "bottom-tier model there has ever been."),
    "AA INDEX": dict(
        col="aa_intel", log=False, title="ARTIFICIAL ANALYSIS INTELLIGENCE INDEX",
        help="Artificial Analysis' intelligence index, read from a single "
             "snapshot so models from different eras are on one scale."),
}

METR_URL = "https://metr.org/time-horizons/"
# The doubling times quoted on this page are TH1.1's, so they cite the TH1.1
# write-up rather than the landing page, which publishes none.
METR_TH11_URL = "https://metr.org/blog/2026-1-29-time-horizon-1-1/"
EPOCH_URL = "https://epoch.ai/data-insights/llm-inference-price-trends"
AA_URL = "https://artificialanalysis.ai/"
HAN_URL = "https://www.youtube.com/watch?v=uIiA6DquRiE"
CAMERON_URL = "https://www.youtube.com/watch?v=sRpqPgKeXNk"
O1_URL = ("https://web.archive.org/web/20260729212647/"
          "https://openai.com/index/learning-to-reason-with-llms/")
# OpenAI's own GPT-5.6 post, archived with the price-cut update banner on it.
# The trade coverage is the secondary source; the vendor's own page is primary.
LUNA_URL = ("https://web.archive.org/web/20260801002141/"
            "https://openai.com/index/gpt-5-6/")
LUNA_PRESS_URL = "https://www.cnbc.com/2026/07/30/open-ai-price-cut-gpt.html"
TOKENIZER_URL = "https://platform.claude.com/docs/en/about-claude/pricing"
REPO_URL = "https://github.com/Prajwalsrinvas/token-tariff"


# =============================================================================
# Section 2: Data
# =============================================================================


@st.cache_data
def load() -> tuple:
    """The timeline, the derived wager, and the frozen prediction it shipped
    with. Cached without a TTL — all three are committed files, so they only
    change on a refresh commit."""
    rows = wager.load_timeline()
    return (rows, wager.milestones(rows), wager.predictions(rows),
            wager.resolution(rows), wager.load_wager())


def _days(target: dt.date) -> int:
    return (target - dt.date.today()).days


def _countdown(target: dt.date) -> str:
    d = _days(target)
    if d < 0:
        return f"{abs(d):,} DAYS AGO"
    return f"IN {d:,} DAYS · {d / (365.2425 / 12):.1f} MONTHS"


def timeline_frame(rows: list) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["tier_label"] = df["tier"].map(TIER_LABELS)
    df["date"] = pd.to_datetime(df["release_date"])
    return df


# =============================================================================
# Section 3: UI — the wager
# =============================================================================


def banner(preds: dict, res: dict, frozen: dict):
    """The claim, the two dates, and where the wager stands — the page's lead.

    The claim sentence is rendered from wager.json rather than written here, so
    the page and the frozen wager cannot drift into saying different things.
    """
    st.markdown("## ▸ THE TRICKLE-DOWN WAGER")
    st.markdown(f"**{frozen['claim']}**")
    st.caption(frozen["framing"].upper())

    a, b, slow = preds["a"], preds["b"], preds["slow"]
    cards = [
        ("METHOD B · PRICE DECLINE", b["date"],
         f"Epoch's median {b['rate']:g}× / year",
         "The wager's price term is a ratio, so this is just the time for the "
         "cost of a fixed capability to fall tenfold — independent of either "
         "sticker price. The clock starts at Fable 5's release."),
        ("METHOD A · HISTORICAL LAG", a["date"],
         f"Median {a['median_lag_months']:.1f} mo over {a['n_pairs']} pairs",
         f"Median lag from a frontier model setting a new high on the index to "
         f"the first bottom-tier model reaching it, added to Fable 5's release. "
         f"The {a['n_pairs']} pairs come from {a['n_matchers']} catch-up "
         f"releases, so the effective sample is {a['n_matchers']}."),
        ("SLOWEST HISTORICAL TREND", slow["date"],
         f"Epoch's slowest {slow['rate']:g}× / year",
         "Method B run at the slowest decline Epoch fitted across the "
         "benchmarks it tracks. A slower trend than anything measured — not a "
         "bound, and nothing says the future stays inside it."),
    ]
    for col, (label, date, sub, tip) in zip(st.columns(3), cards):
        with col:
            st.caption(label, help=tip)
            st.markdown(f"#### {date:%Y-%m-%d}")
            st.caption(f"{_countdown(date)} · {sub.upper()}")

    st.space()
    status = ("RESOLVED YES" if res["resolved"] else "OPEN")
    chips = [
        ("green" if res["resolved"] else "blue", status),
        ("gray", f"BASELINE {res['baseline']} · AA {res['baseline_aa']:.1f} · "
                 f"\\${res['baseline_price']:,.2f}/MTOK BLENDED"),
        ("gray", f"CLOSEST {res['best_bottom']} · AA {res['best_bottom_aa']:.1f} · "
                 f"{res['gap_points']:.1f} POINTS SHORT"),
        ("blue", "MIDPOINT CHECK · " + next(
            x["due"] for x in frozen["sends"] if x["id"] == "midpoint-check")),
        ("gray", f"AA FEEDS · OPENROUTER {wager.SNAPSHOT_DATE} · "
                 f"AA API ≤{wager.AA_API_VINTAGE}"),
    ]
    if str(preds["a"]["date"]) != frozen["predictions"]["method_a"]["date"] or \
            str(preds["b"]["date"]) != frozen["predictions"]["method_b"]["date"]:
        chips.append(("violet", "LIVE DATA HAS MOVED SINCE THE WAGER WAS FROZEN"))
    st.markdown(" ".join(f":{c}-badge[{t}]" for c, t in chips))


def terms(res: dict, frozen: dict):
    """Resolution terms — what would settle this, spelled out before the
    evidence, so the claim can be argued with rather than admired."""
    with st.expander("RESOLUTION TERMS — WHAT WOULD SETTLE THIS"):
        st.markdown(
            f"Resolves **YES** on the earlier of two conditions.\n\n"
            f"**Arm 1 — METR.** [METR]({METR_URL}) measures any lineup-bottom "
            f"model at or above Fable 5's 50% time horizon.\n\n"
            f"**Arm 2 — Artificial Analysis.** A lineup-bottom model reaches "
            f"Fable 5's launch index of **{res['baseline_aa']:.1f}**, compared "
            f"inside a single AA snapshot, at no more than **one tenth** of "
            f"Fable 5's cost per token "
            f"(≤ \\${res['price_cap']:,.2f}/MTok blended, against Fable 5's "
            f"\\${res['baseline_price']:,.2f}).\n\n"
            f"**Lineup bottom** means the cheapest model a vendor ships in its "
            f"current lineup — Claude Haiku, OpenAI's mini / nano / Luna slot, "
            f"Gemini Flash-Lite. Membership is lineup position; price is data, "
            f"not the qualification.\n\n"
            f"**Arm 1 cannot currently resolve.** METR has published a horizon "
            f"for **{res['metr_measurable']}** bottom-tier models — none, in "
            f"either suite version. Fable 5 has no published horizon either; "
            f"`{res['metr_proxy']}`, an early preview of what Anthropic "
            f"describes as the same underlying model, stands in provisionally "
            f"at **{res['metr_target_min']:,.0f} min**. Arm 2 is the instrument "
            f"that can actually be read today.\n\n"
            f"**Arm 2 is a joint event.** "
            f"{frozen['resolution']['joint_event_note']}"
        )
        st.caption("RESOLUTION CHECKLIST")
        for i, step in enumerate(frozen["resolution"]["checklist"], 1):
            st.caption(f"{i}. {step}")


# =============================================================================
# Section 4: UI — the evidence
# =============================================================================


def _axis_y(value: float, log: bool) -> float:
    """Shapes and annotations are positioned in the axis' own coordinates, and
    a log axis' coordinates are exponents. Plotly does not convert for us: pass
    a raw 60 to a log axis and the label lands at 10^60, off the top of the
    plot, taking the layout with it."""
    return math.log10(value) if log else value


def capability_chart(df: pd.DataFrame, yardstick: str, colors: dict):
    """Frontier and bottom tier over time on one axis, with the three moments
    that shaped the trend called out."""
    spec = YARDSTICKS[yardstick]
    plot = df.dropna(subset=[spec["col"]]).sort_values("date")
    if plot.empty:
        st.info(f"No {yardstick} coverage in the timeline.")
        return

    fig = px.scatter(
        plot, x="date", y=spec["col"], color="tier_label",
        hover_name="model", log_y=spec["log"], color_discrete_map=colors,
        category_orders={"tier_label": TIER_ORDER},
        custom_data=["model", "vendor"],
    )
    fig.update_traces(
        marker=dict(size=9),
        hovertemplate="%{customdata[0]} · %{customdata[1]}<br>"
                      "%{x|%Y-%m-%d} · %{y:.4g}<extra></extra>",
    )

    # The line is the running best within a tier, drawn as a step. Joining the
    # releases in date order instead would slope downward every time a vendor
    # shipped something below the standing best — Gemini 3.5 Flash-Lite landing
    # after Luna reads as the cheap tier getting worse, which is not what
    # happened. A step says "this is what you could buy", which is the claim.
    for label in TIER_ORDER:
        tier = plot[plot["tier_label"] == label]
        if tier.empty:
            continue
        fig.add_scatter(
            x=tier["date"], y=tier[spec["col"]].cummax(), mode="lines",
            line=dict(color=colors[label], width=2, shape="hv"),
            name=label, hoverinfo="skip", showlegend=False,
        )

    # Before reasoning: GPT-4 to o1-preview, the stretch Daniel Han calls the
    # intelligence plateau. Shaded rather than annotated — it is a period, not
    # a point.
    fig.add_vrect(
        x0="2023-03-14", x1="2024-09-12", line_width=0, fillcolor="#FFFFFF",
        opacity=0.04, annotation_text="BEFORE REASONING",
        annotation_position="top left",
        annotation_font=dict(size=9, color="#98A6B3"),
    )

    # Han's counterfactual: without test-time compute, capability tops out
    # around Claude 3.7 Sonnet. Drawn at 3.7 Sonnet's own value on whichever
    # yardstick is showing.
    ceiling = plot.loc[plot["model"] == "claude-3-7-sonnet", spec["col"]]
    if not ceiling.empty:
        # add_hline feeds one y to both its shape and its label, but on a log
        # axis the two want different coordinates: shapes take raw data values
        # (Plotly log-transforms them), annotations take exponents. Drawn
        # separately so each gets its own convention.
        level = float(ceiling.iloc[0])
        fig.add_shape(
            type="line", xref="x domain", x0=0, x1=1, y0=level, y1=level,
            line=dict(color="#98A6B3", width=1, dash="dash"),
        )
        fig.add_annotation(
            xref="x domain", x=0, xanchor="left",
            y=_axis_y(level, spec["log"]), yanchor="bottom",
            text="THE PLATEAU THAT DIDN'T HAPPEN — HAN'S CEILING",
            showarrow=False, font=dict(size=9, color="#98A6B3"),
        )

    # Both labels are anchored leftward into empty plot: centred, o1-preview's
    # runs into the rising frontier step and Luna's runs off the right edge.
    for model, text, anchor, ax, ay in [
        ("o1-preview", "o1-preview — TEST-TIME COMPUTE", "right", -8, -30),
        ("gpt-5.6-luna", "LUNA — 80% PRICE CUT, 3 WEEKS IN", "right", -12, -30),
    ]:
        point = plot[plot["model"] == model]
        if point.empty:
            continue
        fig.add_annotation(
            x=point.iloc[0]["date"],
            y=_axis_y(float(point.iloc[0][spec["col"]]), spec["log"]), text=text,
            showarrow=True, arrowhead=0, arrowwidth=1, arrowcolor="#98A6B3",
            ax=ax, ay=ay, xanchor=anchor,
            font=dict(size=9, color=st.get_option("theme.textColor")),
        )

    fig.update_layout(
        height=460, margin=dict(l=0, r=0, t=8, b=0),
        xaxis_title=None, yaxis_title=spec["title"],
        legend=dict(orientation="h", y=-0.14, title=None),
        font=dict(family="JetBrains Mono, monospace", size=11),
    )
    st.plotly_chart(fig, width="stretch")
    st.caption("DOTS: INDIVIDUAL RELEASES · STEPS: THE BEST AVAILABLE IN THAT "
               "TIER AT THAT MOMENT")
    # An empty tier is the finding, not a gap in the plot — say so, or the
    # METR view reads as broken rather than as the reason arm 1 cannot resolve.
    missing = [label for tier, label in TIER_LABELS.items()
               if plot[plot["tier"] == tier].empty]
    if missing:
        st.caption(
            f"NO {' OR '.join(missing)} MODEL HAS EVER BEEN MEASURED ON THIS "
            f"YARDSTICK — THAT ABSENCE IS WHY THE WAGER RESOLVES ON THE AA INDEX"
        )
    st.caption(spec["help"].upper())


def lag_table(ms: list):
    """Every frontier high-water mark and the first bottom-tier model to reach
    it. Open rows are the wager's neighbourhood."""
    view = pd.DataFrame([{
        "frontier": m["frontier"],
        "released": m["frontier_date"],
        "aa": m["frontier_aa"],
        "matched_by": m["matched_by"] or "— OPEN —",
        "matched": m["matched_date"],
        "matched_aa": m["matched_aa"] if m["matched_by"] else m["closest_aa"],
        "lag": m["lag_months"],
        "ratio": m["price_ratio"],
    } for m in ms])

    # An open row has no match date, lag or ratio. The data grid prints
    # missing values as a dimmed "None" whatever their dtype — NaT, NaN and
    # a Styler na_rep all render the same way — so the empty cells are made
    # empty the blunt way: formatted to strings before the grid sees them.
    def _num(v):
        return "—" if v is None or v != v else f"{float(v):.1f}"

    view["matched"] = view["matched"].map(lambda v: v or "—")
    for col in ("aa", "matched_aa", "lag", "ratio"):
        view[col] = view[col].map(_num)

    st.dataframe(
        view, hide_index=True, height=35 * (len(view) + 1) + 3,
        column_config={
            "frontier": st.column_config.TextColumn("FRONTIER", width="medium"),
            "released": st.column_config.DateColumn("RELEASED", width="small"),
            "aa": st.column_config.TextColumn("AA", width="small", alignment="right"),
            "matched_by": st.column_config.TextColumn(
                "FIRST BOTTOM-TIER MATCH", width="medium",
                help="The first model at the bottom of any vendor's lineup to "
                     "reach that index, from any vendor — the trickle-down is "
                     "cross-vendor."),
            "matched": st.column_config.TextColumn("ON", width="small"),
            "matched_aa": st.column_config.TextColumn(
                "AA", width="small", alignment="right",
                help="On open rows this is the closest a bottom-tier model has "
                     "come, not a match."),
            "lag": st.column_config.TextColumn(
                "LAG (MO)", width="small", alignment="right"),
            "ratio": st.column_config.TextColumn(
                "PRICE ×", width="small", alignment="right",
                help="How many times more expensive the frontier model is than "
                     "the model that matched it, at today's published rates and "
                     "a fixed 3:1 input:output mix. Blank where a current price "
                     "could not be sourced."),
        },
    )

    # Computed, not asserted: a caption that hardcodes counts or a superlative
    # goes stale the first time a row changes, and reads as a finding while it
    # does.
    matched = [m for m in ms if m["lag_months"] is not None]
    lags = [m["lag_months"] for m in matched]
    open_rows = [m for m in ms if m["lag_months"] is None]
    matchers = {m["matched_by"] for m in matched}
    under = sum(1 for m in matched
                if m["price_ratio"] is not None
                and m["price_ratio"] < 1 / wager.COST_SHARE)
    priced = sum(1 for m in matched if m["price_ratio"] is not None)
    st.caption(
        f"{len(matched)} MATCHED PAIRS FROM {len(matchers)} CATCH-UP RELEASES · "
        f"LAGS {min(lags):.1f}–{max(lags):.1f} MONTHS · {under} OF {priced} "
        f"PRICED MATCHES CLEARED THE INDEX AT LESS THAN A TENFOLD PRICE GAP, "
        f"AND WOULD HAVE FAILED THIS WAGER'S PRICE TERM · {len(open_rows)} OPEN "
        f"ROWS NOTHING CHEAP HAS REACHED"
    )


def narrative():
    """Eight moments, each one line and one source — the argument in order."""
    st.markdown(f"""
**2023-03 · The frontier is four minutes.** GPT-4 lands at
\\$30/\\$60 per MTok and completes tasks that take a human about four minutes,
half the time ([METR]({METR_URL})).

**2023-03 → 2024-09 · The plateau.** For about a year the curve flattens: GPT-4o
is faster and cheaper but never sets a new high on the index. Daniel Han:
*"for one year the models kind of plateaued … I call this the intelligence
plateau"* ([talk]({HAN_URL})).

**2024-07 · Distillation arrives early.** GPT-4o mini ships at \\$0.15/\\$0.60 —
about 140× cheaper than GPT-4's launch price on this page's 3:1 blend
(\\$37.50 → \\$0.26 per MTok) — and scores 6.9 against GPT-4's 7.0. It misses by
a tenth of a point, sixteen months in.

**2024-09 · The slope changes.** o1-preview is trained to spend compute at
inference: *"the performance of o1 consistently improves with … more time spent
thinking"* ([OpenAI]({O1_URL})). METR's doubling time since 2024 is 89 days
against 187.8 days across the whole record — both figures from the TH1.1 suite
([METR]({METR_TH11_URL})).

**2024-11 · The first clean catch-up.** Claude 3.5 Haiku reaches 12.3, clearing
both GPT-4 (20 months earlier) and Claude 3 Opus (8 months earlier) at about a
nineteenth of Opus's price.

**2025-10 · Haiku takes o1.** Claude Haiku 4.5 reaches 29.6 and clears o1's 23.4
ten months later, at a thirteenth of the price — the reasoning frontier of
December 2024, at bottom-tier rates.

**2026-03 · The lag shortens.** GPT-5.4 nano clears GPT-5's index in seven
months and o3's in eleven, at a seventh of GPT-5's price — three standing
frontier highs taken by one \\$0.20/\\$1.25 release.

**2026-07 · The price war.** Luna launches at \\$1/\\$6 and is cut 80% to
\\$0.20/\\$1.20 three weeks later ([OpenAI]({LUNA_URL}), [CNBC]({LUNA_PRESS_URL}));
Opus 5 ships at Opus 4.8's price while scoring above Fable 5. Luna clears Opus
4.6 five months after it shipped — the shortest lag in the table — and the
highest-scoring model at the bottom of OpenAI's lineup now scores 51.2,
**8.7 points** short of the frontier it is chasing.
""")


def methodology(preds: dict, res: dict):
    """The caveats that decide whether any of the above means anything."""
    a, b = preds["a"], preds["b"]
    with st.expander("METHODOLOGY & CAVEATS"):
        st.markdown(f"""
**50% is not 80%.** METR's headline horizon is the task length a model clears
half the time. The Mythos preview measures **1,044.8 min at 50% but 185.9 min at
80%** — a 5.6× difference. A model that has "matched" at 50% has not matched at
80%, and the wager is written on the 50% figure because that is what METR
publishes per model.

**METR cannot resolve this wager yet.** METR has measured no bottom-tier model
in either suite — no Haiku, no Flash, no Flash-Lite, no Luna, no nano. The only
"mini" entries are GPT-4o mini (release date only, no horizon) and o4-mini. The
timeline's METR column is therefore frontier-only, and the lag table runs on the
AA index by necessity, not preference.

**Two feeds, two vintages.** Artificial Analysis publishes no index-version tag
in either feed this repo reads, and it re-scores old models when the index
changes — so a 2024 score read today is not the score that was published in
2024. Scores come from two feeds of different ages: OpenRouter's listing, read
**{wager.SNAPSHOT_DATE}**, and this repo's committed AA API payload, which
predates GPT-5.6 and Opus 5 and is dated no later than
**{wager.AA_API_VINTAGE}**. Each row's `aa_version` says which it was read at.
The AA payload covers the models OpenRouter has since delisted, which is the
only way to put GPT-4 and Fable 5 on one axis; the comparison the wager turns
on — Fable 5 at 59.9 against Luna at 51.2 — sits entirely inside the fresh
OpenRouter feed. `data/history/` is append-only so a future version change is
visible rather than silent.

**One configuration rule, applied to every row.** Models that publish several
configurations — thinking and non-thinking, reasoning and not, adaptive — are
recorded at their **highest-scoring published configuration**, consistently.
Picking per row would let the choice of configuration decide which releases
count as milestones.

**METR suite versions do not mix.** All horizon figures are METR-Horizon-v1.1.
The same model scores differently under v1.0 (GPT-4: 4.0 min under 1.1, 6.0
under 1.0), so mixing them would manufacture progress.

**Method A** takes the median of {a['n_pairs']} matched lags
({a['median_lag_months']:.1f} months; mean {a['mean_lag_months']:.1f}) rather
than fitting a trend. The lags are shrinking, so a fitted trend would predict
sooner — median is the conservative reading, and with one pair more than twice
any other it is also the robust one.

**The sample is smaller than the pair count.** Those {a['n_pairs']} pairs are
produced by **{a['n_matchers']} catch-up releases**: one cheap model that clears
three standing frontier highs at once contributes three pairs and one piece of
evidence. Treat the effective sample as {a['n_matchers']}, not {a['n_pairs']}.

**Method B** uses Epoch AI's finding that the price of a fixed level of
benchmark performance falls **9× to 900× per year, median 50×**
([Epoch]({EPOCH_URL})). Because the wager's price term is a ratio — one tenth of
the baseline's cost — the answer is just the time for a tenfold fall, and does
not depend on the input:output mix or on either price. At the median rate that
is {b['years']:.2f} years, counted from Fable 5's release rather than from the
day this page read the feeds: what is falling is the price of Fable-5-level
capability, and it started falling when that capability first existed.

**Neither method models the thing the wager asks.** Arm 2 needs capability and
price *together*. Method A tracks only when the index gets matched; Method B
only how fast price falls. They are not two independent readings that happen to
agree — capability diffusion and price decline are two views of the same
process, so the dates landing near each other is not corroboration. And the
conjunction bites: of the {a['n_priced']} historical matches where both prices
are known, **{a['n_under_price_bar']}** cleared the index at less than a tenfold
price gap, and would have failed this wager's price term on the day they
matched.

**Two illustrative scenarios, not a forecast.** Each takes one published trend
at face value and runs it forward. Neither is calibrated, neither carries an
interval, and neither is good to better than a season.

**Sticker price is not cost per task.** George Cameron of Artificial Analysis:
*"you're paying for the cost per token but then you're also paying for how
verbose the models are … you need to … measure it not just by the cost per
million tokens but also considering how many reasoning tokens there are"*
([talk]({CAMERON_URL})). The PRICE × column is a fixed 3:1 input:output blend of
today's published rates — a ruler for comparing two models, not an estimate of
what either costs to run. Anthropic also puts its 4.7-and-later tokenizer at
*"approximately 30% more tokens for the same text"*, with the exact increase
depending on the content ([Anthropic]({TOKENIZER_URL})) — which per-token rates
do not capture.

**Blanks are blanks.** Every row in `timeline.csv` carries a source URL, and a
fact that could not be sourced is left empty rather than estimated — which is
why some launch prices, and the price ratios that depend on them, are missing.
""")


# =============================================================================
# Section 5: Main
# =============================================================================


def main():
    rows, ms, preds, res, frozen = load()
    df = timeline_frame(rows)

    palette = (st.get_option("theme.chartCategoricalColors")
               or ["#58A6FF", "#F0883E"])
    colors = {"FRONTIER": palette[0], "LINEUP BOTTOM": palette[1]}

    banner(preds, res, frozen)
    terms(res, frozen)
    st.divider()

    head = st.container(horizontal=True, vertical_alignment="bottom",
                        gap="medium")
    with head:
        st.markdown("### ▸ THE EVIDENCE")
        yardstick = st.segmented_control(
            "YARDSTICK", list(YARDSTICKS), default="AA INDEX",
            label_visibility="collapsed",
            help="Two ways to measure the same climb. METR counts minutes of "
                 "autonomous work and covers frontier models only; the AA "
                 "index covers both tiers, which is why the wager resolves on "
                 "it.",
        )
    capability_chart(df, yardstick or "AA INDEX", colors)

    st.space()
    st.markdown("### ▸ THE LAG")
    lag_table(ms)

    st.space()
    left, right = st.columns([11, 9], gap="large")
    with left:
        st.markdown("### ▸ HOW IT WENT")
        narrative()
    with right:
        st.markdown("### ▸ THE SMALL PRINT")
        methodology(preds, res)
        st.caption("THE FULL TIMELINE")
        st.dataframe(
            df[["model", "vendor", "tier", "release_date", "aa_intel",
                "metr_horizon_min_p50", "current_price_in", "current_price_out",
                "source_url"]],
            hide_index=True, height=320,
            column_config={
                "model": st.column_config.TextColumn("MODEL", width="medium"),
                "vendor": st.column_config.TextColumn("VENDOR", width="small"),
                "tier": st.column_config.TextColumn("TIER", width="small"),
                "release_date": st.column_config.DateColumn("RELEASED",
                                                            width="small"),
                "aa_intel": st.column_config.NumberColumn("AA", format="%.1f",
                                                          width="small"),
                "metr_horizon_min_p50": st.column_config.NumberColumn(
                    "METR MIN", format="%.1f", width="small"),
                "current_price_in": st.column_config.NumberColumn(
                    "IN /1M", format="$%.2f", width="small"),
                "current_price_out": st.column_config.NumberColumn(
                    "OUT /1M", format="$%.2f", width="small"),
                "source_url": st.column_config.LinkColumn("SOURCE",
                                                          display_text="↗"),
            },
        )

    st.caption(
        f"HORIZONS: [METR]({METR_URL}) · SCORES: [ARTIFICIAL ANALYSIS]({AA_URL}) "
        f"· PRICE DECLINE: [EPOCH AI]({EPOCH_URL}) · PRICES: VENDOR DOCS, "
        f"ARCHIVED · EVERY ROW CARRIES ITS SOURCE IN `timeline.csv` · "
        f"THE FROZEN WAGER IS `wager.json` · [REPO]({REPO_URL})"
    )


main()
