# The trickle-down wager — reading the result

Frozen {frozen_on}, delivered {today}. The cutoff passed at 23:59 UTC
yesterday, {deadline}. The answer is already fixed and nothing published from
here on can move it — this letter arrives the morning after so the reading is
done against a closed question rather than raced against a clock.

**The claim.** An entry-level model — the slot a vendor designates as its
cheapest, from Anthropic, OpenAI or Google — would match {baseline}, the
frontier as of June 2026, on the Artificial Analysis intelligence index at no
more than a tenth of {baseline}'s price: at or below ${price_cap} per million
tokens on the fixed 3:1 blend. Both terms, one model, at one time.

**Why that date.** {deadline} is where the slowest price decline Epoch AI has
fitted reaches a tenfold fall, counted from {baseline}'s release. A trend slower
than anything measured would still have landed by then, so past that instant the
claim is false rather than pending. The forecast dates were {method_b_date} and
{method_a_date}; missing those was not a NO, and missing the cutoff is.

**What counts.** The evidence had to be publicly available by 23:59 UTC on
{deadline}. The AA snapshot and the vendor price page proving it may be captured
up to {grace_days} days after that — capture is allowed to lag, publication is
not, and nothing first published after the cutoff counts.

**Where it stood when the wager was frozen.** {baseline} scored {baseline_aa} on
the index. The best any entry-level model managed was {closest} at
{closest_aa} — {gap} points short. That is the number today's reading has to be
compared against, and {waited} days have passed since it was taken.

**Settle it.** The terms are in `wager.json` and have not moved since
{frozen_on}, which was the point of writing them down first. Work the checklist
in order — the date check comes first, and the refresh comes before the reading.

{checklist}

Two ways to get the verdict wrong, both worth ruling out before recording it. A
false YES: an index version change that rescored everything, or a mid-tier model
moved into the entry-level name, which the slot rule excludes. A false NO: a
qualifying model that was public before the cutoff but had not reached this
repo's `timeline.csv` — the refresh step exists for exactly that.

Write the outcome to `data/history/DATE/resolution.json` with `resolved`,
`resolved_by` and `read_from` — the snapshot the reading was taken against. The
page reads that file rather than recomputing once the cutoff has passed, so
until it exists the status reads PAST DEADLINE · VERIFYING. An unrecorded
resolution is the one failure mode that cannot be fixed later.

The page: {page}
The data: {repo}
