# The trickle-down wager is halfway

Due {midpoint_date}, delivered {today}: the midpoint between the day the wager
was frozen ({frozen_on}) and the earlier of its two predicted dates
({method_b_date}). This is the check-in, not the verdict.

**The question.** Is the trend still doing what it was doing? At the freeze, the
lag from a frontier model setting a new high on the Artificial Analysis index to
the first bottom-tier model reaching it had a median of {median_lag} months over
{n_pairs} pairs — pairs produced by {n_matchers} catch-up releases, so treat
{n_matchers} as the sample size that moved.

**The gap to close.** {baseline} at {baseline_aa}; the best bottom-tier model
was {closest} at {closest_aa}, {gap} points short. If something cheap has landed
above {baseline_aa} since, check its price before calling it: the index arm also
requires a tenth of {baseline}'s cost, and a third of the historical catch-ups
arrived with a smaller price gap than that.

**What to do.**

1. Run `uv run python scripts/timeline_fetch.py` for a fresh snapshot and a diff
   against the last one.
2. Run the `/timeline-refresh` skill to turn that diff into sourced
   `timeline.csv` edits and recompute both predictions.
3. Commit the result. The commit also keeps this scheduled workflow alive —
   GitHub disables cron workflows after 60 days without repository activity, so
   the letter due {method_b_date} depends on the repo not going quiet.

The page: {page}
The data: {repo}
