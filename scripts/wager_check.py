"""
Send a wager email when one comes due.

Reads `wager.json` for the two scheduled sends, works out whether either is due
and not already sent, fills the matching template from live data, mails it
through Resend, and opens a status-only issue as the record.

    uv run python scripts/wager_check.py --dry-run          # what would happen
    uv run python scripts/wager_check.py --dry-run --as-of 2027-01-10
    uv run python scripts/wager_check.py                    # send for real

Idempotency is the issue, not a stored flag. A send counts as done when a
labelled issue with its title exists, which is read from the API each run — a
committed flag can disagree with reality whenever the write-back commit fails,
and then either double-sends forever or never sends at all.

The email goes first and the issue immediately after. If the issue fails to
open, the run exits non-zero: at worst that costs one duplicate email at the
next monthly tick, which is loud, where the reverse order risks a letter that
silently never arrives.

Environment (all supplied by the workflow as Actions secrets or defaults):
    RESEND_API_KEY    Resend credential. Absent = dry run, always.
    WAGER_EMAIL_TO    Recipient. Never appears in this repo or in any issue.
    RESEND_FROM       Sender. Defaults to Resend's shared test sender, which
                      delivers only to the Resend account owner's own address.
    GITHUB_TOKEN      For reading and opening issues.
    GITHUB_REPOSITORY owner/name, set automatically inside Actions.
"""

import argparse
import datetime as dt
import json
import pathlib
import os
import sys

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import wager  # noqa: E402

# Resolved against this file, not the working directory — the workflow runs
# from the repo root but nothing guarantees that a human does.
SCRIPTS = pathlib.Path(__file__).resolve().parent

TEMPLATES = {
    "wager-letter": SCRIPTS / "wager_letter.md",
    "midpoint-check": SCRIPTS / "wager_midpoint.md",
}
ISSUE_LABEL = "wager"
RESEND_URL = "https://api.resend.com/emails"
GITHUB_API = "https://api.github.com"
DEFAULT_FROM = "onboarding@resend.dev"


def render(send: dict, doc: dict, today: dt.date) -> str:
    """Fill a template from the frozen wager plus a live recomputation, so a
    letter that arrives months late still describes the data as it is."""
    rows = wager.load_timeline()
    res = wager.resolution(rows)
    a = doc["predictions"]["method_a"]
    frozen_on = dt.date.fromisoformat(doc["frozen_on"])

    checklist = "\n".join(f"{i}. {step}" for i, step
                          in enumerate(doc["resolution"]["checklist"], 1))
    values = {
        "frozen_on": doc["frozen_on"],
        "today": today.isoformat(),
        "waited": (today - frozen_on).days,
        # The prose reads "Claude Fable 5", not the catalog slug; unknown
        # slugs fall through unchanged.
        "baseline": {"claude-fable-5": "Claude Fable 5"}.get(
            res["baseline"], res["baseline"]),
        "baseline_aa": f"{res['baseline_aa']:.1f}",
        "closest": res["best_bottom"],
        "closest_aa": f"{res['best_bottom_aa']:.1f}",
        "gap": f"{res['gap_points']:.1f}",
        "median_lag": a["median_lag_months"],
        "n_pairs": a["n_pairs"],
        "method_a_date": a["date"],
        "method_b_date": doc["predictions"]["method_b"]["date"],
        "slow_date": doc["predictions"]["slowest_trend"]["date"],
        "n_matchers": a["n_distinct_matchers"],
        "midpoint_date": next(x["due"] for x in doc["sends"]
                              if x["id"] == "midpoint-check"),
        "checklist": checklist,
        "page": doc["page"],
        "repo": "https://github.com/Prajwalsrinvas/token-tariff",
    }
    body = TEMPLATES[send["id"]].read_text()
    if res["resolved"]:
        body += (f"\n**It has already resolved YES.** {res['resolved_by']} "
                 f"cleared the bar. Check that this is not an artefact before "
                 f"celebrating.\n")
    return body.format(**values)


def already_sent(send: dict, repo: str, token: str) -> bool:
    """True when this send's issue exists, open or closed. Listing by label
    keeps it to one page and one request, and never confuses a pull request
    for an issue."""
    response = requests.get(
        f"{GITHUB_API}/repos/{repo}/issues",
        params={"state": "all", "labels": ISSUE_LABEL, "per_page": 100},
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json"},
        timeout=30,
    )
    response.raise_for_status()
    return any(i["title"] == send["issue_title"] for i in response.json())


def send_email(send: dict, body: str, key: str, to: str):
    response = requests.post(
        RESEND_URL,
        headers={"Authorization": f"Bearer {key}"},
        # `or`, not a get() default: an unset Actions secret arrives as an
        # empty string, which would be sent as the From address.
        json={"from": os.environ.get("RESEND_FROM") or DEFAULT_FROM,
              "to": [to], "subject": send["subject"], "text": body},
        timeout=30,
    )
    response.raise_for_status()


def open_issue(send: dict, doc: dict, repo: str, token: str, today: dt.date):
    """The record, and the marker that stops a second send. Status only — no
    recipient, no letter body, nothing that is not already public in the repo."""
    res = wager.resolution(wager.load_timeline())
    body = (
        f"Scheduled send `{send['id']}`, due {send['due']}, dispatched "
        f"{today}.\n\n"
        f"{send['purpose']}\n\n"
        f"| | |\n|---|---|\n"
        f"| Baseline | {res['baseline']} at AA {res['baseline_aa']:.1f} |\n"
        f"| Closest bottom-tier model | {res['best_bottom']} at AA "
        f"{res['best_bottom_aa']:.1f} |\n"
        f"| Gap | {res['gap_points']:.1f} points |\n"
        f"| Bottom-tier models with a METR horizon | "
        f"{res['metr_measurable']} |\n"
        f"| Resolved | {'yes — ' + res['resolved_by'] if res['resolved'] else 'no'} |\n\n"
        f"Terms are in `wager.json`; the [page]({doc['page']}) renders them. "
        f"This issue is the idempotency marker: while it exists, "
        f"`{send['id']}` will not send again.\n"
    )
    response = requests.post(
        f"{GITHUB_API}/repos/{repo}/issues",
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json"},
        json={"title": send["issue_title"], "body": body,
              "labels": [ISSUE_LABEL]},
        timeout=30,
    )
    response.raise_for_status()
    print(f"opened issue: {response.json()['html_url']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be sent and print the body")
    parser.add_argument("--as-of", default=str(dt.date.today()),
                        help="pretend today is this date (default: today)")
    args = parser.parse_args()

    today = dt.date.fromisoformat(args.as_of)
    doc = wager.load_wager()
    key = os.environ.get("RESEND_API_KEY", "")
    to = os.environ.get("WAGER_EMAIL_TO", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")

    # No credential means no send, whatever the flags say — running this
    # locally must never be able to mail anyone.
    dry = args.dry_run or not key or not to
    if dry and not args.dry_run:
        print("RESEND_API_KEY or WAGER_EMAIL_TO unset — dry run")

    print(f"as of {today} · {len(doc['sends'])} scheduled sends")
    failures = 0
    for send in doc["sends"]:
        due = dt.date.fromisoformat(send["due"])
        if today < due:
            print(f"  {send['id']}: not due until {due} "
                  f"({(due - today).days} days)")
            continue

        if token and repo:
            if already_sent(send, repo, token):
                print(f"  {send['id']}: already sent "
                      f"(issue \"{send['issue_title']}\" exists)")
                continue
        elif not dry:
            print(f"  {send['id']}: no GITHUB_TOKEN — cannot check the marker, "
                  f"refusing to send")
            failures += 1
            continue
        else:
            print(f"  {send['id']}: no GITHUB_TOKEN — marker unchecked")

        body = render(send, doc, today)
        if dry:
            print(f"  {send['id']}: WOULD SEND · subject "
                  f"\"{send['subject']}\" · issue \"{send['issue_title']}\"")
            print("\n" + "-" * 72)
            print(body)
            print("-" * 72 + "\n")
            continue

        send_email(send, body, key, to)
        print(f"  {send['id']}: sent")
        try:
            open_issue(send, doc, repo, token, today)
        except requests.RequestException as exc:
            print(f"  {send['id']}: EMAIL SENT BUT ISSUE FAILED — {exc}\n"
                  f"  Open an issue titled \"{send['issue_title']}\" with the "
                  f"\"{ISSUE_LABEL}\" label, or this will send again next month.")
            failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
