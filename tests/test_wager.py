"""
The frozen wager, pinned.

`wager.json` is what the scheduled emails, the README table and the workflow's
cron were all built around. It is a snapshot of an arithmetic that runs on a
hand-curated CSV, and the failure mode is silent: a single edited cell can move
a milestone, drop a lag pair, and shift both dates without anything complaining.

So these tests do two jobs. They pin the numbers the wager was published with —
if one moves, that is a decision, not a diff — and they check that recomputing
from `timeline.csv` today still reproduces the frozen document exactly. When the
wager is deliberately re-frozen, the expected values below move with it, and so
must the cron day numbers, which are also checked here.
"""

import datetime as dt
import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import wager  # noqa: E402

ROOT = pathlib.Path(wager.ROOT)

# Frontier milestone -> (matching bottom-tier model, lag in months to 2dp).
EXPECTED_PAIRS = {
    "gpt-4": ("claude-3-5-haiku", 19.75),
    "claude-3-opus": ("claude-3-5-haiku", 8.05),
    "o1-preview": ("gpt-5-nano", 10.81),
    "o1": ("claude-haiku-4.5", 9.92),
    "claude-3-7-sonnet": ("claude-haiku-4.5", 7.66),
    "o3": ("gpt-5.4-nano", 11.01),
    "claude-opus-4": ("gpt-5.4-nano", 9.82),
    "gpt-5": ("gpt-5.4-nano", 7.29),
    "claude-opus-4.5": ("gpt-5.6-luna", 7.46),
    "claude-opus-4.6": ("gpt-5.6-luna", 5.06),
}

EXPECTED_MEDIAN_LAG = 8.94
EXPECTED_METHOD_A = dt.date(2027, 3, 8)
EXPECTED_METHOD_B = dt.date(2027, 1, 10)
EXPECTED_SLOWEST = dt.date(2027, 6, 27)
EXPECTED_MIDPOINT = dt.date(2026, 10, 21)


@pytest.fixture(scope="module")
def rows():
    return wager.load_timeline()


@pytest.fixture(scope="module")
def preds(rows):
    return wager.predictions(rows)


@pytest.fixture(scope="module")
def frozen():
    return wager.load_wager()


def test_lag_pairs(rows):
    """Every matched pair, to the hundredth of a month. This is the test that
    catches a timeline.csv edit changing which releases count as milestones."""
    pairs = {p["frontier"]: (p["matched_by"], round(p["lag_months"], 2))
             for p in wager.method_a(rows)["pairs"]}
    assert pairs == EXPECTED_PAIRS


def test_median_and_dates(preds):
    assert round(preds["a"]["median_lag_months"], 2) == EXPECTED_MEDIAN_LAG
    assert preds["a"]["date"] == EXPECTED_METHOD_A
    assert preds["b"]["date"] == EXPECTED_METHOD_B
    assert preds["slow"]["date"] == EXPECTED_SLOWEST
    assert preds["earliest"] == EXPECTED_METHOD_B


def test_method_b_starts_at_the_baseline_release(rows, preds):
    """Not at the freeze date: the price of a capability starts falling when
    the capability ships, not when this repo reads a feed."""
    assert preds["b"]["from_date"] == wager.baseline_row(rows)["release_date"]
    assert preds["b"]["from_date"] == dt.date(2026, 6, 9)


def test_midpoint(preds):
    assert wager.midpoint(preds["earliest"]) == EXPECTED_MIDPOINT


def test_effective_sample_is_smaller_than_the_pair_count(preds):
    a = preds["a"]
    assert a["n_pairs"] == 10
    assert a["n_matchers"] == 5
    assert a["n_priced"] == 9
    assert a["n_under_price_bar"] == 3


def test_frozen_document_matches_a_fresh_recomputation(preds, frozen):
    """The drift check. The page renders live numbers and the emails render
    frozen ones; while these agree, both tell the same story."""
    a, b = frozen["predictions"]["method_a"], frozen["predictions"]["method_b"]
    assert a["date"] == str(preds["a"]["date"])
    assert b["date"] == str(preds["b"]["date"])
    assert frozen["predictions"]["slowest_trend"]["date"] == str(preds["slow"]["date"])
    assert frozen["predictions"]["earliest"] == str(preds["earliest"])
    assert frozen["predictions"]["latest"] == str(preds["latest"])
    assert a["median_lag_months"] == round(preds["a"]["median_lag_months"], 2)
    assert a["mean_lag_months"] == round(preds["a"]["mean_lag_months"], 2)
    assert a["n_pairs"] == preds["a"]["n_pairs"]
    assert a["n_distinct_matchers"] == preds["a"]["n_matchers"]
    assert [(p["frontier"], p["matched_by"], p["lag_months"]) for p in a["pairs"]] == \
        [(p["frontier"], p["matched_by"], round(p["lag_months"], 2))
         for p in preds["a"]["pairs"]]


def test_sends_are_the_midpoint_and_the_earlier_date(frozen, preds):
    due = {s["id"]: s["due"] for s in frozen["sends"]}
    assert due["midpoint-check"] == str(wager.midpoint(preds["earliest"]))
    assert due["wager-letter"] == str(preds["earliest"])
    for send in frozen["sends"]:
        assert send["due"] in send["issue_title"]


def test_cron_fires_on_the_due_dates(frozen):
    """A monthly cron would deliver a letter that opens "The date is today" on
    the wrong day eleven times out of twelve."""
    workflow = (ROOT / ".github" / "workflows" / "wager-email.yml").read_text()
    cron = re.search(r'cron:\s*"([^"]+)"', workflow).group(1)
    days = set(cron.split()[2].split(","))
    assert days == {str(int(s["due"].split("-")[2])) for s in frozen["sends"]}


def test_resolution_status_matches_the_frozen_status(rows, frozen):
    res = wager.resolution(rows)
    status = frozen["resolution"]["status_at_freeze"]
    assert res["resolved"] is status["resolved"] is False
    assert res["best_bottom"] == status["closest_bottom_model"]
    assert res["best_bottom_aa"] == status["closest_bottom_aa"]
    assert round(res["gap_points"], 1) == status["gap_points"]
    assert res["metr_measurable"] == status["bottom_models_with_a_metr_horizon"]
    assert res["price_cap"] == frozen["resolution"]["price_cap_blended_per_mtok"]


def test_every_timeline_row_carries_a_source(rows):
    for r in rows:
        assert r["source_url"].startswith("http"), r["model"]
        if r["aa_intel"] is not None:
            assert r["aa_version"], r["model"]
            assert r["aa_source"].startswith("http"), r["model"]
        if r["metr_horizon_min_p50"] is not None:
            assert r["metr_key"] and r["metr_source"].startswith("http"), r["model"]
