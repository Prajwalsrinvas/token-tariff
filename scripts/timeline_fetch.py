"""
Refresh the wager's raw sources into a new dated snapshot, then report what
changed since the last one.

Deterministic and keyless by default: the OpenRouter model listing and METR's
published benchmark YAMLs need no credentials. The Artificial Analysis API is
fetched only when AA_API_KEY is set, matching how the main app treats it.

    uv run python scripts/timeline_fetch.py

Writes data/history/<today>/ and prints a diff against the previous snapshot:
new and retired models, price moves, index moves, new METR measurements, and
any timeline.csv cell that no longer agrees with its source. Nothing is written
to timeline.csv — curating that file is a judgement call, made with the
/timeline-refresh skill, which reads this output.
"""

import argparse
import datetime as dt
import json
import os
import pathlib
import sys

import requests
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import wager  # noqa: E402

HISTORY = pathlib.Path(wager.HISTORY_DIR)

# Every keyless source, as (filename, url). Fetched in order; a failure on any
# one aborts before anything is written, so a snapshot directory is never
# half-populated.
SOURCES = [
    ("openrouter_models.json", "https://openrouter.ai/api/v1/models"),
    ("metr_benchmark_results_1_1.yaml",
     "https://metr.org/assets/benchmark_results_1_1.yaml"),
    ("metr_benchmark_results_1_0.yaml",
     "https://metr.org/assets/benchmark_results_1_0.yaml"),
    ("metr_release_dates.yaml",
     "https://raw.githubusercontent.com/METR/eval-analysis-public/main/"
     "data/external/release_dates.yaml"),
]

AA_FILE = "aa_models.json"
AA_URL = "https://artificialanalysis.ai/api/v2/data/llms/models"

PROVENANCE = """# Provenance — {date}

Raw sources for `timeline.csv`, fetched by `scripts/timeline_fetch.py` on
{date}. Append-only: never edit a snapshot after the fact — a corrected figure
belongs in the next one, so that a source silently changing its own history
stays visible.

| File | Source | Fetched |
|---|---|---|
{table}

`aa_models.json` is present only when the fetch ran with `AA_API_KEY` set.

Artificial Analysis publishes no index-version field in either the OpenRouter
listing or its own API, and re-scores older models when the index changes. The
snapshot date is therefore the version key for every AA figure drawn from it.

METR figures come from METR-Horizon-v1.1 unless a row says otherwise; the same
model scores differently under v1.0, so the two suites must not be mixed.
"""


def fetch(url: str, headers=None) -> bytes:
    response = requests.get(url, timeout=60, headers=headers)
    response.raise_for_status()
    return response.content


def write_snapshot(date: str, aa_key: str, force: bool) -> pathlib.Path:
    # Append-only is the whole point: a snapshot records what a source said on
    # a day, and rewriting one destroys the evidence that it has since changed
    # its mind. It also silently drops any provenance note added by hand.
    target = HISTORY / date
    if target.exists() and any(target.iterdir()) and not force:
        raise SystemExit(
            f"{target}/ already exists. Snapshots are append-only — pass a "
            f"different --date, or --force to overwrite deliberately.")

    payloads = [(name, fetch(url)) for name, url in SOURCES]
    sources = list(SOURCES)

    if aa_key:
        payloads.append((AA_FILE, fetch(AA_URL, {"x-api-key": aa_key})))
        sources.append((AA_FILE, AA_URL))
    else:
        print("AA_API_KEY not set — skipping the Artificial Analysis API "
              "(the OpenRouter listing still carries AA scores for the models "
              "it routes)")

    target.mkdir(parents=True, exist_ok=True)
    for name, body in payloads:
        (target / name).write_bytes(body)

    table = "\n".join(f"| `{name}` | {url} | {date} |" for name, url in sources)
    (target / "provenance.md").write_text(
        PROVENANCE.format(date=date, table=table))
    return target


def or_index(path: pathlib.Path) -> dict:
    """model id -> (price in, price out, AA intelligence) from an OR listing."""
    data = json.loads((path / "openrouter_models.json").read_text())["data"]
    out = {}
    for m in data:
        aa = (m.get("benchmarks") or {}).get("artificial_analysis") or {}
        out[m["id"]] = (
            float(m["pricing"]["prompt"]) * 1e6,
            float(m["pricing"]["completion"]) * 1e6,
            aa.get("intelligence_index"),
        )
    return out


def metr_index(path: pathlib.Path) -> dict:
    """model key -> (50%, 80%) horizons in minutes, from METR-Horizon-v1.1.

    Both thresholds, because timeline.csv records both and the gap between
    them is a caveat the page leans on — an unverified p80 column would be the
    one number nothing checks.
    """
    doc = yaml.safe_load((path / "metr_benchmark_results_1_1.yaml").read_text())
    out = {}
    for k, v in doc["results"].items():
        metrics = v["metrics"]
        out[k] = tuple((metrics.get(f"p{p}_horizon_length") or {}).get("estimate")
                       for p in (50, 80))
    return out


def bullets(title: str, lines: list, limit: int = 25):
    print(f"\n{title} ({len(lines)})")
    if not lines:
        print("  none")
        return
    for line in lines[:limit]:
        print(f"  {line}")
    if len(lines) > limit:
        print(f"  ... and {len(lines) - limit} more")


def diff(new: pathlib.Path, old: pathlib.Path):
    a, b = or_index(old), or_index(new)
    added = sorted(set(b) - set(a))
    removed = sorted(set(a) - set(b))

    prices, scores = [], []
    for k in sorted(set(a) & set(b)):
        (ai, ao, asc), (bi, bo, bsc) = a[k], b[k]
        if (ai, ao) != (bi, bo):
            prices.append(f"{k}: ${ai:g}/${ao:g} -> ${bi:g}/${bo:g}")
        if asc != bsc:
            scores.append(f"{k}: AA {asc} -> {bsc}")

    ma, mb = metr_index(old), metr_index(new)
    metr_new = sorted(set(mb) - set(ma))
    metr_moved = []
    for k in sorted(set(ma) & set(mb)):
        moved = [f"p{p} {x:.1f} -> {y:.1f}" for p, x, y
                 in zip((50, 80), ma[k], mb[k])
                 if x is not None and y is not None and abs(x - y) > 0.05]
        if moved:
            metr_moved.append(f"{k}: {', '.join(moved)} min")

    print(f"\n=== {new.name} vs {old.name} ===")
    bullets("NEW MODELS", added)
    bullets("DELISTED", removed)
    bullets("PRICE CHANGES", prices)
    bullets("AA INDEX CHANGES", scores)
    bullets("NEW METR MEASUREMENTS", metr_new)
    bullets("METR RE-MEASUREMENTS", metr_moved)


def check_timeline(new: pathlib.Path):
    """Flag any timeline.csv cell the newest snapshot no longer agrees with.

    Only checks rows whose source column names the feed being compared, so a
    row sourced from a vendor's own docs is never second-guessed by a route
    price. Disagreement is a prompt to look, not proof of an error — a
    promotional route price will trip it, and should.
    """
    live, horizons = or_index(new), metr_index(new)
    problems = []
    for r in wager.load_timeline():
        ids = [f"{r['vendor'].lower()}/{r['model']}",
               f"openai/{r['model']}", f"anthropic/{r['model']}",
               f"google/{r['model']}"]
        hit = next((live[i] for i in ids if i in live), None)
        if hit and r["aa_intel"] is not None and "openrouter" in r["aa_source"]:
            if hit[2] is not None and abs(hit[2] - r["aa_intel"]) > 0.05:
                problems.append(f"{r['model']}: AA {r['aa_intel']} in "
                                f"timeline.csv, {hit[2]} in the snapshot")
        if hit and r["current_price_in"] is not None:
            if abs(hit[0] - r["current_price_in"]) > 0.001:
                problems.append(f"{r['model']}: price in ${r['current_price_in']:g} "
                                f"in timeline.csv, ${hit[0]:g} on the OpenRouter "
                                f"route")
        key = r["metr_key"]
        if key and key in horizons:
            for col, measured in zip(("metr_horizon_min_p50",
                                      "metr_horizon_min_p80"), horizons[key]):
                if r[col] is None or measured is None:
                    continue
                if abs(measured - r[col]) > 0.05:
                    problems.append(f"{r['model']}: METR {col[-3:]} {r[col]} in "
                                    f"timeline.csv, {measured:.3f} in the "
                                    f"snapshot")
    bullets("TIMELINE.CSV CELLS THAT DISAGREE WITH THIS SNAPSHOT", problems)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=str(dt.date.today()),
                        help="snapshot directory name (default: today)")
    parser.add_argument("--force", action="store_true",
                        help="overwrite an existing snapshot for that date")
    args = parser.parse_args()

    previous = wager.latest_snapshot()
    target = write_snapshot(args.date, os.environ.get("AA_API_KEY", ""),
                            args.force)
    print(f"wrote {target}/ — {len(list(target.iterdir()))} files")

    if previous and previous != args.date:
        diff(target, HISTORY / previous)
    else:
        print("\nno earlier snapshot to compare against")

    check_timeline(target)
    print("\nNext: run the /timeline-refresh skill to turn this into "
          "timeline.csv edits, each with a source URL.")


if __name__ == "__main__":
    main()
