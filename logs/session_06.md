# Session 06 — 2026-09-23

## Goal
User asked to (1) research further ways to improve the prediction model's
accuracy and implement them in Python, and (2) propose dashboard
improvement ideas.

## Research performed (web search, before writing code)
- EGARCH vs. GJR-GARCH vs. plain GARCH for equity volatility (leverage
  effect / asymmetric response to negative vs. positive shocks).
- Wilson score confidence intervals for small-sample binomial proportions
  (directly applicable to the backtest's hit rate).
- Moving block bootstrap for preserving time-series dependence (researched,
  not implemented this session — see "Not done" below).
- Fintech dashboard UX best practices, specifically around communicating
  uncertainty (error bars vs. frequency framing) — informs the dashboard
  ideas list handed back to the user, not yet implemented.

Full citations in `docs/system_architecture.md`.

## What was built
1. **`src/markov.py` rewritten for EGARCH**: replaced symmetric GARCH(1,1)
   with EGARCH(1,1,1) — captures the leverage effect GARCH structurally
   can't represent. Required a real rewrite of the antithetic-variate logic
   (GARCH's variance recursion is sign-invariant; EGARCH's is not, since
   the asymmetry is the entire point of using it) — both signs now run
   their own log-variance recursion sharing only the drawn `|z|`
   magnitudes and state sequence.
2. **`wilson_interval()` added to `analysis_engine.py`**: 95% Wilson score
   CI on hit rate, both displayed everywhere hit rate appears (report,
   interface cards/table/calculator, chart titles) and used directly in
   the ranking formula (CI lower bound replaces the raw hit rate).
3. **`MAX_BACKTEST_EVENTS` raised from 8 to 50** — runtime headroom was
   large (full pipeline still under 20s), so the original cap was leaving
   real statistical power on the table for no reason.
4. **A genuine, previously-latent numerical bug found and fixed** while
   testing the sample-size increase — see below. This took most of this
   session's time and is the most important thing that happened.
5. Interface guide panel and calculator updated to explain and surface the
   Wilson CI; chart titles now show it too.

## The degenerate-fit bug (full trail in AI_Performance_Report.md)
Raising `MAX_BACKTEST_EVENTS` surfaced `NaN`/`inf` in the aggregate
backtest stats for O and STAG. Traced to a specific historical window
(`O`, fit ending 2023-02-28) whose Student-t EGARCH fit converged
(`convergence_flag == 0`, i.e. "success") to `alpha=748.7`, `gamma=234.3`,
`beta=1.0` — nowhere near sane values — because the fitted degrees-of-
freedom landed at `ν≈2.08`, right at the Student-t distribution's
finite-variance boundary. Three fix attempts, each verified against this
specific case before moving on rather than assumed to work:
1. Clip the variance recursion to a wide band (±15 log-space) — too wide,
   didn't fix it.
2. Tighten the clip to a realistic band (±4, anchored to empirical
   log-variance) — reduced but didn't eliminate it; the bootstrapped
   *residual pool itself* contained values in the hundreds (same root
   cause: in-sample conditional volatility near zero for a few days).
3. Clip the residual pool to ±10 **and** explicitly reject a degenerate
   parameter set (retry once with Normal distribution, else raise
   `DegenerateFitError` and skip that event) — this is what actually fixed
   it. `res.convergence_flag` does not catch this failure mode; had to be
   checked on the fitted parameters directly.

Also found and fixed: `_usable_event_indices` only required 15 days of
pre-event history, not nearly enough for a stable fit (especially the
252-day "recent" model) — added `MIN_FIT_HISTORY = 300`. This was a second,
independent contributor to the same NaN symptom.

## Also fixed in passing (unrelated)
`trailing_dividend_yield` returned NaN on this session's first run —
`yfinance` had appended a not-yet-finalized row for the most recent session
with a NaN Close. Fixed at the source: `data_io.fetch_history` now filters
`Close.notna()`.

## Verification performed
- Every fix attempt for the degenerate-fit bug was checked against the
  specific failing case in isolation (`O`, 2023-02-28) before re-running
  the full pipeline — cheaper and more precise than guessing from full-run
  output alone.
- Re-ran the full 4-ticker pipeline after each change; confirmed final
  output has no NaN/inf anywhere in `ranking.csv` and the Wilson intervals
  are sane (e.g. TTE's "100% hit rate" now shows as "[77–100%]" at n=13,
  correctly signaling real but limited certainty).
- Drove the updated interface live in the browser (not just read the
  generated HTML) to confirm the Wilson CI displays correctly in the
  cards, table, chart titles, and calculator, and that the "Aggressive
  pick" / "Conservative pick" labels shifted sensibly now that the
  underlying sample sizes changed (AGNC moved from "Conservative pick" to
  "Aggressive pick" once measured against 39 events instead of 8 — a
  legitimate reclassification, not a bug, since the group's medians moved
  too).

## Dashboard improvement ideas (not implemented this session — handed to user)
Proposed, not built: per-event outcome strip/dot visualization (frequency
framing for uncertainty, per fintech UX research above), sortable table
columns, a normalized multi-ticker comparison chart, a "last generated"
staleness warning. See the chat response for the full list with rationale.

## Not done, and why
- **Block/stationary bootstrap for residual draws**: researched (moving
  block bootstrap preserves short-term serial dependence that iid
  resampling within a state doesn't), but adapting it cleanly to this
  engine's per-day state-transition loop is nontrivial and was judged
  lower priority than fixing the degenerate-fit bug this session actually
  surfaced. Worth a future session if pursued.

## State for next session
- `docs/system_architecture.md` and `AI_Performance_Report.md` both have
  full session-6 sections — read both before touching `markov.py`'s
  numerical safety net (the ±10 residual clip, ±4 variance clip, and
  `_is_degenerate()` thresholds are all load-bearing, not arbitrary).
- Dashboard ideas list is still open — a good starting point if asked to
  improve the interface further.
