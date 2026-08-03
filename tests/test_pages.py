"""
Both pages boot, and the things a reader would quote off them are the things
`wager.json` says.

These run the real Streamlit scripts through AppTest — no network, since every
fetch in the app falls back to a committed JSON file — so they catch the class
of bug that unit tests cannot: a chart annotation positioned in the wrong
coordinate space, an empty cell rendering the word "None", a claim sentence
drifting away from the document it is supposed to quote.
"""

import datetime as dt
import json
import math
import pathlib
import sys
import types

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import wager  # noqa: E402

ROOT = pathlib.Path(wager.ROOT)
WAGER_PAGE = str(ROOT / "pages_src" / "wager_page.py")
RATE_CARD = str(ROOT / "app.py")
RATE_CARD_SRC = str(ROOT / "pages_src" / "rate_card.py")
TIMEOUT = 90


def page_module(path: str, name: str) -> types.ModuleType:
    """A page's functions without its page.

    Both files call main() on import, as a Streamlit script must; the source is
    loaded with that call removed, so the rules underneath can be checked on
    frames and dates written for the purpose instead of on whatever the live
    feeds and today's date happen to say."""
    source = pathlib.Path(path).read_text().replace("\nmain()\n", "\n")
    module = types.ModuleType(name)
    module.__file__ = path
    exec(compile(source, path, "exec"), module.__dict__)
    return module


RATE = page_module(RATE_CARD_SRC, "rate_card")
PAGE = page_module(WAGER_PAGE, "wager_page")


def run(path: str, **query) -> AppTest:
    app = AppTest.from_file(path, default_timeout=TIMEOUT)
    for key, value in query.items():
        app.query_params[key] = value
    app.run()
    assert not app.exception, app.exception
    return app


@pytest.fixture(scope="module")
def page() -> AppTest:
    return run(WAGER_PAGE)


@pytest.fixture(scope="module")
def frozen() -> dict:
    return wager.load_wager()


def chart_figure(yardstick: str):
    """The capability chart as a Plotly figure, built by the page's own code,
    with st.plotly_chart swapped for a collector."""
    captured = []
    original, st.plotly_chart = st.plotly_chart, lambda fig, **kw: captured.append(fig)
    try:
        rows = wager.load_timeline()
        palette = st.get_option("theme.chartCategoricalColors")
        PAGE.capability_chart(
            PAGE.timeline_frame(rows), yardstick,
            {"FRONTIER": palette[0], "ENTRY-LEVEL": palette[1]})
    finally:
        st.plotly_chart = original
    return captured[-1]


def captions_of(render) -> list:
    """Every caption a page function emits, with no Streamlit runtime under
    it — the page's own reporting channel for what it could not render."""
    captured = []
    original, st.caption = st.caption, lambda text, **kw: captured.append(text)
    try:
        render()
    finally:
        st.caption = original
    return captured


def text_of(app: AppTest) -> str:
    """Every string the page rendered, in one blob."""
    parts = [el.value for el in app.markdown]
    parts += [el.value for el in app.caption]
    return "\n".join(str(p) for p in parts)


def test_the_page_shows_every_frozen_date(page, frozen):
    body = text_of(page)
    preds = frozen["predictions"]
    for date in (preds["method_a"]["date"], preds["method_b"]["date"],
                 preds["slowest_trend"]["date"], frozen["deadline"]):
        assert date in body, date
    for send in frozen["sends"]:
        label = send["id"].replace("-", " ").upper()
        assert f"{label} · {send['due']}" in body


def test_claim_is_rendered_from_the_frozen_wager(page, frozen):
    """Dollar signs are escaped on the way into markdown, or a price pair
    renders as LaTeX. Everything else is the frozen sentence, verbatim."""
    assert frozen["claim"].replace("$", "\\$") in text_of(page)


def test_the_page_reads_in_one_direction(page):
    """The order is the argument: the question and where it stands, then the
    rule, then the forecast, then the history that motivates it, then the
    evidence, then the small print."""
    body = text_of(page)
    order = ["▸ THE TRICKLE-DOWN WAGER", "▸ HOW IT RESOLVES", "▸ THE FORECAST",
             "▸ HOW IT WENT", "▸ THE MEASURE", "▸ EVERY CATCH-UP",
             "▸ THE SMALL PRINT"]
    found = [body.find(heading) for heading in order]
    assert all(i >= 0 for i in found), dict(zip(order, found))
    assert found == sorted(found), dict(zip(order, found))
    for layer in ("WHY I BELIEVE IT", "WHAT COULD MAKE IT WRONG",
                  "FULL EVIDENCE", "THE FROZEN ARTIFACT",
                  "EXACT RESOLUTION TERMS"):
        assert layer in [e.label for e in page.expander], layer


def test_the_scorecard_is_computed_from_the_timeline(page):
    """Target, ceiling, contender, gap and status all come off the derivation
    — an asserted status goes stale the day the data moves."""
    res = wager.resolution(wager.load_timeline())
    body = text_of(page)
    assert f"AA {res['baseline_aa']:.1f}" in body
    assert f"AA {res['best_bottom_aa']:.1f}" in body
    assert f"{res['gap_points']:.1f} PTS" in body
    assert f"\\${res['price_cap']:,.2f}" in body
    assert "OPEN" in body
    # The joint event, stated rather than left to be inferred.
    assert "The price half is already met." in body


RECORDED_YES = {"resolved": True, "resolved_by": "gemini-4-flash-lite",
                "read_from": "data/history/2027-06-28"}
RECORDED_NO = {"resolved": False, "resolved_by": None,
               "read_from": "data/history/2027-06-28"}


def test_the_status_before_the_deadline_is_the_live_reading():
    live = wager.resolution(wager.load_timeline())
    assert PAGE.status_of(live, None, wager.DEADLINE) == (
        "OPEN", "PRICE MET · INDEX SHORT")
    resolved = dict(live, resolved=True, resolved_by="doctored-entry-level")
    assert PAGE.status_of(resolved, None, wager.DEADLINE)[0] == "RESOLVED YES"


def test_the_status_after_the_deadline_is_the_recorded_artifact():
    """Past the cutoff only the recording answers. A resolution is a reading
    taken on a date and written down, so a row that reaches timeline.csv
    afterwards must not settle a closed question — and until the reading is
    taken there is no answer to render, which is a state of its own rather
    than an early NO."""
    live = wager.resolution(wager.load_timeline())
    after = wager.DEADLINE + dt.timedelta(days=1)

    assert PAGE.status_of(live, None, after) == (
        "PAST DEADLINE · VERIFYING", "NO RESOLUTION RECORDED YET")
    assert PAGE.status_of(live, RECORDED_YES, after) == (
        "RESOLVED YES", "BY GEMINI-4-FLASH-LITE")
    assert PAGE.status_of(live, RECORDED_NO, after)[0] == "RESOLVED NO"

    # The same live hit that resolves it before the cutoff decides nothing
    # after it, whatever the recording says or fails to say.
    hit = dict(live, resolved=True, resolved_by="doctored-entry-level")
    assert PAGE.status_of(hit, RECORDED_NO, after)[0] == "RESOLVED NO"
    assert PAGE.status_of(hit, None, after)[0] == "PAST DEADLINE · VERIFYING"


def test_the_deadline_cell_cannot_wrap_mid_date(page):
    """Six columns leave the value cell narrow enough to break an ISO date
    between its parts. The month and day stay together; the year goes to the
    subline with the countdown."""
    body = text_of(page)
    assert f"##### {wager.DEADLINE:%b %d}".upper() in body.upper()
    assert f"##### {wager.DEADLINE}" not in body
    assert f"{wager.DEADLINE:%Y} · IN " in body


def test_the_story_needs_every_figure_it_formats():
    """timeline.csv records absence rather than a guess, so any figure the
    three acts format can come back blank. A paragraph with a hole in it reads
    as a broken claim, and one that raises takes the rest of the page down."""
    rows = wager.load_timeline()
    assert captions_of(
        lambda: PAGE.story(rows, wager.milestones(rows),
                           wager.resolution(rows))) == []

    for blank in ("launch_price_in", "current_price_in", "aa_intel"):
        doctored = [dict(r) for r in rows]
        for r in doctored:
            if r["model"] == "gpt-5.6-luna":
                r[blank] = None
        assert captions_of(
            lambda d=doctored: PAGE.story(
                d, wager.milestones(d), wager.resolution(d))
        ) == [PAGE.STORY_UNTELLABLE], blank


def test_no_implementation_vocabulary_reaches_the_reader(page):
    """METHOD A and METHOD B are identifiers in wager.json and in the code; a
    visitor gets lenses. "Lineup-bottom" is the wording the amendment
    replaced, and the CSV's `bottom` tier is data, not copy."""
    body = text_of(page).upper()
    for term in ("METHOD A", "METHOD B", "LINEUP-BOTTOM", "LINEUP BOTTOM",
                 "BOTTOM-TIER"):
        assert term not in body, term
    assert "ENTRY-LEVEL MODEL" in body


def test_slowest_trend_is_an_uncertainty_note_not_a_third_date(page):
    body = text_of(page)
    assert "UNCERTAINTY · AT THE SLOWEST DECLINE EPOCH FITTED" in body
    assert "NOT A BOUND" in body
    assert "PESSIMISTIC BOUND" not in body


def test_frozen_and_live_are_told_apart(page, frozen):
    """One of these two notices always renders: either the recomputation
    still reproduces the frozen dates, or it has moved and says which."""
    body = text_of(page)
    assert ("LIVE DATA STILL REPRODUCES EVERY FROZEN DATE" in body
            or "THE LIVE PROJECTION HAS MOVED; THE ORIGINAL PREDICTION HAS "
               "NOT" in body)


def test_lag_table_has_no_none_literals(page):
    """Open rows have no match date, lag or price ratio. The data grid prints
    any missing value — None, NaN or NaT alike — as a dimmed "None", so the
    page pre-formats every nullable cell to a string and blanks with an
    em-dash. The grid must never see a missing value at all."""
    lag_table = page.dataframe[0].value
    assert len(lag_table) == len(wager.milestones(wager.load_timeline()))
    assert "None" not in lag_table.to_string()
    assert not lag_table.isna().any().any(), (
        "a missing value reached the grid — it will render as 'None'")
    open_rows = lag_table[lag_table["matched_by"] == "— OPEN —"]
    assert not open_rows.empty
    assert (open_rows["lag"] == "—").all()
    assert (open_rows["matched"] == "—").all()
    # Matched rows keep real formatted values.
    matched = lag_table[lag_table["matched_by"] != "— OPEN —"]
    assert matched["lag"].str.match(r"\d+\.\d$").all()


def test_lag_table_fits_without_horizontal_scrolling(page):
    """Seven columns at fixed pixel widths, dates at month resolution, and one
    merged index column — the shape that reads at 1280px. Re-adding a column
    or letting a width go back to "small" is what pushed LAG and PRICE × off
    the right edge."""
    element = page.dataframe[0]
    assert list(element.value.columns) == [
        "frontier", "released", "aa", "matched_by", "matched", "lag", "ratio"]
    assert element.value["aa"].str.contains("→").all()
    assert element.value["released"].str.match(r"\d{4}-\d{2}$").all()
    matched = element.value[element.value["matched_by"] != "— OPEN —"]
    assert matched["matched"].str.match(r"\d{4}-\d{2}$").all()
    # The hidden index carries no width; every visible column must.
    widths = [c["width"] for name, c in json.loads(element.proto.columns).items()
              if not name.startswith("_")]
    assert len(widths) == 7 and sum(widths) <= 900, widths


@pytest.mark.parametrize("yardstick", ["METR HORIZON", "AA INDEX"])
def test_chart_annotations_land_inside_the_plot(yardstick):
    """The METR yardstick is a log axis, where shapes and annotations are
    positioned by exponent. Passing a raw 60-minute value would place a label
    at 10^60 and drag the autorange with it.

    AppTest cannot read a Plotly figure back out, so the figure is captured
    from the page's own chart function rather than from the rendered tree."""
    fig = chart_figure(yardstick)
    plotted = [y for trace in fig.data for y in (trace.y if trace.y is not None else [])
               if y == y]  # NaN is the only value that fails this
    low, high = min(plotted), max(plotted)

    if yardstick == "METR HORIZON":
        assert fig.layout.yaxis.type == "log"
        # Traces carry raw minutes; the axis they land on is exponents. The
        # METR data runs 4 min to 17 h, so the drawn axis spans 10^0..10^4.
        low, high = math.log10(low), math.log10(high)
        assert 0 <= low and high < 4, f"axis spans 10^{low}..10^{high}"

    # Only the things anchored to the data axis. The "BEFORE REASONING" band
    # spans the plot in domain coordinates (0..1) and is not part of this check.
    # Shapes and annotations take DIFFERENT coordinates on a log axis: shapes
    # carry raw data values (Plotly log-transforms them), annotations carry
    # exponents. Checking them in one space is exactly how the ceiling line
    # ended up at 1.8 minutes with its label at 60.
    on_axis = (None, "y")
    annots = [a.y for a in fig.layout.annotations
              if a.y is not None and a.yref in on_axis]
    shapes = [s.y0 for s in fig.layout.shapes
              if s.y0 is not None and s.yref in on_axis]
    assert annots and shapes
    assert all(low <= y <= high for y in annots), (
        f"{yardstick}: annotations at {annots} are outside the plotted "
        f"range {low}..{high} — wrong coordinate space")
    raw_low, raw_high = min(plotted), max(plotted)
    assert all(raw_low <= y <= raw_high for y in shapes), (
        f"{yardstick}: shapes at {shapes} are outside the raw data range "
        f"{raw_low}..{raw_high} — shapes take raw values, not exponents")
    if yardstick == "METR HORIZON":
        # The ceiling line must sit at Claude 3.7 Sonnet's own METR value —
        # raw, unlogged — while its label sits at the same level in exponents.
        ceiling = next(r["metr_horizon_min_p50"]
                       for r in wager.load_timeline()
                       if r["model"] == "claude-3-7-sonnet")
        assert any(abs(y - ceiling) < 1e-9 for y in shapes), (
            f"ceiling line not at {ceiling} min: shapes={shapes}")
        assert any(abs(y - math.log10(ceiling)) < 1e-9 for y in annots), (
            f"ceiling label not at log10({ceiling}): annotations={annots}")


def test_rate_card_boots_through_the_router():
    app = run(RATE_CARD)
    assert app.get("dataframe"), "the rate card rendered no ledger"


def test_rate_card_still_reads_url_params():
    """Every control is URL-bound; st.navigation must not break that. The
    preset has to actually apply, not merely survive in the URL."""
    app = run(RATE_CARD, preset="CODING AGENT")
    assert app.session_state["preset"] == "CODING AGENT"
    applied = {w.label: w.value for w in app.number_input}
    assert applied, "no workload inputs rendered"

    default = run(RATE_CARD)
    assert default.session_state["preset"] == "CHATBOT"
    assert {w.label: w.value for w in default.number_input} != applied


def widget_labels(app: AppTest) -> set:
    return {element.label
            for group in (app.segmented_control, app.pills, app.selectbox,
                          app.text_input, app.multiselect)
            for element in group}


# The control each mode owns, and by ownership does not lend to the others.
MODE_CONTROL = {"RECOMMEND": "OPTIMIZE FOR", "MATCH": "MATCH THIS MODEL",
                "LOOK UP": "SEARCH"}


@pytest.mark.parametrize("mode", list(MODE_CONTROL))
def test_each_mode_renders_only_its_own_controls(mode):
    """A mode that renders another mode's control asks a question it has no
    use for — the whole point of splitting the page in three."""
    app = run(RATE_CARD, mode=mode)
    assert app.session_state["mode"] == mode
    assert app.get("dataframe"), "the mode rendered no ledger"
    labels = widget_labels(app)
    assert MODE_CONTROL[mode] in labels
    for other, control in MODE_CONTROL.items():
        if other != mode:
            assert control not in labels, control
    # Unscored models live in LOOK UP; the scope toggle is gone from the rest.
    assert "ALL MODELS" not in [t.label for t in app.toggle]


def test_recommend_is_where_a_first_visit_lands():
    app = run(RATE_CARD)
    assert app.session_state["mode"] == "RECOMMEND"


@pytest.mark.parametrize("mode", list(MODE_CONTROL))
def test_the_mode_travels_in_the_url(mode):
    """A shared link opens the mode it was copied from, and keeps carrying
    it. Repeatable widgets read back as lists, mode included."""
    value = run(RATE_CARD, mode=mode).query_params["mode"]
    assert (value[-1] if isinstance(value, list) else value) == mode


def test_a_shared_match_link_reopens_the_same_comparison():
    """Mode, anchor, tolerance and currency together, since a shared link
    carries all of them at once or reproduces nothing."""
    anchor = run(RATE_CARD, mode="MATCH").selectbox[0].options[0]
    app = run(RATE_CARD, mode="MATCH", anchor=anchor, tol="5", ccy="INR")
    assert app.session_state["anchor"] == anchor
    assert app.session_state["tol"] == 5
    body = text_of(app)
    assert f"ANCHOR {anchor} −5 PTS" in body
    assert "FX USD→INR" in body


@pytest.mark.parametrize("label", list(RATE.OPTIMIZE_FOR))
def test_optimize_for_writes_the_weights_it_names(label):
    app = run(RATE_CARD, opt=label)
    weights = tuple(app.session_state[k] for k in RATE.WEIGHT_KEYS)
    assert weights == RATE.OPTIMIZE_FOR[label]
    assert app.session_state["opt"] == label


def test_the_weights_decide_what_optimize_for_reads():
    """The control describes the sliders, never the reverse: weights that
    spell one of the four read as it, and weights that spell none read as
    CUSTOM rather than leaving a stale label claiming otherwise."""
    named = run(RATE_CARD, w_smart="2", w_cheap="5", w_fast="1")
    assert named.session_state["opt"] == "CHEAPEST"
    custom = run(RATE_CARD, w_smart="1", w_cheap="1", w_fast="1")
    assert custom.session_state["opt"] == RATE.CUSTOM
    # A preset sets weights of its own, and while they stand untouched the
    # control is the preset's to describe rather than the sliders'.
    coding = run(RATE_CARD, preset="CODING AGENT")
    assert coding.session_state["opt"] is None
    assert "AS SET BY CODING AGENT" in text_of(coding)


def test_the_verdict_leaves_the_fit_number_to_the_table():
    """FIT is a percentile blend over whatever is in view, so it moves when
    the filters do. The reasons under it do not."""
    app = run(RATE_CARD)
    line = next(str(m.value) for m in app.markdown
                if str(m.value).startswith("**VERDICT**"))
    assert "FIT" not in line


def test_editing_a_preset_says_so_and_offers_the_way_back():
    app = run(RATE_CARD)
    assert "PRESET MODIFIED" not in text_of(app)
    calls = next(w for w in app.number_input if w.label == "API CALLS")
    calls.set_value(calls.value * 5).run()
    assert "PRESET MODIFIED" in text_of(app)
    reset = next(b for b in app.button if b.label == "RESET TO PRESET")
    reset.click().run()
    assert app.session_state["api_calls"] == RATE.PRESETS["CHATBOT"]["values"]["api_calls"]
    assert "PRESET MODIFIED" not in text_of(app)


def test_look_up_reaches_the_models_nothing_else_scores():
    app = run(RATE_CARD, mode="LOOK UP")
    ledger = app.dataframe[0].value
    assert (ledger["intelligence"] == "—").any(), (
        "LOOK UP is the only mode that carries unscored models")


def test_look_up_renders_missing_metrics_as_em_dashes():
    """A float NaN cell reaches the data grid as the literal word "None". Not
    every model is scored on every axis and AA has measured the speed of only
    some of them, so the display frame formats those cells and the grid never
    sees a blank. The numeric columns the ranking and the charts read are a
    different frame and keep their NaNs."""
    app = run(RATE_CARD, mode="LOOK UP")
    ledger = app.dataframe[0].value
    assert "None" not in ledger.to_string()
    for column in ("intelligence", "speed", "usage_b"):
        assert (ledger[column] == "—").any(), column
        assert ledger[column].str.match(r"^(\d[\d,]*(\.\d)?|—)$").all(), column


def test_a_match_anchor_with_no_score_on_the_axis_gives_no_verdict():
    """gpt-5-nano carries an intelligence index and no coding one. Asked to
    match it on CODE there is no floor to apply, so the whole catalog is in
    view — naming its cheapest row would present an unfiltered ranking as a
    match."""
    on_axis = run(RATE_CARD, mode="MATCH", anchor="gpt-5-nano", axis="INT")
    assert [m for m in on_axis.markdown if str(m.value).startswith("## ▸")]

    off_axis = run(RATE_CARD, mode="MATCH", anchor="gpt-5-nano", axis="CODE")
    assert off_axis.session_state["anchor"] == "gpt-5-nano"
    assert not [m for m in off_axis.markdown if str(m.value).startswith("## ▸")]
    assert "no CODE score" in " ".join(str(i.value) for i in off_axis.info)

    # The options are the models the active axis scores — plus the one the
    # link carried in, which has to survive long enough to be explained.
    options = next(s for s in off_axis.selectbox
                   if s.label == "MATCH THIS MODEL").options
    assert "gpt-5-nano" in options
    assert "gemini-2.5-flash-lite" not in options


def speed_frame(rows: list) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["key", "intelligence", "total_usd", "speed"])
    return df.sort_values("total_usd").reset_index(drop=True)


def test_an_unmeasured_speed_is_disclosed_rather_than_renormalized():
    """FIT scores a dimension nobody measured as zero — being unmeasured is
    not a selling point. The cost is that a model beating the pick on both
    score and price can still rank below it, so the page names it instead of
    letting the ranking assert something the data does not."""
    df = speed_frame([
        ("the-pick", 50.0, 4.0, 120.0),
        ("unmeasured", 54.0, 2.0, float("nan")),
    ])
    pick = df[df["key"] == "the-pick"].iloc[0]
    rival = df[df["key"] == "unmeasured"].iloc[0]

    assert RATE.speed_penalized(df, pick, "intelligence", 1)["key"] == "unmeasured"
    # No FAST weight, no penalty, nothing to disclose.
    assert RATE.speed_penalized(df, pick, "intelligence", 0) is None
    # Losing on cost or on score is an ordinary tradeoff, not this case.
    dearer = speed_frame([("the-pick", 50.0, 4.0, 120.0),
                          ("dearer", 54.0, 9.0, float("nan"))])
    assert RATE.speed_penalized(dearer, pick, "intelligence", 1) is None

    assert RATE._tradeoff(rival, pick, "intelligence", "INT", 1).endswith(
        "· SPEED UNMEASURED")
    assert "SPEED UNMEASURED" not in RATE._tradeoff(
        rival, pick, "intelligence", "INT", 0)


def optimize_control(app: AppTest):
    return next(c for c in app.segmented_control if c.label == "OPTIMIZE FOR")


def test_a_preset_owns_the_optimize_control_until_something_moves():
    """CHATBOT's priorities spell none of the four named options. Reading
    CUSTOM at a visitor who has customised nothing is the control describing
    the sliders instead of the use case that set them."""
    for app in (run(RATE_CARD, preset="CHATBOT"), run(RATE_CARD)):
        assert app.session_state["opt"] is None
        assert "AS SET BY CHATBOT" in text_of(app)
        assert RATE.CUSTOM not in optimize_control(app).options

    picked = optimize_control(app).set_value("CHEAPEST").run()
    assert picked.session_state["opt"] == "CHEAPEST"
    assert tuple(picked.session_state[k] for k in RATE.WEIGHT_KEYS) == \
        RATE.OPTIMIZE_FOR["CHEAPEST"]
    assert "AS SET BY CHATBOT" not in text_of(picked)


def test_preset_modified_lands_in_the_run_that_moves_a_weight():
    """Divergence is read after every control that can write a preset value.
    Read inside the pills, which run first, the chip describes the previous
    click."""
    app = run(RATE_CARD, preset="CODING AGENT")
    assert "PRESET MODIFIED" not in text_of(app)
    moved = optimize_control(app).set_value("CHEAPEST").run()
    assert "PRESET MODIFIED" in text_of(moved)


def test_the_workload_chip_reads_as_a_sentence():
    """Calls first, then what one call looks like. An "×" between two token
    counts invites reading them as a total."""
    values = RATE.PRESETS["CHATBOT"]["values"]
    assert (f"{values['api_calls']:,} CALLS · ~{values['input_tokens']:,} IN / "
            f"{values['output_tokens']:,} OUT TOKENS EACH") in text_of(
        run(RATE_CARD))


def alt_frame(rows: list) -> pd.DataFrame:
    """A cost-sorted catalog slice — the shape alternatives() is handed."""
    df = pd.DataFrame(rows, columns=["key", "intelligence", "total_usd"])
    return df.sort_values("total_usd").reset_index(drop=True)


def alternatives_of(df: pd.DataFrame):
    pick = df[df["key"] == "the-pick"].iloc[0]
    return RATE.alternatives(df, pick, "intelligence")


def test_the_alternatives_name_a_tradeoff_or_nothing():
    """Cheapest near-equal below the pick, cheapest clear upgrade above it —
    and no card at all when neither exists, since an alternative that is not
    one puts a second winner under a one-winner verdict."""
    cheaper, capable = alternatives_of(alt_frame([
        ("too-dim", 30.0, 1.0),
        ("near-equal-cheaper", 46.0, 2.0),
        ("the-pick", 50.0, 4.0),
        ("cheap-upgrade", 53.0, 5.0),
        ("pricey-upgrade", 55.0, 9.0),
    ]))
    assert cheaper["key"] == "near-equal-cheaper"
    assert capable["key"] == "cheap-upgrade"

    # The bands are exact: 5 points below still qualifies, 5.1 does not, and
    # 3 points above is the smallest gain worth calling an upgrade.
    cheaper, capable = alternatives_of(alt_frame([
        ("just-outside", 44.9, 1.0),
        ("just-inside", 45.0, 3.0),
        ("the-pick", 50.0, 4.0),
        ("not-enough-gain", 52.9, 6.0),
    ]))
    assert cheaper["key"] == "just-inside"
    assert capable is None

    # Cheaper and better is an upgrade, not a cheaper option.
    cheaper, capable = alternatives_of(alt_frame([
        ("strictly-better", 54.0, 2.0),
        ("the-pick", 50.0, 4.0),
    ]))
    assert cheaper is None
    assert capable["key"] == "strictly-better"

    assert alternatives_of(alt_frame([("the-pick", 50.0, 4.0)])) == (None, None)


def test_wager_page_has_no_stale_hardcoded_counts(page):
    body = text_of(page)
    assert "NINE MATCHED PAIRS" not in body
    assert "LAST FIVE UNDER" not in body
    a = wager.method_a(wager.load_timeline())
    assert f"{a['n_pairs']} MATCHED PAIRS FROM {a['n_matchers']}" in body


def test_countdowns_are_relative_to_today(page, frozen):
    """A hardcoded 'in N days' would be wrong the day after it was written."""
    due = dt.date.fromisoformat(frozen["predictions"]["method_b"]["date"])
    days = (due - dt.date.today()).days
    assert f"IN {days:,} DAYS" in text_of(page)
