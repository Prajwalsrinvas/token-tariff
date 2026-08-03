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
import json
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
EXPECTED_DEADLINE = dt.date(2027, 6, 27)

# Curated open-weights flagship high-water marks. The third item is the exact
# key in the committed feed named by the row's aa_version.
EXPECTED_OPEN = {
    "deepseek-r1": (dt.date(2025, 1, 20), 18.5,
                    "deepseek/deepseek-r1"),
    "command-a": (dt.date(2025, 3, 13), 22.5, "cohere/command-a"),
    "gpt-oss-120b": (dt.date(2025, 8, 5), 23.8,
                     "openai/gpt-oss-120b"),
    "deepseek-v3.1-terminus": (dt.date(2025, 9, 22), 30.4,
                               "deepseek/deepseek-v3.1-terminus"),
    "deepseek-v3.2": (dt.date(2025, 12, 1), 32.0,
                      "deepseek/deepseek-v3.2"),
    "glm-4.7": (dt.date(2025, 12, 22), 33.7, "z-ai/glm-4.7"),
    "kimi-k2.5": (dt.date(2026, 1, 27), 35.4,
                  "moonshotai/kimi-k2.5"),
    "glm-5": (dt.date(2026, 2, 11), 39.5, "glm-5"),
    "glm-5.1": (dt.date(2026, 4, 7), 40.2, "z-ai/glm-5.1"),
    "kimi-k2.6": (dt.date(2026, 4, 20), 44.2,
                  "moonshotai/kimi-k2.6"),
    "deepseek-v4-pro": (dt.date(2026, 4, 24), 44.3,
                        "deepseek/deepseek-v4-pro"),
    "minimax-m3": (dt.date(2026, 5, 31), 44.4,
                   "minimax/minimax-m3"),
    "glm-5.2": (dt.date(2026, 6, 16), 51.1, "z-ai/glm-5.2"),
    "kimi-k3": (dt.date(2026, 7, 26), 57.1,
                "moonshotai/kimi-k3"),
}


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


def test_open_rows_are_sourced_non_binding_high_water_marks(rows):
    """The watch is a sequence, not an open-model catalog. Every row improves
    on the prior open flagship, has no invented price, and reproduces a score
    that already exists in the committed feed its version names."""
    benchmark = json.loads((ROOT / "benchmark_scores.json").read_text())
    aa = json.loads((ROOT / "aa_models.json").read_text())
    open_rows = [r for r in rows if r["tier"] == "open"]

    assert {r["model"] for r in open_rows} == set(EXPECTED_OPEN)
    assert [r["aa_intel"] for r in open_rows] == sorted(
        r["aa_intel"] for r in open_rows)
    for row in open_rows:
        date, score, feed_key = EXPECTED_OPEN[row["model"]]
        assert (row["release_date"], row["aa_intel"]) == (date, score)
        assert all(row[col] is None for col in (
            "launch_price_in", "launch_price_out", "current_price_in",
            "current_price_out"))
        assert "Non-binding" in row["notes"]
        if row["aa_version"] == "2026-08-01":
            assert benchmark[feed_key]["intelligence"] == score
        else:
            assert row["aa_version"] == "≤2026-07-05"
            assert aa[feed_key]["intelligence"] == score


def test_open_rows_are_inert_to_every_wager_derivation(rows, frozen):
    """Adding the non-binding watch cannot move the contract indirectly.
    Exercise every derived object over the full spine and over the exact same
    spine with `open` removed; explicit frontier/bottom filters make them equal."""
    binding_rows = [r for r in rows if r["tier"] != "open"]

    assert wager.milestones(rows) == wager.milestones(binding_rows)
    assert wager.method_a(rows) == wager.method_a(binding_rows)
    assert wager.predictions(rows) == wager.predictions(binding_rows)
    assert wager.resolution(rows) == wager.resolution(binding_rows)

    live = wager.predictions(rows)
    assert str(live["a"]["date"]) == frozen["predictions"]["method_a"]["date"]
    assert str(live["b"]["date"]) == frozen["predictions"]["method_b"]["date"]
    assert str(live["slow"]["date"]) == \
        frozen["predictions"]["slowest_trend"]["date"]
    assert str(wager.DEADLINE) == frozen["deadline"]


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


def test_sends_are_the_midpoint_the_earlier_date_and_the_reading(frozen, preds):
    """The last send is the morning after the cutoff, not the cutoff itself.
    Everything that can count is public by 23:59 UTC on the deadline, so a
    letter that lands that morning asks for a reading against a question still
    hours from closing."""
    due = {s["id"]: s["due"] for s in frozen["sends"]}
    assert due["midpoint-check"] == str(wager.midpoint(preds["earliest"]))
    assert due["wager-letter"] == str(preds["earliest"])
    assert due["deadline-resolution"] == str(wager.DEADLINE + dt.timedelta(days=1))
    for send in frozen["sends"]:
        assert send["due"] in send["issue_title"]


def test_every_send_has_a_body_that_renders(frozen):
    """A send with no template raises at the moment it comes due, months after
    the mistake, in a job nobody is watching. Rendering each one here fails
    instead on the missing template and on any placeholder the values dict
    does not carry."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import wager_check  # noqa: PLC0415

    assert set(wager_check.TEMPLATES) == {s["id"] for s in frozen["sends"]}
    for send in frozen["sends"]:
        body = wager_check.render(send, frozen, dt.date.fromisoformat(send["due"]))
        assert send["due"] in body or frozen["frozen_on"] in body
        assert "{" not in body, send["id"]


def test_the_deadline_send_never_declares_from_live_data(frozen, monkeypatch):
    """Past the cutoff only the recorded artifact under data/history/ may say
    YES or NO. Even a live recomputation that resolves must reach the deadline
    email as VERIFYING while nothing is recorded."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import wager_check  # noqa: PLC0415

    doctored = wager.load_timeline()
    for r in doctored:
        if r["tier"] == "bottom":
            r["aa_intel"] = 99.0
    assert wager.resolution(doctored)["resolved"] is True
    monkeypatch.setattr(wager_check.wager, "load_timeline", lambda: doctored)
    monkeypatch.setattr(wager_check.wager, "recorded_resolution", lambda: None)
    send = next(s for s in frozen["sends"] if s["id"] == "deadline-resolution")
    body = wager_check.render(send, frozen, dt.date.fromisoformat(send["due"]))
    assert "VERIFYING" in body
    assert "already resolved YES" not in body

    monkeypatch.setattr(
        wager_check.wager, "recorded_resolution",
        lambda: {"resolved": True, "resolved_by": "example-model",
                 "read_from": "data/history/2027-06-28/"})
    body = wager_check.render(send, frozen, dt.date.fromisoformat(send["due"]))
    assert "recorded resolution is YES — example-model" in body


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


def test_the_deadline_is_one_date_in_two_files(frozen):
    """`wager.DEADLINE` is what the page and the status computation read;
    `wager.json` is what the letter, the README and any future arbiter quote.
    A deadline that differs between them is the one drift a reader cannot
    see, so the constant is the source of truth and the document is pinned to
    it."""
    assert wager.DEADLINE == EXPECTED_DEADLINE
    assert frozen["deadline"] == str(wager.DEADLINE)
    assert frozen["resolution"]["deadline"] == str(wager.DEADLINE)
    assert str(wager.DEADLINE) in frozen["claim"] or (
        f"{wager.DEADLINE:%B} {wager.DEADLINE.day}, {wager.DEADLINE.year}"
        in frozen["claim"])


def test_the_deadline_is_where_the_slowest_trend_lands(preds, frozen):
    """The bound is not a round number picked for feel: it is the date the
    slowest decline Epoch fitted reaches a tenfold fall, so a trend slower
    than anything measured would still have resolved by it."""
    assert preds["slow"]["date"] == wager.DEADLINE
    assert frozen["predictions"]["slowest_trend"]["date"] == str(wager.DEADLINE)
    assert preds["latest"] < wager.DEADLINE


def test_the_document_is_v2_with_a_dated_amendment(frozen):
    assert frozen["version"] == 2
    assert dt.date.fromisoformat(frozen["amended_on"]) >= \
        dt.date.fromisoformat(frozen["frozen_on"])
    amendment = frozen["amendment"]
    assert len(amendment["changed"]) == 4
    assert amendment["why"] and amendment["v1"]
    # The forecast is not what the amendment touched.
    assert frozen["predictions"]["method_a"]["date"] == str(EXPECTED_METHOD_A)
    assert frozen["predictions"]["method_b"]["date"] == str(EXPECTED_METHOD_B)


def test_the_index_arm_is_the_only_binding_one(rows, frozen):
    """METR is a secondary check. Even a measured entry-level model far above
    the proxy horizon leaves the wager open — only the index-plus-price rule
    settles it."""
    rules = frozen["resolution"]
    assert rules["binding_arms"] == 1
    assert rules["secondary_check"]["binding"] is False

    doctored = [dict(r) for r in rows]
    for r in doctored:
        if r["tier"] == "bottom":
            r["metr_horizon_min_p50"] = 10_000.0
    res = wager.resolution(doctored)
    assert res["metr_measurable"] > 0
    assert res["resolved"] is False


def _blanked_baseline(rows, **blanks):
    doctored = [dict(r) for r in rows]
    for r in doctored:
        if r["model"] == wager.BASELINE:
            r.update(blanks)
    return doctored


def qualifying(rows, **overrides):
    """An entry-level row that clears both terms — the shape a YES arrives in.
    Built from a real row so every column the arm reads is present."""
    base = wager.baseline_row(rows)
    row = dict(next(r for r in rows if r["tier"] == "bottom"))
    row.update(model="doctored-entry-level", vendor="Google",
               release_date=wager.DEADLINE - dt.timedelta(days=1),
               aa_intel=base["aa_intel"],
               current_price_in=0.5, current_price_out=0.5)
    row.update(overrides)
    return row


def test_the_price_ceiling_is_one_number_in_two_files(rows, frozen):
    """The ceiling is a frozen constant, not a tenth of whatever the baseline
    costs today. Derived from the live price it would be a bar the other side
    can move by repricing the baseline, which is the one term a wager cannot
    leave adjustable."""
    assert wager.PRICE_CAP_BLENDED == \
        frozen["resolution"]["price_cap_blended_per_mtok"]
    assert wager.resolution(rows)["price_cap"] == wager.PRICE_CAP_BLENDED

    repriced = _blanked_baseline(rows, current_price_in=100.0,
                                 current_price_out=500.0)
    res = wager.resolution(repriced)
    assert res["price_cap"] == wager.PRICE_CAP_BLENDED
    assert res["baseline_price"] == 200.0  # reported, and not the ceiling


def test_only_an_eligible_vendors_entry_slot_can_settle_it(rows, frozen):
    """The vendor list is frozen with the terms: a fourth lab getting there
    first is a different claim."""
    assert list(wager.ELIGIBLE_VENDORS) == \
        frozen["resolution"]["eligible_vendors"]
    assert wager.resolution(rows + [qualifying(rows)])["resolved"] is True
    outsider = wager.resolution(rows + [qualifying(rows, vendor="Meta")])
    assert outsider["resolved"] is False
    assert outsider["resolved_by"] is None


def test_a_model_released_after_the_deadline_cannot_settle_it(rows):
    """The bar closes on the deadline. A row dated after it is evidence about
    a different question."""
    late = qualifying(rows,
                      release_date=wager.DEADLINE + dt.timedelta(days=1))
    assert wager.resolution(rows + [late])["resolved"] is False
    on_time = qualifying(rows, release_date=wager.DEADLINE)
    assert wager.resolution(rows + [on_time])["resolved"] is True


def test_a_missing_baseline_price_costs_a_figure_not_the_arm(rows):
    """With the ceiling frozen, the baseline's own price is information the
    page quotes. Losing it loses a sentence, not the rule."""
    res = wager.resolution(_blanked_baseline(
        rows, current_price_in=None, current_price_out=None))
    assert res["baseline_price"] is None
    assert res["price_cap"] == wager.PRICE_CAP_BLENDED
    assert res["unevaluable"] is None
    assert res["resolved"] is False


def test_a_missing_baseline_index_cannot_be_evaluated(rows):
    """No target index means no bar to clear, which is half the rule
    unreadable. That is a reported reason, not a comparison against None."""
    res = wager.resolution(_blanked_baseline(rows, aa_intel=None))
    assert res["resolved"] is False
    assert res["resolved_by"] is None
    assert res["gap_points"] is None
    assert wager.BASELINE in res["unevaluable"]


def test_the_recorded_resolution_is_the_newest_one_written(tmp_path):
    """Past the cutoff the page reads this file rather than recomputing, so
    which file wins is part of the contract: the newest snapshot carrying one,
    and None while none does."""
    assert wager.recorded_resolution(tmp_path) is None
    for date in ("2027-06-28", "2027-07-05"):
        (tmp_path / date).mkdir()
    assert wager.recorded_resolution(tmp_path) is None  # a snapshot, no reading

    (tmp_path / "2027-06-28" / "resolution.json").write_text(json.dumps(
        {"resolved": False, "resolved_by": None,
         "read_from": "data/history/2027-06-28"}))
    assert wager.recorded_resolution(tmp_path)["resolved"] is False

    (tmp_path / "2027-07-05" / "resolution.json").write_text(json.dumps(
        {"resolved": True, "resolved_by": "gemini-4-flash-lite",
         "read_from": "data/history/2027-07-05"}))
    recorded = wager.recorded_resolution(tmp_path)
    assert recorded["resolved"] is True
    assert recorded["resolved_by"] == "gemini-4-flash-lite"


def test_nothing_is_recorded_yet():
    """The state the page has to render today: snapshots exist, no reading has
    been taken, and that is not an error."""
    assert wager.latest_snapshot() is not None
    assert wager.recorded_resolution() is None


def test_the_wager_never_says_lineup_bottom(frozen):
    """The amendment replaced the wording everywhere, including in its own
    record of what it replaced — the page renders that record. `bottom`
    survives only as the CSV's tier value and the key names built on it."""
    assert "lineup-bottom" not in json.dumps(frozen).lower()
    assert "entry-level" in frozen["claim"]


def test_every_timeline_row_carries_a_source(rows):
    for r in rows:
        assert r["source_url"].startswith("http"), r["model"]
        if r["aa_intel"] is not None:
            assert r["aa_version"], r["model"]
            assert r["aa_source"].startswith("http"), r["model"]
        if r["metr_horizon_min_p50"] is not None:
            assert r["metr_key"] and r["metr_source"].startswith("http"), r["model"]
