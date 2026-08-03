"""
THE TRICKLE-DOWN WAGER — the data spine and the arithmetic behind it.

Reads `timeline.csv` (one curated, sourced row per tracked model) and derives
everything the WAGER page, the scheduled email, and the refresh skill need:
frontier milestones, the first entry-level model to match each one, the two
prediction methods, and whether the wager has resolved.

Standard library only, so the arithmetic itself has no dependencies to
drift. The page and the scheduled email job both re-run it from the CSV.
"""

import csv
import datetime as dt
import json
import math
import os

# Resolved against this file, not the working directory — the page, the scripts,
# and the scheduled job all run from different places.
ROOT = os.path.dirname(os.path.abspath(__file__))
TIMELINE_FILE = os.path.join(ROOT, "timeline.csv")
WAGER_FILE = os.path.join(ROOT, "wager.json")
HISTORY_DIR = os.path.join(ROOT, "data", "history")

# The day the wager was frozen: the date the OpenRouter feed was read on, and
# the start of the midpoint check-in interval.
SNAPSHOT_DATE = dt.date(2026, 8, 1)

# The Artificial Analysis API payload this repo committed is older than the
# OpenRouter read — it predates GPT-5.6 and Opus 5. Rows sourced from it carry
# this vintage rather than the freeze date.
AA_API_VINTAGE = dt.date(2026, 7, 5)

# The model the wager is about.
BASELINE = "claude-fable-5"

# The price term as a number, frozen with the rest of the terms. Derived from
# the baseline's blended price at the freeze — a tenth of $20.00 — but not read
# from it: a wager whose ceiling moves when a vendor reprices the baseline is a
# wager whose bar the other side can move. wager.json carries the same figure
# and the tests pin the two together; this constant is the one the code reads.
PRICE_CAP_BLENDED = 2.00

# The vendors whose entry-level slot can settle this. Frozen with the terms: a
# fourth lab getting there first is a different claim, and the page says so.
ELIGIBLE_VENDORS = ("Anthropic", "OpenAI", "Google")

# The resolution bound. Past it the wager is false rather than pending. It is
# where the slowest price decline Epoch fitted reaches a tenfold fall, run from
# the baseline's release — a trend slower than anything measured would still
# have landed by this date. wager.json carries the same date and the tests pin
# the two together; this constant is the one the code reads.
DEADLINE = dt.date(2027, 6, 27)

# The archival grace: evidence has to be public by the deadline, but the AA
# snapshot and the vendor list price proving it may be captured this many days
# later. It bounds the evidence date a recorded resolution may be read from.
# wager.json carries the same figure and the tests pin the two together; this
# constant is the one the code reads.
GRACE_DAYS = 14

# Epoch AI measured the price of a fixed level of benchmark performance falling
# 9x-900x per year across six benchmarks, median 50x.
# https://epoch.ai/data-insights/llm-inference-price-trends
EPOCH_MEDIAN_DECLINE = 50.0
EPOCH_SLOW_DECLINE = 9.0

# The wager's price term: an entry-level model must match the baseline's index
# at no more than this share of the baseline's cost.
COST_SHARE = 0.10

DAYS_PER_MONTH = 365.2425 / 12


def _num(value):
    """Blank cells stay blank — timeline.csv records absence rather than a
    guess, and every downstream calculation has to survive that."""
    return float(value) if value not in ("", None) else None


def load_timeline(path=TIMELINE_FILE):
    """timeline.csv as a list of dicts, oldest release first, numbers parsed."""
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["release_date"] = dt.date.fromisoformat(r["release_date"])
        for col in ("launch_price_in", "launch_price_out", "current_price_in",
                    "current_price_out", "metr_horizon_min_p50",
                    "metr_horizon_min_p80", "aa_intel"):
            r[col] = _num(r[col])
    return sorted(rows, key=lambda r: r["release_date"])


def blended_price(row, in_out_ratio=3.0):
    """One $/MTok number per model, at a fixed input:output mix. Only ever
    compared against another model at the same mix — a real workload's ratio
    differs, and reasoning tokens bill as output, so this is a ruler, not a
    quote."""
    pin, pout = row["current_price_in"], row["current_price_out"]
    if pin is None or pout is None:
        return None
    return (in_out_ratio * pin + pout) / (in_out_ratio + 1)


def milestones(rows):
    """Frontier models that set a new high-water mark on the AA index at their
    release, each paired with the first entry-level model from any vendor to
    reach that index.

    High-water mark rather than a hand-picked list: which releases count as
    milestones then follows from the data, and a release that failed to beat
    the standing best (GPT-4o) drops out on its own.
    """
    scored = [r for r in rows if r["aa_intel"] is not None]
    bottom = [r for r in scored if r["tier"] == "bottom"]

    out = []
    best = 0.0
    for r in scored:
        if r["tier"] != "frontier" or r["aa_intel"] <= best:
            continue
        best = r["aa_intel"]
        match = next((b for b in bottom
                      if b["release_date"] > r["release_date"]
                      and b["aa_intel"] >= r["aa_intel"]), None)
        # The closest an entry-level model has come while falling short — the
        # near-misses are the interesting part of an open row.
        later = [b for b in bottom if b["release_date"] > r["release_date"]]
        closest = max(later, key=lambda b: b["aa_intel"], default=None)

        entry = {
            "frontier": r["model"],
            "frontier_date": r["release_date"],
            "frontier_aa": r["aa_intel"],
            "frontier_price": blended_price(r),
            "matched_by": None,
            "matched_date": None,
            "matched_aa": None,
            "matched_price": None,
            "lag_months": None,
            "price_ratio": None,
            "closest": closest["model"] if closest else None,
            "closest_aa": closest["aa_intel"] if closest else None,
        }
        if match:
            lag_days = (match["release_date"] - r["release_date"]).days
            fp, mp = entry["frontier_price"], blended_price(match)
            entry.update(
                matched_by=match["model"],
                matched_date=match["release_date"],
                matched_aa=match["aa_intel"],
                matched_price=mp,
                lag_months=lag_days / DAYS_PER_MONTH,
                price_ratio=(fp / mp) if fp and mp else None,
            )
        out.append(entry)
    return out


def baseline_row(rows):
    return next(r for r in rows if r["model"] == BASELINE)


def method_a(rows):
    """Extrapolate the historical frontier-to-bottom lag.

    Rule: the median lag over every milestone that has been matched, added to
    the baseline's release date. Median rather than a fitted trend — ten
    points, one of them (the pre-reasoning GPT-4 era) more than twice any
    other, is not enough to fit a slope that would survive the next release.

    The pairs are not independent of each other. A single cheap release can
    clear several standing frontier highs at once, so `n_matchers` — the number
    of distinct entry-level models doing the clearing — is the sample size that
    matters, and it is far smaller than the pair count.
    """
    ms = milestones(rows)
    matched = [m for m in ms if m["lag_months"] is not None]
    lags = sorted(m["lag_months"] for m in matched)
    n = len(lags)
    median = (lags[n // 2] if n % 2 else (lags[n // 2 - 1] + lags[n // 2]) / 2)

    matchers = {}
    for m in matched:
        matchers[m["matched_by"]] = matchers.get(m["matched_by"], 0) + 1

    # How many of the historical catch-ups would have failed the wager's own
    # price term. Matching the index is the easy half; doing it at a tenth of
    # the cost is the half the wager actually turns on.
    priced = [m for m in matched if m["price_ratio"] is not None]
    under_bar = [m for m in priced if m["price_ratio"] < 1 / COST_SHARE]

    base = baseline_row(rows)
    date = base["release_date"] + dt.timedelta(days=round(median * DAYS_PER_MONTH))
    return {
        "method": "A — historical frontier-to-bottom lag",
        "date": date,
        "median_lag_months": median,
        "mean_lag_months": sum(lags) / n,
        "n_pairs": n,
        "n_matchers": len(matchers),
        "matchers": matchers,
        "n_priced": len(priced),
        "n_under_price_bar": len(under_bar),
        "pairs": [{"frontier": m["frontier"], "matched_by": m["matched_by"],
                   "lag_months": m["lag_months"]} for m in matched],
        "from_date": base["release_date"],
    }


def method_b(rows, rate=EPOCH_MEDIAN_DECLINE, from_date=None,
             cost_share=COST_SHARE):
    """Extrapolate Epoch AI's price decline for a fixed level of capability.

    The wager's price term is a ratio — an entry-level model must match the
    baseline at <= 1/10th its cost — so the answer is the time for the price
    of baseline-level capability to fall 10x, whatever the two sticker prices
    are. That makes this method independent of the input:output mix, and of
    the baseline's own price ever changing.

    The clock starts at the baseline's release, not at the freeze date. The
    quantity falling is the price of Fable-5-level capability, and it began
    falling the day that capability first existed — starting the clock when
    this repo happened to read the feeds would push the answer out by however
    long it took to get around to writing the page.
    """
    from_date = from_date or baseline_row(rows)["release_date"]
    years = math.log(1 / cost_share) / math.log(rate)
    return {
        "method": f"B — Epoch price decline at {rate:g}x/yr",
        "date": from_date + dt.timedelta(days=round(years * 365.2425)),
        "years": years,
        "rate": rate,
        "cost_share": cost_share,
        "from_date": from_date,
    }


def resolution(rows):
    """Where the binding arm stands today.

    One arm binds: an entry-level model from an eligible vendor, released on or
    before the deadline, at or above the baseline's launch AA index and at or
    below PRICE_CAP_BLENDED, compared inside one AA snapshot. A candidate whose
    index was read at a different `aa_version` than the baseline's is two
    snapshots rather than one, so it cannot clear the arm. METR is carried
    alongside as a secondary check — it has measured neither the baseline nor
    any entry-level model, so it cannot settle anything, and it does not enter
    `resolved`.

    A candidate's release date is in the CSV; the date its price took effect is
    not. Whether a qualifying price was published before the cutoff or after it
    is adjudicated by hand against the snapshot recorded on the deadline, as the
    resolution checklist sets out — this function reads only what the spine
    carries.

    Today's date is not read here. Whether an unresolved wager is still OPEN or
    has run past DEADLINE depends on when the question is asked, and this
    function stays a pure function of the CSV so the tests can pin its output.
    """
    base = baseline_row(rows)
    bottom = [r for r in rows
              if r["tier"] == "bottom" and r["vendor"] in ELIGIBLE_VENDORS
              and r["release_date"] <= DEADLINE]

    # The baseline has no published horizon; the family's early preview is the
    # only METR-measured member and stands in provisionally.
    proxy = next((r for r in rows if r["metr_horizon_min_p50"] is not None
                  and r["model"].startswith("claude-mythos")), None)
    metr_target = proxy["metr_horizon_min_p50"] if proxy else None
    metr_measured = [b for b in bottom if b["metr_horizon_min_p50"] is not None]

    # The ceiling is the frozen constant; the baseline's live blended price is
    # reported next to it as information, and a missing one costs the reader a
    # figure rather than the arm.
    base_price = blended_price(base)
    price_cap = PRICE_CAP_BLENDED
    # No target index means no arm: half the rule is unreadable, so nothing can
    # clear it. Saying so beats comparing a score against None and calling it a
    # crash.
    reason = None if base["aa_intel"] is not None else (
        f"{base['model']} carries no AA index in timeline.csv, so the "
        f"capability term has no target to test against and the arm cannot be "
        f"evaluated")
    def under_cap(row):
        # A price the timeline does not carry cannot be shown to clear the
        # ceiling; a published price of zero clears it.
        price = blended_price(row)
        return price is not None and price <= price_cap

    aa_hits = [] if reason else [
        b for b in bottom
        if b["aa_intel"] is not None and b["aa_intel"] >= base["aa_intel"]
        and b["aa_version"] == base["aa_version"] and under_cap(b)]
    best = max((b for b in bottom if b["aa_intel"] is not None),
               key=lambda b: b["aa_intel"], default=None)

    return {
        "baseline": base["model"],
        "baseline_aa": base["aa_intel"],
        "baseline_price": base_price,
        "price_cap": price_cap,
        "deadline": DEADLINE,
        "metr_target_min": metr_target,
        "metr_proxy": proxy["model"] if proxy else None,
        "metr_measurable": len(metr_measured),
        "best_bottom": best["model"] if best else None,
        "best_bottom_aa": best["aa_intel"] if best else None,
        "best_bottom_price": blended_price(best) if best else None,
        "gap_points": (base["aa_intel"] - best["aa_intel"])
                      if best and base["aa_intel"] is not None else None,
        "resolved": bool(aa_hits),
        "resolved_by": aa_hits[0]["model"] if aa_hits else None,
        "unevaluable": reason,
    }


def predictions(rows):
    """Both methods plus the slowest fitted trend, earliest first.

    Two illustrative scenarios, not a calibrated forecast. They land close
    together because capability diffusion and price decline are two views of
    the same underlying trend, so proximity is not corroboration.
    """
    a = method_a(rows)
    b = method_b(rows)
    slow = method_b(rows, rate=EPOCH_SLOW_DECLINE)
    return {
        "a": a, "b": b, "slow": slow,
        "earliest": min(a["date"], b["date"]),
        "latest": max(a["date"], b["date"]),
    }


def midpoint(earliest, start=SNAPSHOT_DATE):
    """Halfway from the snapshot to the earlier predicted date — the check-in."""
    return start + dt.timedelta(days=(earliest - start).days // 2)


def load_wager(path=WAGER_FILE):
    with open(path) as f:
        return json.load(f)


def _snapshot_dates(history_dir=HISTORY_DIR):
    """Snapshot directory names, oldest first. The name is the version key, so
    a directory whose name is not an ISO date is not a snapshot and takes no
    part in the ordering."""
    try:
        names = os.listdir(history_dir)
    except OSError:
        return []
    dated = []
    for name in names:
        if not os.path.isdir(os.path.join(history_dir, name)):
            continue
        try:
            dt.date.fromisoformat(name)
        except ValueError:
            continue
        dated.append(name)
    return sorted(dated)


def latest_snapshot(history_dir=HISTORY_DIR):
    """Newest dated snapshot directory, or None if there are none."""
    dates = _snapshot_dates(history_dir)
    return dates[-1] if dates else None


def _is_readable_resolution(artifact, history_dir):
    """Whether an artifact carries a reading this function may report.

    A YES has to name what settled it, and the reading has to point at evidence
    the terms admit: a snapshot that exists in the same history directory, dated
    no later than the deadline plus the archival grace. The bound is on the
    evidence rather than on the artifact — a file written late about a snapshot
    taken in time is the case the grace exists for.
    """
    if not isinstance(artifact, dict):
        return False
    if not isinstance(artifact.get("resolved"), bool):
        return False
    if artifact["resolved"]:
        by = artifact.get("resolved_by")
        if not isinstance(by, str) or not by.strip():
            return False
    read_from = artifact.get("read_from")
    if not isinstance(read_from, str):
        return False
    name = os.path.basename(read_from.rstrip("/"))
    try:
        read_date = dt.date.fromisoformat(name)
    except ValueError:
        return False
    if read_date > DEADLINE + dt.timedelta(days=GRACE_DAYS):
        return False
    return os.path.isdir(os.path.join(history_dir, name))


def recorded_resolution(history_dir=HISTORY_DIR):
    """The written-down outcome, from the newest snapshot that carries one.

    Convention: `data/history/<date>/resolution.json`, carrying at least
    `resolved`, `resolved_by` and `read_from` — the snapshot the reading was
    taken against. Past the deadline this file is the wager's status. A
    resolution is something read on a date and recorded, not a recomputation:
    a timeline row added afterwards must not be able to reopen a settled
    question, or to settle one that was recorded as NO.

    An artifact that does not satisfy `_is_readable_resolution` is skipped like
    an unreadable one: this file decides the wager once the cutoff has passed,
    which is the last place to take a malformed reading at its word.

    None until one is recorded, which is the state between the cutoff and the
    reading rather than an error.
    """
    for date in reversed(_snapshot_dates(history_dir)):
        try:
            with open(os.path.join(history_dir, date, "resolution.json")) as f:
                artifact = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if _is_readable_resolution(artifact, history_dir):
            return artifact
    return None
