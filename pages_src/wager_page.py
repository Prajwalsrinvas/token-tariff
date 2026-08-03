"""
THE TRICKLE-DOWN WAGER — how long the frontier stays the frontier.

Frontier intelligence keeps arriving at the cheapest slot in a vendor's lineup a
few months later, at a fraction of the price. This page stakes a falsifiable
claim on the next repetition — an entry-level model matching Claude Fable 5 on
the Artificial Analysis intelligence index at a tenth of its price, by the
deadline — and then shows the history it rests on, from sourced data.

The page reads in one direction: what is predicted, how it resolves, when it is
expected, the story so far, the evidence, then the small print in layers. Prose
sits in a narrow reading column; charts and tables get the full width.

The arithmetic lives in wager.py and runs against timeline.csv, so the numbers
here move when the data does. wager.json holds the frozen prediction the
scheduled emails were built around; the page flags drift from it rather than
quietly restating it.
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
# The CSV's tier value stays `bottom` — it is data — but nothing a reader sees
# says "lineup bottom", because the wager is written on the entry-level slot.
TIER_LABELS = {"frontier": "FRONTIER", "bottom": "ENTRY-LEVEL"}
TIER_ORDER = ["FRONTIER", "ENTRY-LEVEL"]

# The two things a model can be measured on, one axis at a time. METR counts
# minutes of autonomous work and spans six orders of magnitude, so it reads on
# a log axis; the AA index is a bounded score and reads linear.
YARDSTICKS = {
    "AA INDEX": dict(
        col="aa_intel", log=False, title="ARTIFICIAL ANALYSIS INTELLIGENCE INDEX",
        help="Artificial Analysis' intelligence index, read from a single "
             "snapshot so models from different eras are on one scale. This is "
             "the instrument the wager resolves on."),
    "METR HORIZON": dict(
        col="metr_horizon_min_p50", log=True, title="50% TIME HORIZON (MIN, LOG)",
        help="Task length at which a model succeeds half the time, measured by "
             "METR. Blank for every model METR has not run — including every "
             "entry-level model there has ever been, which is why this is a "
             "secondary check and not the resolution instrument."),
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

# The models the three acts name. Miss one and the story cannot be told from
# the data, which is a data decision rather than something to narrate around.
CAST = ("gpt-4", "gpt-4o", "gpt-4o-mini", "claude-3-opus", "claude-3-5-haiku",
        "o1-preview", "o1", "claude-haiku-4.5", "o3", "gpt-5", "gpt-5.4-nano",
        "claude-opus-4.6", "gpt-5.6-luna", "claude-opus-5", "claude-fable-5")

# What the story says when the data cannot tell it — a missing row, or a row
# whose prices or index are blank. One caption for both, because to a reader
# they are the same fact: the acts are computed, and the figures are not there.
STORY_UNTELLABLE = ("THE STORY NAMES ROWS AND FIGURES timeline.csv NO LONGER "
                    "CARRIES")


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
    return f"IN {d:,} DAYS · {d / wager.DAYS_PER_MONTH:.1f} MONTHS"


def _money(text: str) -> str:
    """Streamlit renders a matched pair of dollar signs as LaTeX, and prices
    come in pairs. Every $ that reaches markdown is escaped."""
    return text.replace("$", "\\$")


def _price(value) -> str:
    """A blended price where the timeline may hold none — the live baseline
    price is information, not the arm, and its absence renders as a dash
    rather than a crash."""
    return f"${value:,.2f}" if value is not None else "—"


def reading():
    """A narrow column for prose. Full-width paragraphs at 1280px run to
    thirty words a line, which is a dashboard measure, not a reading one."""
    return st.columns([11, 9], gap="large")[0]


def timeline_frame(rows: list) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["tier_label"] = df["tier"].map(TIER_LABELS)
    df["date"] = pd.to_datetime(df["release_date"])
    return df


def row_of(rows: list, model: str) -> dict:
    return next((r for r in rows if r["model"] == model), None)


def launch_blend(row: dict, in_out_ratio: float = 3.0):
    """The 3:1 blend of a model's launch prices, where both were sourced. The
    same ruler as blended_price, pointed at the day the model shipped."""
    pin, pout = row["launch_price_in"], row["launch_price_out"]
    if pin is None or pout is None:
        return None
    return (in_out_ratio * pin + pout) / (in_out_ratio + 1)


def months_between(start: dt.date, end: dt.date) -> float:
    return (end - start).days / wager.DAYS_PER_MONTH


def vendor_list(vendors: list, conjunction: str = "or") -> str:
    return f"{', '.join(vendors[:-1])} {conjunction} {vendors[-1]}"


def rate(value: float) -> str:
    """A published per-token rate as the vendor writes it: $30, $0.60, $1.25.
    Two decimals unless the price is a whole number of dollars."""
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}"


# =============================================================================
# Section 3: UI — the prediction
# =============================================================================


def headline(frozen: dict):
    """The question in plain English, the prediction, and what this object is.

    The prediction sentence is rendered from wager.json rather than written
    here, so the page and the frozen wager cannot drift into saying different
    things.
    """
    st.markdown("## ▸ THE TRICKLE-DOWN WAGER")
    with reading():
        st.markdown(f"### Will a bargain model catch mid-2026's frontier by "
                    f"{wager.DEADLINE:%B %Y}?")
        st.markdown(f"**My prediction: yes.** {_money(frozen['claim'])}")
        st.caption(
            f"A PUBLIC, TIMESTAMPED SELF-PREDICTION — NO MONEY, NO "
            f"COUNTERPARTY, NO ONE ON THE OTHER SIDE OF IT. FROZEN "
            f"{frozen['frozen_on']}, TERMS CLARIFIED {frozen['amended_on']}; "
            f"EVERY CHANGE IS IN GIT, AND {len(frozen['sends'])} SCHEDULED "
            f"SELF-EMAILS FORCE A REVIEW WHETHER OR NOT IT IS GOING WELL."
        )


def status_of(res: dict, recorded: dict, today: dt.date) -> tuple:
    """The status cell and the line under it, on either side of the cutoff.

    Before it, the timeline decides: OPEN until a live row clears both terms.
    After it, only the recorded artifact does. A resolution is a reading taken
    on a date and written down, so a row that reaches `timeline.csv` afterwards
    must not be able to settle a closed question — nor to reopen one recorded
    as NO. Between the cutoff and the reading there is no answer yet, and
    saying so is the honest state rather than asserting the NO early.

    Takes the date rather than reading it, so all three states are testable.
    """
    if today <= wager.DEADLINE:
        if res["resolved"]:
            return "RESOLVED YES", f"BY {res['resolved_by']}".upper()
        price_met = (res["best_bottom_price"] is not None
                     and res["price_cap"] is not None
                     and res["best_bottom_price"] <= res["price_cap"])
        index_met = res["gap_points"] is not None and res["gap_points"] <= 0
        return "OPEN", ("BOTH TERMS MET" if price_met and index_met else
                        "PRICE MET · INDEX SHORT" if price_met else
                        "INDEX MET · PRICE SHORT" if index_met else
                        "BOTH TERMS SHORT")
    if recorded is None:
        return "PAST DEADLINE · VERIFYING", "NO RESOLUTION RECORDED YET"
    if recorded["resolved"]:
        return "RESOLVED YES", f"BY {recorded['resolved_by']}".upper()
    return "RESOLVED NO", "NOTHING CLEARED BOTH TERMS"


def scorecard(rows: list, res: dict, frozen: dict):
    """Target, ceiling, contender, gap, status, deadline — the six numbers a
    visitor wants before they have any other question.

    Every one of them is read off the derivation or off the recorded artifact,
    including the status: an asserted "OPEN" is a maintenance burden that goes
    stale silently.
    """
    price_met = (res["best_bottom_price"] is not None
                 and res["price_cap"] is not None
                 and res["best_bottom_price"] <= res["price_cap"])
    index_met = res["gap_points"] is not None and res["gap_points"] <= 0
    today = dt.date.today()
    past = today > wager.DEADLINE
    recorded = wager.recorded_resolution()
    status, standing = status_of(res, recorded, today)

    cells = [
        ("TARGET", f"AA {res['baseline_aa']:.1f}",
         f"{res['baseline']} · FROZEN",
         "The frontier as of June 2026, at its launch index. Frozen: a later "
         "model scoring higher does not move the bar."),
        ("PRICE CEILING", _money(f"${res['price_cap']:,.2f}"),
         "PER MTOK · 3:1 BLEND · FROZEN",
         _money(f"A tenth of {res['baseline']}'s launch price at a fixed 3:1 "
                f"input:output mix — {_price(res['baseline_price'])} per MTok "
                f"blended today, carried as information, not the arm. The "
                f"ceiling is stated as a number so nobody has to derive it "
                f"before arguing with it.")),
        ("CLOSEST", f"AA {res['best_bottom_aa']:.1f}",
         _money(f"{res['best_bottom']} · {_price(res['best_bottom_price'])}/MTOK"),
         "The highest-scoring entry-level model in the timeline, and its "
         "blended price on the same ruler."),
        ("GAP", f"{res['gap_points']:.1f} PTS",
         "OF INDEX LEFT TO CLOSE",
         "Index points between the closest entry-level model and the target. "
         "The price half is a separate term."),
        ("STATUS", status, standing,
         "Computed, not asserted: OPEN until a model clears both terms. Past "
         "the deadline it is whatever was read and recorded under "
         "data/history/, and nothing added to the timeline afterwards can "
         "change it."),
        # The value cell is one line at any width the six columns take, so the
        # date splits: a month and a day that cannot wrap between them, and the
        # year with the countdown underneath.
        ("DEADLINE", f"{wager.DEADLINE:%b %d}".upper(),
         f"{wager.DEADLINE:%Y} · {_countdown(wager.DEADLINE)}",
         "23:59 UTC. The date the slowest price decline Epoch fitted reaches a "
         "tenfold fall, counted from the baseline's release — past it, the "
         "trend claim is false rather than pending."),
    ]
    for col, (label, value, sub, tip) in zip(st.columns(6), cells):
        with col:
            st.caption(label, help=tip)
            st.markdown(f"##### {value}")
            st.caption(sub.upper())

    if res["unevaluable"]:
        st.caption(f"THE BINDING ARM CANNOT BE EVALUATED — "
                   f"{res['unevaluable'].upper()}")

    if past:
        st.caption(
            f"READ FROM {recorded['read_from']}".upper() if recorded else
            "THE CUTOFF HAS PASSED AND NOTHING IS RECORDED UNDER "
            "data/history/ YET — PAST IT THE STATUS IS THE RECORDING, NEVER A "
            "FRESH READ OF timeline.csv")

    st.space()
    with reading():
        # Where it stands is a question with a deadline on it. Past the cutoff
        # the recorded artifact has answered it, and a line about what still
        # has to close would be arguing with a settled result.
        if not past:
            if price_met and not index_met:
                st.markdown(_money(
                    f"**The price half is already met.** {res['best_bottom']} "
                    f"sells at ${res['best_bottom_price']:,.2f} per MTok "
                    f"against a ${res['price_cap']:,.2f} ceiling — "
                    f"{res['price_cap'] / res['best_bottom_price']:.1f}× under "
                    f"it. What is short is capability: {res['gap_points']:.1f} "
                    f"index points. The wager is that those points close before "
                    f"the deadline, and that nothing pushes the price back up "
                    f"while they do."))
            elif not res["resolved"]:
                st.markdown(_money(
                    f"**Both halves are still short.** {res['best_bottom']} is "
                    f"{res['gap_points']:.1f} index points under the target at "
                    f"{_price(res['best_bottom_price'])} per MTok, against a "
                    f"${res['price_cap']:,.2f} ceiling."))

        pin = frontier_pin(rows, res)
        if pin:
            st.caption(
                f"{pin['model']} PASSED {res['baseline']} ON THE INDEX ON "
                f"{pin['release_date']} — AA {pin['aa_intel']:.1f} AGAINST "
                f"{res['baseline_aa']:.1f}. THE WAGER STAYS PINNED TO THE JUNE "
                f"2026 FRONTIER: THAT THE TARGET KEEPS MOVING IS THE THESIS, "
                f"NOT A PROBLEM FOR IT.".upper())


def frontier_pin(rows: list, res: dict) -> dict:
    """The highest-scoring frontier model to pass the baseline since it
    shipped, if one has. The bar is the baseline's launch index and does not
    follow it."""
    base = wager.baseline_row(rows)
    later = [r for r in rows
             if r["tier"] == "frontier" and r["aa_intel"] is not None
             and r["release_date"] > base["release_date"]
             and r["aa_intel"] > base["aa_intel"]]
    return max(later, key=lambda r: r["aa_intel"], default=None)


def how_it_resolves(preds: dict, res: dict, frozen: dict):
    """Two lines anyone can hold in their head, then the formal terms for
    anyone who wants to argue with them."""
    rules = frozen["resolution"]
    st.markdown("### ▸ HOW IT RESOLVES")
    with reading():
        st.markdown(_money(
            f"**YES** — one entry-level model from "
            f"{vendor_list(rules['eligible_vendors'])} reaches AA "
            f"{res['baseline_aa']:.1f} at or below ${res['price_cap']:,.2f} per "
            f"MTok blended, both terms on the same model at the same time, by "
            f"{wager.DEADLINE}.\n\n"
            f"**NO** — none does by 23:59 UTC that day.\n\n"
            f"An *entry-level model* is the cheapest slot a vendor designates "
            f"in its own lineup: Claude Haiku, OpenAI's mini / nano / Luna "
            f"slot, Gemini Flash-Lite. It is the slot, not the price tag — an "
            f"older, cheaper model still on sale does not disqualify the "
            f"current one."))
    terms(preds, res, frozen)


def terms(preds: dict, res: dict, frozen: dict):
    """The formal terms, spelled out before the evidence, so the claim can be
    argued with rather than admired."""
    rules = frozen["resolution"]
    a = preds["a"]
    secondary = rules["secondary_check"]
    with st.expander("EXACT RESOLUTION TERMS"):
        st.markdown(_money(
            f"**The binding arm.** An entry-level model reaches "
            f"{res['baseline']}'s launch [Artificial Analysis]({AA_URL}) "
            f"intelligence index of **{res['baseline_aa']:.1f}**, compared "
            f"inside a single AA snapshot, at **no more than one tenth** of its "
            f"cost per token — **≤ ${res['price_cap']:,.2f}/MTok** on a fixed "
            f"3:1 input:output blend, against {res['baseline']}'s "
            f"{_price(res['baseline_price'])}. There is one arm; nothing else "
            f"settles this.\n\n"
            f"**Deadline.** {rules['resolves_no_if']}\n\n"
            f"**Eligible vendors** are frozen at "
            f"{vendor_list(rules['eligible_vendors'], 'and')}. "
            f"{rules['entry_level_definition']}\n\n"
            f"**Slot inheritance.** {rules['slot_inheritance']}\n\n"
            f"**It is a joint event.** Capability and price, on one model, at "
            f"one time. Neither forecast lens models that conjunction: one "
            f"tracks when the index gets matched, the other how fast price "
            f"falls. Of the **{a['n_priced']}** historical matches where both "
            f"prices are known, **{a['n_under_price_bar']}** cleared the index "
            f"at less than a tenfold price gap and would have failed this "
            f"wager on the day they matched.\n\n"
            f"**Secondary check — METR, non-binding.** METR has published a "
            f"horizon for **{res['metr_measurable']}** entry-level models — "
            f"none, in either suite version — and none for {res['baseline']} "
            f"either. `{res['metr_proxy']}`, an early preview of what Anthropic "
            f"describes as the same underlying model, stands in at "
            f"**{res['metr_target_min']:,.0f} min** p50 on "
            f"[{secondary['suite']}]({METR_URL}). If both ends ever get "
            f"measured on one suite version, an entry-level model at or above "
            f"that figure is corroboration. It settles nothing on its own."))
        st.caption("RESOLUTION CHECKLIST")
        for i, step in enumerate(rules["checklist"], 1):
            st.caption(f"{i}. {step}")


def forecast(preds: dict, frozen: dict):
    """One expected window, two lenses that produce it, and the slow trend as
    an uncertainty note rather than a third competing date."""
    a, b, slow = preds["a"], preds["b"], preds["slow"]
    early, late = preds["earliest"], preds["latest"]
    window = (f"{early:%B} – {late:%B %Y}" if early.year == late.year
              else f"{early:%B %Y} – {late:%B %Y}")

    st.markdown("### ▸ THE FORECAST")
    with reading():
        st.caption("EXPECTED")
        st.markdown(f"#### {window.upper()}")
        st.markdown(
            f"**Past catch-ups took a median {a['median_lag_months']:.1f} "
            f"months** — from a frontier model setting a new index high to the "
            f"first entry-level model reaching it, added to the baseline's "
            f"release. That lands **{a['date']:%B %Y}**.")
        st.caption(f"{a['date']} · {_countdown(a['date'])} · "
                   f"MEDIAN OF {a['n_pairs']} MATCHED PAIRS FROM "
                   f"{a['n_matchers']} CATCH-UP RELEASES")
        st.markdown(
            f"**The price of a fixed capability falls about {b['rate']:g}× a "
            f"year** ([Epoch AI]({EPOCH_URL})). A tenfold fall takes "
            f"{b['years']:.2f} years from the baseline's release, which lands "
            f"**{b['date']:%B %Y}**.")
        st.caption(f"{b['date']} · {_countdown(b['date'])} · "
                   f"EPOCH'S MEDIAN MEASURED RATE")
        st.caption(
            f"UNCERTAINTY · AT THE SLOWEST DECLINE EPOCH FITTED "
            f"({slow['rate']:g}× A YEAR) THE TENFOLD FALL LANDS "
            f"{slow['date']}, WHICH IS WHERE THE DEADLINE SITS. IT IS THE "
            f"SLOWEST TREND MEASURED, NOT A BOUND — NOTHING ABOUT THE FIT SAYS "
            f"THE FUTURE STAYS INSIDE IT.")
        st.caption(f"{frozen['predictions']['forecast_note'].upper()} "
                   f"{frozen['framing'].upper()}")


# =============================================================================
# Section 4: UI — the evidence
# =============================================================================


def story(rows: list, ms: list, res: dict):
    """The history in three acts, every figure computed from the timeline.

    Prose that hardcodes a number reads as a finding and ages into a lie the
    first time a row changes, so the acts name models and let the CSV supply
    the arithmetic.
    """
    cast = {m: row_of(rows, m) for m in CAST}
    by_frontier = {m["frontier"]: m for m in ms}
    milestones_named = ("gpt-4", "claude-3-opus", "o1", "gpt-5",
                        "claude-opus-4.6")
    if any(r is None for r in cast.values()) or not set(milestones_named) <= \
            set(by_frontier):
        st.caption(STORY_UNTELLABLE)
        return

    g4, mini = cast["gpt-4"], cast["gpt-4o-mini"]
    opus3, haiku35 = cast["claude-3-opus"], cast["claude-3-5-haiku"]
    o1p, o1, haiku45 = cast["o1-preview"], cast["o1"], cast["claude-haiku-4.5"]
    nano, luna = cast["gpt-5.4-nano"], cast["gpt-5.6-luna"]
    opus5, base = cast["claude-opus-5"], cast["claude-fable-5"]

    g4_launch, mini_launch = launch_blend(g4), launch_blend(mini)
    plateau_high = max((m["frontier_aa"] for m in ms
                        if m["frontier_date"] < o1p["release_date"]),
                       default=None)
    nano_clears = sum(1 for m in ms if m["matched_by"] == nano["model"])
    luna_cut = (1 - luna["current_price_in"] / luna["launch_price_in"]
                if luna["current_price_in"] is not None
                and luna["launch_price_in"] else None)
    shortest = min((m for m in ms if m["lag_months"] is not None),
                   key=lambda m: m["lag_months"], default=None)
    # Ratios are computed here rather than inline so a zero denominator is a
    # missing figure like any other, not a division in the middle of a
    # paragraph.
    g4_over_mini = g4_launch / mini_launch if g4_launch and mini_launch else None
    headroom = (res["price_cap"] / res["best_bottom_price"]
                if res["price_cap"] and res["best_bottom_price"] else None)

    # timeline.csv records absence rather than a guess, so any figure the acts
    # format can come back blank. Prose is not a table: a paragraph with a hole
    # in it reads as a broken claim, and a paragraph that raises takes the rest
    # of the page with it. All of them are checked before a word is written.
    figures = [
        g4_launch, mini_launch, g4_over_mini, plateau_high, luna_cut, shortest,
        headroom, res["best_bottom_aa"], res["best_bottom_price"],
        res["gap_points"],
        *(r["aa_intel"] for r in cast.values()),
        *(p for r in (g4, mini, nano, luna)
          for p in (r["launch_price_in"], r["launch_price_out"])),
        luna["current_price_in"], luna["current_price_out"],
        *(by_frontier[m]["lag_months"]
          for m in ("gpt-4", "claude-3-opus", "o1", "gpt-5")),
        *(by_frontier[m]["price_ratio"]
          for m in ("claude-3-opus", "o1", "gpt-5")),
    ]
    if any(v is None for v in figures):
        st.caption(STORY_UNTELLABLE)
        return

    st.markdown("### ▸ HOW IT WENT")
    with reading():
        st.markdown(_money(f"""
**ACT 1 · THE PATTERN BEGINS**

**{g4['release_date']:%Y-%m} — the frontier costs ${g4_launch:,.2f} per MTok.**
GPT-4 lands at ${rate(g4['launch_price_in'])}/${rate(g4['launch_price_out'])} and
completes tasks that take a human about four minutes, half the time
([METR]({METR_URL})). On the index it scores {g4['aa_intel']:.1f}.

**{months_between(g4['release_date'], mini['release_date']):.0f} months later,
the cheap tier is a tenth of a point away.** GPT-4o mini ships at
${rate(mini['launch_price_in'])}/${rate(mini['launch_price_out'])} —
{g4_over_mini:.0f}× cheaper than GPT-4's launch price on this page's
3:1 blend (${g4_launch:,.2f} → ${mini_launch:,.2f} per MTok) — and scores
{mini['aa_intel']:.1f} against GPT-4's {g4['aa_intel']:.1f}. A near-miss, and
the shape of everything after it.

**{haiku35['release_date']:%Y-%m} — the first clean catch-up.** Claude 3.5 Haiku
reaches {haiku35['aa_intel']:.1f}, clearing GPT-4
({by_frontier['gpt-4']['lag_months']:.0f} months after it shipped) and Claude 3
Opus ({by_frontier['claude-3-opus']['lag_months']:.0f} months) at
1/{by_frontier['claude-3-opus']['price_ratio']:.0f} of Opus's price.

Expensive frontier capability keeps arriving at the cheapest slot in a lineup
months later. That is the whole thesis. The rest is how fast, and whether it
still holds.

**ACT 2 · REASONING MOVES THE FRONTIER**

**{g4['release_date']:%Y-%m} → {o1p['release_date']:%Y-%m} — the plateau.** For
{months_between(g4['release_date'], o1p['release_date']):.0f} months the index
high-water mark moves only {g4['aa_intel']:.1f} → {plateau_high:.1f}, and GPT-4o
— faster and cheaper than anything before it, at {cast['gpt-4o']['aa_intel']:.1f}
— never takes it. Daniel Han: *"for one year the models kind of plateaued … I
call this the intelligence plateau"* ([talk]({HAN_URL})).

**{o1p['release_date']:%Y-%m} — the slope changes.** o1-preview is trained to
spend compute at inference: *"the performance of o1 consistently improves with …
more time spent thinking"* ([OpenAI]({O1_URL})). METR's doubling time since 2024
is 89 days against 187.8 days across the whole record, both from the TH1.1 suite
([METR]({METR_TH11_URL})).

The target starts moving again, and fast: in the
{months_between(o1p['release_date'], base['release_date']):.0f} months from
o1-preview to {base['model']}, the frontier goes {o1p['aa_intel']:.1f} →
{base['aa_intel']:.1f}. The wager is not a trivial extrapolation, because the
thing being chased keeps accelerating.

**ACT 3 · THE CHEAP TIER ACCELERATES**

**{haiku45['release_date']:%Y-%m} — Haiku takes o1.** Claude Haiku 4.5 reaches
{haiku45['aa_intel']:.1f} and clears o1's {o1['aa_intel']:.1f}
{by_frontier['o1']['lag_months']:.0f} months later, at
1/{by_frontier['o1']['price_ratio']:.0f} of the price: December 2024's reasoning
frontier, at entry-level rates.

**{nano['release_date']:%Y-%m} — the lag shortens.** GPT-5.4 nano clears
{nano_clears} standing frontier highs at once — GPT-5's index in
{by_frontier['gpt-5']['lag_months']:.0f} months — on one
${rate(nano['launch_price_in'])}/${rate(nano['launch_price_out'])} release, at
1/{by_frontier['gpt-5']['price_ratio']:.0f} of GPT-5's price.

**{luna['release_date']:%Y-%m} — the price war.** Luna launches at
${rate(luna['launch_price_in'])}/${rate(luna['launch_price_out'])} and is cut
{luna_cut:.0%} to ${rate(luna['current_price_in'])}/${rate(luna['current_price_out'])}
three weeks later ([OpenAI]({LUNA_URL}), [CNBC]({LUNA_PRESS_URL})); Opus 5 ships
at Opus 4.8's price while scoring {opus5['aa_intel']:.1f}, above the baseline's
{base['aa_intel']:.1f}. {shortest['matched_by']} clears {shortest['frontier']}
{shortest['lag_months']:.1f} months after it shipped — the shortest lag in the
record.

**Where that leaves it.** {res['best_bottom']} scores
{res['best_bottom_aa']:.1f} at ${res['best_bottom_price']:,.2f} per MTok
blended: {res['gap_points']:.1f} points short of the target, and already
{headroom:.1f}× under the price ceiling. The
wager is that those {res['gap_points']:.1f} points close before
{wager.DEADLINE}.
"""))


def _axis_y(value: float, log: bool) -> float:
    """Shapes and annotations are positioned in the axis' own coordinates, and
    a log axis' coordinates are exponents. Plotly does not convert for us: pass
    a raw 60 to a log axis and the label lands at 10^60, off the top of the
    plot, taking the layout with it."""
    return math.log10(value) if log else value


def capability_chart(df: pd.DataFrame, yardstick: str, colors: dict):
    """Frontier and entry-level tier over time on one axis, with the three
    moments that shaped the trend called out."""
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
    luna = plot[plot["model"] == "gpt-5.6-luna"]
    cut = (1 - luna.iloc[0]["current_price_in"] / luna.iloc[0]["launch_price_in"]
           if not luna.empty and luna.iloc[0]["launch_price_in"] else None)
    for model, text, anchor, ax, ay in [
        ("o1-preview", "o1-preview — TEST-TIME COMPUTE", "right", -8, -30),
        ("gpt-5.6-luna", f"LUNA — {cut:.0%} PRICE CUT, 3 WEEKS IN"
         if cut else "LUNA", "right", -12, -30),
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
    # METR view reads as broken rather than as the reason METR cannot settle
    # this.
    missing = [label for tier, label in TIER_LABELS.items()
               if plot[plot["tier"] == tier].empty]
    if missing:
        st.caption(
            f"NO {' OR '.join(missing)} MODEL HAS EVER BEEN MEASURED ON THIS "
            f"YARDSTICK — THAT ABSENCE IS WHY IT IS A SECONDARY CHECK AND THE "
            f"WAGER RESOLVES ON THE AA INDEX"
        )
    st.caption(spec["help"].upper())


def lag_table(ms: list):
    """Every frontier high-water mark and the first entry-level model to reach
    it. Open rows are the wager's neighbourhood.

    Seven columns at fixed pixel widths: the table has to be readable at
    1280px, where "small" columns and long headers push LAG and PRICE × off the
    right edge. The two index columns are merged into one frontier → match
    cell for the same reason.
    """
    def _num(v, fmt="{:.1f}"):
        return "—" if v is None or v != v else fmt.format(float(v))

    view = pd.DataFrame([{
        "frontier": m["frontier"],
        # YYYY-MM, as strings: months are the resolution the story is told at,
        # and mixing dates with an em-dash in one object column breaks Arrow
        # serialization (a logged traceback per render).
        "released": f"{m['frontier_date']:%Y-%m}",
        "aa": f"{_num(m['frontier_aa'])} → "
              f"{_num(m['matched_aa'] if m['matched_by'] else m['closest_aa'])}",
        "matched_by": m["matched_by"] or "— OPEN —",
        "matched": f"{m['matched_date']:%Y-%m}" if m["matched_date"] else "—",
        "lag": _num(m["lag_months"]),
        "ratio": _num(m["price_ratio"]),
    } for m in ms])

    st.dataframe(
        view, hide_index=True, height=35 * (len(view) + 1) + 3,
        column_config={
            "frontier": st.column_config.TextColumn("FRONTIER", width=170,
                                                    pinned=True),
            "released": st.column_config.TextColumn("RELEASED", width=90),
            "aa": st.column_config.TextColumn(
                "AA", width=110,
                help="The frontier model's index, then the index the model "
                     "that matched it reached. On open rows the second figure "
                     "is the closest an entry-level model has come, not a "
                     "match."),
            "matched_by": st.column_config.TextColumn(
                "FIRST MATCH", width=170,
                help="The first model in the entry-level slot of any vendor's "
                     "lineup to reach that index — the trickle-down is "
                     "cross-vendor."),
            "matched": st.column_config.TextColumn("ON", width=90),
            "lag": st.column_config.TextColumn(
                "LAG (MO)", width=90, alignment="right",
                help="Months from the frontier release to the entry-level "
                     "model that matched it."),
            "ratio": st.column_config.TextColumn(
                "PRICE ×", width=90, alignment="right",
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


def drift(preds: dict, frozen: dict):
    """Frozen against live. The claim is frozen; the dates the same formulas
    produce today are not, and a visitor has to be able to tell which is
    which."""
    live = [
        ("THE HISTORICAL-LAG DATE", preds["a"]["date"],
         frozen["predictions"]["method_a"]["date"]),
        ("THE PRICE-DECLINE DATE", preds["b"]["date"],
         frozen["predictions"]["method_b"]["date"]),
        ("THE SLOWEST-TREND DATE", preds["slow"]["date"],
         frozen["predictions"]["slowest_trend"]["date"]),
    ]
    moved = [(label, now, then) for label, now, then in live if str(now) != then]
    with reading():
        if moved:
            st.markdown(":violet-badge[THE LIVE PROJECTION HAS MOVED; THE "
                        "ORIGINAL PREDICTION HAS NOT]")
            for label, now, then in moved:
                st.caption(f"{label} · FROZEN {then} · RECOMPUTED TODAY {now}")
            st.caption(
                "THE CLAIM, THE BASELINE, THE PRICE CEILING AND THE DEADLINE "
                "ARE FROZEN AND DO NOT MOVE. THESE DATES ARE THE SAME FORMULAS "
                "RUN OVER NEWER DATA — THE DIVERGENCE IS THE POINT OF FREEZING "
                "THE FILE.")
        else:
            st.markdown(":gray-badge[LIVE DATA STILL REPRODUCES EVERY FROZEN "
                        "DATE]")
            st.caption(
                f"THE FORECAST DATES RECOMPUTE EXACTLY AS `wager.json` FROZE "
                f"THEM ON {frozen['frozen_on']}. IF A TIMELINE ROW CHANGES AND "
                f"THEY MOVE, THIS NOTICE SAYS SO RATHER THAN QUIETLY "
                f"RESTATING THE HEADLINE.")


# =============================================================================
# Section 5: UI — the layers
# =============================================================================


def why_i_believe_it(preds: dict):
    """The two lenses in full, and what the sample really is."""
    a, b = preds["a"], preds["b"]
    with st.expander("WHY I BELIEVE IT"):
        st.markdown(f"""
**The historical-lag lens** takes the median of {a['n_pairs']} matched lags
({a['median_lag_months']:.1f} months; mean {a['mean_lag_months']:.1f}) rather
than fitting a trend. The lags are shrinking, so a fitted trend would predict
sooner — median is the conservative reading, and with one pair more than twice
any other it is also the robust one.

**The sample is smaller than the pair count.** Those {a['n_pairs']} pairs are
produced by **{a['n_matchers']} catch-up releases**: one cheap model that clears
three standing frontier highs at once contributes three pairs and one piece of
evidence. Treat the effective sample as {a['n_matchers']}, not {a['n_pairs']}.

**The price-decline lens** uses Epoch AI's finding that the price of a fixed
level of benchmark performance falls **{wager.EPOCH_SLOW_DECLINE:g}× to 900× per
year, median {wager.EPOCH_MEDIAN_DECLINE:g}×** ([Epoch]({EPOCH_URL})). Because
the price term is a ratio — one tenth of the baseline's cost — the answer is
just the time for a tenfold fall, and does not depend on the input:output mix or
on either sticker price. At the median rate that is {b['years']:.2f} years,
counted from the baseline's release rather than from the day this page read the
feeds: what is falling is the price of that capability, and it started falling
when the capability first existed.

**The high-water-mark rule does the milestone selection.** A frontier release
counts only if it sets a new high on the index, so which releases are milestones
follows from the data instead of from a hand-picked list — and a release that
failed to beat the standing best drops out on its own.
""")


def what_could_make_it_wrong(preds: dict, res: dict, frozen: dict):
    """The caveats that decide whether any of the above means anything."""
    a = preds["a"]
    with st.expander("WHAT COULD MAKE IT WRONG"):
        st.markdown(_money(f"""
**Matching the index is not general equivalence.** The Artificial Analysis index
is an exam-style composite. A model can reach {res['baseline_aa']:.1f} without
being a substitute for the model it matched: long-context behaviour and agentic
reliability are not in the index, and this wager does not claim they follow. It
claims one number, at one price, by one date.

**Sticker price is not cost per task.** George Cameron of Artificial Analysis:
*"you're paying for the cost per token but then you're also paying for how
verbose the models are … you need to … measure it not just by the cost per
million tokens but also considering how many reasoning tokens there are"*
([talk]({CAMERON_URL})). A verbose entry-level model can cost more per finished
task than a frontier model at ten times the per-token rate. The PRICE × column
and the ${res['price_cap']:,.2f} ceiling are a fixed 3:1 blend of published
rates — a ruler for comparing two models, not an estimate of what either costs
to run. Anthropic also puts its 4.7-and-later tokenizer at *"approximately 30%
more tokens for the same text"* ([Anthropic]({TOKENIZER_URL})), which per-token
rates do not capture.

**The two dates are not independent evidence.** Capability diffusion and price
decline are two views of one process, so the lenses landing two months apart is
not corroboration. And the conjunction bites: of the {a['n_priced']} historical
matches where both prices are known, **{a['n_under_price_bar']}** cleared the
index at less than a tenfold price gap and would have failed this wager's price
term on the day they matched.

**50% is not 80%.** METR's headline horizon is the task length a model clears
half the time. The Mythos preview measures **1,044.8 min at 50% but 185.9 min at
80%** — a 5.6× difference. A model that has "matched" at 50% has not matched at
80%, which is one reason METR is a secondary check here rather than the binding
arm.

**METR cannot corroborate anything yet.** METR has measured no entry-level model
in either suite — no Haiku, no Flash, no Flash-Lite, no Luna, no nano — and no
horizon is published for {res['baseline']} either. The only "mini" entries are
GPT-4o mini (release date only, no horizon) and o4-mini.

**It could resolve YES on a technicality.** An index version change that rescores
everything, or a vendor moving a mid-tier model into its entry slot. The terms
name the slot a vendor prices and markets as its cheapest for that reason, and
say to re-read the baseline on the same snapshot if the index version moves.

**It could resolve NO for the wrong reason.** The trend holds perfectly well and
the entry-level slot simply stops being called that, or a vendor stops shipping
one. The eligible vendors are frozen at
{vendor_list(frozen['resolution']['eligible_vendors'])}, so a fourth lab doing
it first would not settle this either.
"""))


def full_evidence(df: pd.DataFrame):
    """Every row the page runs on, and how the feeds it came from behave."""
    with st.expander("FULL EVIDENCE"):
        st.markdown(f"""
**Two feeds, two vintages.** Artificial Analysis publishes no index-version tag
in either feed this repo reads, and it re-scores old models when the index
changes — so a 2024 score read today is not the score that was published in
2024. Scores come from two feeds of different ages: OpenRouter's listing, read
**{wager.SNAPSHOT_DATE}**, and this repo's committed AA API payload, which
predates GPT-5.6 and Opus 5 and is dated no later than
**{wager.AA_API_VINTAGE}**. Each row's `aa_version` says which it was read at.
The AA payload covers the models OpenRouter has since delisted, which is the
only way to put GPT-4 and the baseline on one axis; the comparison the wager
turns on sits entirely inside the fresh OpenRouter feed. `data/history/` is
append-only so a future version change is visible rather than silent.

**One configuration rule, applied to every row.** Models that publish several
configurations — thinking and non-thinking, reasoning and not, adaptive — are
recorded at their **highest-scoring published configuration**, consistently.
Picking per row would let the choice of configuration decide which releases
count as milestones.

**METR suite versions do not mix.** All horizon figures are METR-Horizon-v1.1.
The same model scores differently under v1.0 (GPT-4: 4.0 min under 1.1, 6.0
under 1.0), so mixing them would manufacture progress.

**Blanks are blanks.** Every row in `timeline.csv` carries a source URL, and a
fact that could not be sourced is left empty rather than estimated — which is
why some launch prices, and the price ratios that depend on them, are missing.
""")
        st.caption("THE FULL TIMELINE")
        st.dataframe(
            df[["model", "vendor", "tier", "release_date", "aa_intel",
                "metr_horizon_min_p50", "current_price_in", "current_price_out",
                "source_url"]],
            hide_index=True, height=320,
            column_config={
                "model": st.column_config.TextColumn("MODEL", width="medium",
                                                     pinned=True),
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
            f"HORIZONS: [METR]({METR_URL}) · SCORES: [ARTIFICIAL ANALYSIS]"
            f"({AA_URL}) · PRICE DECLINE: [EPOCH AI]({EPOCH_URL}) · PRICES: "
            f"VENDOR DOCS, ARCHIVED · EVERY ROW CARRIES ITS SOURCE IN "
            f"`timeline.csv`"
        )


def frozen_artifact(frozen: dict):
    """What was written down, when, and what was changed afterwards."""
    amendment = frozen["amendment"]
    with st.expander("THE FROZEN ARTIFACT"):
        st.markdown(_money(
            f"`wager.json` is the prediction as it stands, version "
            f"**{frozen['version']}** — frozen **{frozen['frozen_on']}**, terms "
            f"clarified **{frozen['amended_on']}**. The scheduled emails and "
            f"this page both render from it, so neither can quietly say "
            f"something else.\n\n"
            f"**What the clarification changed:**"))
        for change in amendment["changed"]:
            st.caption(f"· {_money(change)}")
        st.markdown(_money(
            f"**Why then.** {amendment['why']}\n\n"
            f"**Version 1.** {amendment['v1']}"))
        st.caption("SCHEDULED SENDS")
        for send in frozen["sends"]:
            st.markdown(
                f":blue-badge[{send['id'].replace('-', ' ').upper()} · "
                f"{send['due']}] {send['purpose']}")
        st.caption(
            f"THE WAGER FILE, THE TIMELINE AND THE ARITHMETIC ARE ALL IN THE "
            f"REPO · [{REPO_URL.split('/')[-1]}]({REPO_URL})")


# =============================================================================
# Section 6: Main
# =============================================================================


def main():
    rows, ms, preds, res, frozen = load()
    df = timeline_frame(rows)

    palette = (st.get_option("theme.chartCategoricalColors")
               or ["#58A6FF", "#F0883E"])
    colors = {"FRONTIER": palette[0], "ENTRY-LEVEL": palette[1]}

    headline(frozen)
    st.space()
    scorecard(rows, res, frozen)
    st.divider()

    how_it_resolves(preds, res, frozen)
    st.space()
    forecast(preds, frozen)
    st.divider()

    story(rows, ms, res)

    st.space()
    head = st.container(horizontal=True, vertical_alignment="bottom",
                        gap="medium")
    with head:
        st.markdown("### ▸ THE MEASURE")
        yardstick = st.segmented_control(
            "YARDSTICK", list(YARDSTICKS), default="AA INDEX",
            label_visibility="collapsed",
            help="The AA index is what the wager resolves on: it covers both "
                 "tiers. METR counts minutes of autonomous work and has never "
                 "measured an entry-level model, which is why it is the "
                 "secondary check.",
        )
    capability_chart(df, yardstick or "AA INDEX", colors)

    st.space()
    st.markdown("### ▸ EVERY CATCH-UP")
    lag_table(ms)

    st.space()
    drift(preds, frozen)
    st.divider()

    st.markdown("### ▸ THE SMALL PRINT")
    why_i_believe_it(preds)
    what_could_make_it_wrong(preds, res, frozen)
    full_evidence(df)
    frozen_artifact(frozen)


main()
