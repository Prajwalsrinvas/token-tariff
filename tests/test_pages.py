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
import math
import pathlib
import sys

import pytest
from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import wager  # noqa: E402

ROOT = pathlib.Path(wager.ROOT)
WAGER_PAGE = str(ROOT / "pages_src" / "wager_page.py")
RATE_CARD = str(ROOT / "app.py")
TIMEOUT = 90


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
    """The capability chart as a Plotly figure, built by the page's own code.

    The page module is imported once (which runs it bare, no Streamlit
    runtime), with st.plotly_chart swapped for a collector."""
    import importlib.util

    import streamlit as st

    captured = []
    original, st.plotly_chart = st.plotly_chart, lambda fig, **kw: captured.append(fig)
    try:
        spec = importlib.util.spec_from_file_location("wager_page", WAGER_PAGE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        rows = wager.load_timeline()
        palette = st.get_option("theme.chartCategoricalColors")
        module.capability_chart(
            module.timeline_frame(rows), yardstick,
            {"FRONTIER": palette[0], "LINEUP BOTTOM": palette[1]})
    finally:
        st.plotly_chart = original
    return captured[-1]


def text_of(app: AppTest) -> str:
    """Every string the page rendered, in one blob."""
    parts = [el.value for el in app.markdown]
    parts += [el.value for el in app.caption]
    return "\n".join(str(p) for p in parts)


def test_banner_shows_every_frozen_date(page, frozen):
    body = text_of(page)
    preds = frozen["predictions"]
    for date in (preds["method_a"]["date"], preds["method_b"]["date"],
                 preds["slowest_trend"]["date"]):
        assert date in body, date
    midpoint = next(s["due"] for s in frozen["sends"]
                    if s["id"] == "midpoint-check")
    assert f"MIDPOINT CHECK · {midpoint}" in body


def test_claim_is_rendered_from_the_frozen_wager(page, frozen):
    assert f"**{frozen['claim']}**" in text_of(page)


def test_slowest_trend_is_not_called_a_bound(page):
    body = text_of(page)
    assert "SLOWEST HISTORICAL TREND" in body
    assert "PESSIMISTIC BOUND" not in body


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
