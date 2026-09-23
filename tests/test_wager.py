"""
The frozen wager, pinned.

`wager.json` is what the scheduled emails, the README table and the workflow's
cron were all built around. It is a snapshot of an arithmetic that runs on a
hand-curated CSV, and the failure mode is silent: a single edited cell can move
a milestone, drop a lag pair, and shift both dates without anything complaining.

So these tests pin two things, separately. The numbers the wager was published
with (`FROZEN_*`, read from `wager.json`) never move unless the wager is
deliberately re-frozen, and then the cron day numbers move with them. What the
live `timeline.csv` recomputes to today (`LIVE_*`) moves on every refresh that
changes a milestone — each refresh updates those pins on purpose, so a moved
number is still a decision rather than a diff. The two are allowed to disagree:
that disagreement is what the page's drift badge shows. The dates that do not
depend on the timeline at all — the price-decline lens, the slowest trend, the
deadline and the sends — must still agree with the frozen document exactly.
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

# As published in wager.json on the freeze. These do not move with the data.
FROZEN_MEDIAN_LAG = 8.94
FROZEN_METHOD_A = dt.date(2027, 3, 8)

# The AA snapshot every aa_intel in timeline.csv is read from. Milestones
# compare scores across rows, so the column is one index version or nothing.
LIVE_AA_SNAPSHOT = "2026-09-23"

# Live: frontier milestone -> (matching entry-level model, lag in months to
# 2dp), recomputed from timeline.csv on the AA v4.3 snapshot.
LIVE_PAIRS = {
    "gpt-4": ("gpt-4o-mini", 16.16),
    "claude-3-opus": ("claude-3-5-haiku", 8.05),
    "o1-preview": ("gpt-5-nano", 10.81),
    "o1": ("claude-haiku-4.5", 9.92),
    "claude-3-7-sonnet": ("gpt-5.4-nano", 12.68),
    "o3": ("gpt-5.4-nano", 11.01),
    "claude-opus-4": ("gpt-5.4-nano", 9.82),
    "gpt-5": ("gpt-5.6-luna", 11.04),
    "claude-opus-4.5": ("gpt-5.6-luna", 7.46),
    "claude-opus-4.6": ("gpt-5.6-luna", 5.06),
}

LIVE_MEDIAN_LAG = 10.37
LIVE_METHOD_A = dt.date(2027, 4, 20)
EXPECTED_METHOD_B = dt.date(2027, 1, 10)
EXPECTED_SLOWEST = dt.date(2027, 6, 27)
EXPECTED_MIDPOINT = dt.date(2026, 10, 21)
EXPECTED_DEADLINE = dt.date(2027, 6, 27)

# Curated open-weights flagship high-water marks on the live snapshot. The
# third item is the model's slug in data/history/<aa_version>/aa_models.json.
EXPECTED_OPEN = {
    "deepseek-r1": (dt.date(2025, 1, 20), 11.4, "deepseek-r1-0120"),
    "gpt-oss-120b": (dt.date(2025, 8, 5), 11.6, "gpt-oss-120b"),
    "deepseek-v3.1-terminus": (dt.date(2025, 9, 22), 14.8,
                               "deepseek-v3-1-terminus-reasoning"),
    "deepseek-v3.2": (dt.date(2025, 12, 1), 21.5, "deepseek-v3-2-reasoning"),
    "glm-4.7": (dt.date(2025, 12, 22), 22.2, "glm-4-7"),
    "kimi-k2.5": (dt.date(2026, 1, 27), 23.5, "kimi-k2-5"),
    "glm-5": (dt.date(2026, 2, 11), 27.9, "glm-5"),
    "deepseek-v4-pro": (dt.date(2026, 4, 24), 30.4, "deepseek-v4-pro-0424"),
    "glm-5.2": (dt.date(2026, 6, 16), 33.7, "glm-5-2"),
    "kimi-k3": (dt.date(2026, 7, 26), 43.6, "kimi-k3"),
    "glm-5.3": (dt.date(2026, 8, 28), 44.8, "glm-5-3"),
    "mimo-v2.6-pro": (dt.date(2026, 9, 22), 46.3, "mimo-v2-6-pro"),
}


def aa_snapshot(version: str) -> dict:
    """slug -> intelligence index, from the raw AA API payload committed under
    data/history/. Read from the snapshot rather than the app's root cache,
    which the rate card rewrites whenever it fetches."""
    payload = json.loads(
        (ROOT / "data" / "history" / version / "aa_models.json").read_text())
    return {m["slug"]: m["evaluations"]["artificial_analysis_intelligence_index"]
            for m in payload["data"]}


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
    assert pairs == LIVE_PAIRS


def test_every_index_is_read_from_one_snapshot(rows):
    """Milestones compare aa_intel across rows, and AA rescales every model
    when its index version changes — v4.3 moved Fable 5 from 59.9 to 49.6.
    A column that mixes two versions puts two rulers on one axis, so a refresh
    re-reads every row or none."""
    versions = {r["aa_version"] for r in rows if r["aa_intel"] is not None}
    assert versions == {LIVE_AA_SNAPSHOT}
    scores = aa_snapshot(LIVE_AA_SNAPSHOT)
    assert scores["claude-fable-5"] == \
        wager.baseline_row(rows)["aa_intel"]


def test_median_and_dates(preds):
    assert round(preds["a"]["median_lag_months"], 2) == LIVE_MEDIAN_LAG
    assert preds["a"]["date"] == LIVE_METHOD_A
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
    assert a["n_matchers"] == 6
    assert a["n_priced"] == 9
    assert a["n_under_price_bar"] == 2


def test_open_rows_are_sourced_non_binding_high_water_marks(rows):
    """The watch is a sequence, not an open-model catalog. Every row improves
    on the prior open flagship, has no invented price, and reproduces a score
    that already exists in the committed feed its version names."""
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
        assert aa_snapshot(row["aa_version"])[feed_key] == score


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
    assert live["a"]["date"] == LIVE_METHOD_A
    assert str(live["b"]["date"]) == frozen["predictions"]["method_b"]["date"]
    assert str(live["slow"]["date"]) == \
        frozen["predictions"]["slowest_trend"]["date"]
    assert str(wager.DEADLINE) == frozen["deadline"]


def test_the_frozen_document_is_what_was_published(frozen):
    """The frozen historical-lag lens is a record, not a recomputation: it
    stays as published while the live one moves with the timeline. It must
    still be internally consistent — its median is the median of its own
    pairs, and its window is its own two dates."""
    a, b = frozen["predictions"]["method_a"], frozen["predictions"]["method_b"]
    assert a["date"] == str(FROZEN_METHOD_A)
    assert a["median_lag_months"] == FROZEN_MEDIAN_LAG
    lags = sorted(p["lag_months"] for p in a["pairs"])
    n = len(lags)
    assert n == a["n_pairs"]
    assert round((lags[n // 2 - 1] + lags[n // 2]) / 2, 2) == FROZEN_MEDIAN_LAG
    assert len({p["matched_by"] for p in a["pairs"]}) == a["n_distinct_matchers"]
    assert frozen["predictions"]["earliest"] == min(a["date"], b["date"])
    assert frozen["predictions"]["latest"] == max(a["date"], b["date"])


def test_a_tie_on_the_index_goes_to_the_cheaper_model(rows):
    """Two entry-level models at the same score are not equally close to a
    wager with a price term, so the cheaper one is the contender — in the
    scorecard and in every open milestone's near-miss."""
    doctored = [dict(r) for r in rows]
    top = max(r["aa_intel"] for r in doctored
              if r["tier"] == "bottom" and r["aa_intel"] is not None)
    twin = dict(next(r for r in doctored if r["tier"] == "bottom"))
    twin.update(model="doctored-twin", vendor="Google", aa_intel=top,
                release_date=dt.date(2026, 9, 1),
                current_price_in=0.01, current_price_out=0.01)
    doctored.append(twin)
    assert wager.resolution(doctored)["best_bottom"] == "doctored-twin"
    assert all(m["closest"] == "doctored-twin"
               for m in wager.milestones(doctored)
               if m["lag_months"] is None
               and m["frontier_date"] < twin["release_date"])


def test_the_timeline_independent_dates_still_recompute(preds, frozen):
    """The price-decline lens and the slowest trend read only the baseline's
    release date and Epoch's rates, so no timeline refresh can move them. If
    one of these differs, the frozen document is wrong, not stale."""
    b = frozen["predictions"]["method_b"]
    assert b["date"] == str(preds["b"]["date"])
    assert frozen["predictions"]["slowest_trend"]["date"] == str(preds["slow"]["date"])
    assert frozen["predictions"]["earliest"] == str(preds["earliest"])


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


def test_resolution_status_today_and_at_the_freeze(rows, frozen):
    """The freeze status is a record of the index as it stood then; the live
    status is the same reading on the current snapshot. On v4.3 the gap reads
    wider because AA's rescale compressed cheaper models harder."""
    status = frozen["resolution"]["status_at_freeze"]
    assert (status["closest_bottom_model"], status["closest_bottom_aa"],
            status["gap_points"]) == ("gpt-5.6-luna", 51.2, 8.7)

    res = wager.resolution(rows)
    assert res["resolved"] is status["resolved"] is False
    assert res["baseline_aa"] == 49.6
    # GPT-6 Luna ties GPT-5.6 Luna on the index at under half the price.
    assert res["best_bottom"] == "gpt-6-luna"
    assert res["best_bottom_price"] == 0.2
    assert res["best_bottom_aa"] == 37.3
    assert round(res["gap_points"], 1) == 12.3
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
    assert len(amendment["changed"]) == 5
    assert amendment["why"] and amendment["v1"]
    # The forecast is not what the amendment touched.
    assert frozen["predictions"]["method_a"]["date"] == str(FROZEN_METHOD_A)
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
    Built from a real row so every column the arm reads is present, and read in
    the baseline's own AA snapshot, since the arm compares inside one."""
    base = wager.baseline_row(rows)
    row = dict(next(r for r in rows if r["tier"] == "bottom"))
    row.update(model="doctored-entry-level", vendor="Google",
               release_date=wager.DEADLINE - dt.timedelta(days=1),
               aa_intel=base["aa_intel"], aa_version=base["aa_version"],
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


def test_a_candidate_read_in_another_snapshot_cannot_settle_it(rows):
    """The arm compares inside a single AA snapshot. Artificial Analysis
    rescores old models when the index changes and tags no version, so the read
    date is the version key — and a candidate rescored in a later reading, held
    against a target frozen in an earlier one, is two snapshots."""
    base = wager.baseline_row(rows)
    rescored = qualifying(rows, aa_version="2027-01-01")
    assert rescored["aa_version"] != base["aa_version"]
    assert wager.resolution(rows + [rescored])["resolved"] is False

    same_snapshot = qualifying(rows)
    assert same_snapshot["aa_version"] == base["aa_version"]
    assert wager.resolution(rows + [same_snapshot])["resolved"] is True


def test_a_published_price_of_zero_clears_the_ceiling(rows):
    """Free is under the ceiling. Unpriced is not shown to be under it, and the
    two must not collapse into one falsy value."""
    free = qualifying(rows, current_price_in=0.0, current_price_out=0.0)
    assert wager.blended_price(free) == 0.0
    assert wager.resolution(rows + [free])["resolved"] is True

    unpriced = qualifying(rows, current_price_in=None, current_price_out=None)
    assert wager.blended_price(unpriced) is None
    assert wager.resolution(rows + [unpriced])["resolved"] is False


def test_the_archival_grace_is_one_number_in_two_files(frozen):
    """`wager.GRACE_DAYS` bounds the evidence a recorded reading may be taken
    from; `wager.json` is what the letter and any future arbiter quote."""
    assert wager.GRACE_DAYS == frozen["resolution"]["archival_grace_days"]


def _record(history_dir, date, artifact):
    (history_dir / date).mkdir(exist_ok=True)
    (history_dir / date / "resolution.json").write_text(json.dumps(artifact))


def test_an_unreadable_recorded_resolution_is_skipped(tmp_path):
    """Past the cutoff this file is the wager's status, which makes it the last
    place to take a malformed reading at its word. Each artifact below is
    written into the newest snapshot, where it would win if it were readable,
    and the older valid reading has to survive every one of them."""
    good = {"resolved": False, "resolved_by": None,
            "read_from": "data/history/2027-06-28"}
    _record(tmp_path, "2027-06-28", good)
    for date in ("2027-07-05", "2027-07-12"):
        (tmp_path / date).mkdir()
    assert wager.recorded_resolution(tmp_path) == good

    for bad in (
        ["resolved"],  # not an object
        {"read_from": "data/history/2027-07-05"},  # no verdict
        {"resolved": "yes", "read_from": "data/history/2027-07-05"},
        # a YES that names nothing settles nothing
        {"resolved": True, "resolved_by": "   ",
         "read_from": "data/history/2027-07-05"},
        {"resolved": True, "resolved_by": None,
         "read_from": "data/history/2027-07-05"},
        # read against a snapshot this history does not hold
        {"resolved": True, "resolved_by": "gemini-4-flash-lite",
         "read_from": "data/history/2027-07-04"},
        {"resolved": True, "resolved_by": "gemini-4-flash-lite",
         "read_from": "not-a-date"},
        # evidence captured past the archival grace
        {"resolved": True, "resolved_by": "gemini-4-flash-lite",
         "read_from": "data/history/2027-07-12"},
    ):
        _record(tmp_path, "2027-07-05", bad)
        assert wager.recorded_resolution(tmp_path) == good, bad

    # The grace is inclusive: the last day it admits is a reading, not a
    # rejection — and a NO has nothing to name.
    last_day = str(wager.DEADLINE + dt.timedelta(days=wager.GRACE_DAYS))
    (tmp_path / last_day).mkdir(exist_ok=True)
    _record(tmp_path, "2027-07-05", {"resolved": True, "resolved_by": "gemini-4",
                                     "read_from": f"data/history/{last_day}/"})
    assert wager.recorded_resolution(tmp_path)["resolved_by"] == "gemini-4"


def test_a_directory_that_is_not_a_date_is_not_a_snapshot(tmp_path):
    """The directory name is the version key, so a name that is not a date is
    not a reading. One sorting after every real date would otherwise take the
    newest slot and answer the wager from a scratch directory."""
    _record(tmp_path, "2027-06-28", {"resolved": False, "resolved_by": None,
                                     "read_from": "data/history/2027-06-28"})
    _record(tmp_path, "zzz-scratch", {"resolved": True, "resolved_by": "draft",
                                      "read_from": "data/history/zzz-scratch"})
    assert wager.latest_snapshot(tmp_path) == "2027-06-28"
    assert wager.recorded_resolution(tmp_path)["resolved"] is False


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
