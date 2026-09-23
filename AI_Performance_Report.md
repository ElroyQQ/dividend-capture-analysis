# AI Performance Report

Objective assessment of this build: where the AI-generated pipeline worked,
where it needed correction, and where the underlying statistical model
diverges from reality. Written for a reader deciding how much to trust the
output in `output/report.md`, not just as a build log.

## What worked without incident

- Data ingestion (`data_io.py`), the transition-matrix/regime-bootstrap
  Monte Carlo engine (`markov.py`), and the orchestration/ranking layer
  (`analysis_engine.py`) all ran successfully on the first architecture
  attempt, once dependencies were installed. No hallucinated APIs, no
  invented price data — every number in `output/report.md` traces back to
  a live `yfinance` call, not model recall.
- 100,000-path simulations × 4 tickers × 2 models completed in ~11 seconds
  of CPU time, vectorized with numpy. No need to cut the simulation count
  to make it tractable.

## Manual interventions required

1. **Markdown table export** needed the `tabulate` package, not caught
   until the first run — added to `requirements.txt` and installed.
2. **"No recovery" case displayed as `NaN`** in the first report draft
   (Python `None` → pandas `NaN` in a mixed int/None column). Fixed to
   display `>40` so a reader doesn't mistake "didn't recover" for "missing
   data."
3. **Sanity-checked an unexpected result by hand** rather than trusting it:
   AGNC and TTE both showed a 1-trading-day "recovery," which looked at
   first glance like an off-by-one bug. Traced it through manually (see
   below) and confirmed it's a real, explainable property of the data, not
   a defect — but it required stepping outside the pipeline to verify.

## Where the statistical model differs from reality (important)

This is the main finding worth flagging, not just a footnote:

**The Markov states are derived purely from past price action and have no
awareness that a dividend date is coming.** Verified directly against
AGNC's most recent ex-dividend event: actual closing prices rallied from
$10.11 to $11.00 over the 15 trading days before the ex-div date — the
"pre-dividend buying ramp" the project brief describes as a real phenomenon.
The conservative model's *simulated* expected price over that same window
stayed essentially flat (10.11 → 10.08, i.e. drifting slightly down). See
`output/AGNC_paths.png` — the black actual-price line visibly diverges from
both dashed model lines well before the vertical ex-div marker.

This isn't a bug in the code; it's an inherent property of first-order
Markov chains built only from recent return states, exactly as the project
brief's own "Technical Appendix" limitation section predicts: *"Financial
markets exhibit non-stationary distributions... standard first-order Markov
chains must often be augmented... for higher fidelity."* In practice this
means:

- The **entry-point search** (lowest expected price in the 15 days before
  ex-div) is not reliably finding a genuine pre-ramp trough — for 3 of 4
  tickers it converged to a window boundary rather than an interior
  minimum, which is a sign the model sees a roughly monotonic trend, not a
  trough-then-ramp shape.
- The **exit/recovery numbers are more trustworthy** than the entry numbers,
  because they're anchored to an actual observed starting price
  (`ex_close`) and a fixed, data-derived target — the model only has to
  extrapolate forward, not detect a turning point.
- The **recovery day = 1** results for AGNC/TTE are real but somewhat
  hollow: they reflect that both tickers' historical `Q_ratio` (price drop
  ÷ dividend) is comfortably below 1.0, so the *actual* ex-dividend price
  already satisfies the recovery condition almost immediately — the model
  barely needs to do any predictive work to reach that answer. It's a
  genuine data pattern, but "the strategy recovers instantly" for those two
  is really a restatement of "these stocks historically don't drop by the
  full dividend amount," which you could see directly from `Q_ratio` alone
  without running any simulation.

## Interface layer (session 2)

The ranked dashboard and earnings calculator (`interface/index.html`) are
arithmetic on numbers this report already covers — they don't introduce a
new model. Two things worth flagging about how that arithmetic is
presented:

- **The calculator shows a point estimate, not a range.** It uses the mean
  of 100,000 simulated paths as if it were a single known future price. The
  simulation itself produces a full distribution (visible qualitatively in
  the fan-chart PNGs), but the calculator collapses that to one number per
  side of the trade. A reader could reasonably mistake "$461.31 estimated
  earnings" for a forecast rather than an average-case backtest output.
- **It inherits the entry-timing weakness directly into a "Buy" column.**
  Because the interface presents `buy_days_before_ex` as an actionable
  instruction ("Buy 15d before ex-div") rather than as a research output,
  it's more likely to be read as a recommendation than the raw CSV was.
  The disclaimer banner and the not-recovered warning are there to counter
  that, but the framing risk is real and worth being aware of.

## Session 3: accuracy optimizations

Asked to research and implement ways to make the calculations more
accurate. Researched first (web search — GARCH/regime-switching literature,
ex-dividend event-study literature, Monte Carlo variance reduction,
walk-forward backtest aggregation — see `docs/system_architecture.md` for
the specific references), then implemented four changes: a GARCH(1,1)
volatility filter replacing the old ad hoc winsorizing, an explicit
ex-dividend calendar-drift term, antithetic variance reduction, and
multi-event backtest aggregation (up to 8 historical events per ticker
instead of 1). Full rationale for each is in
`docs/system_architecture.md` §§2–4.

**A real bug was caught by testing, not assumed away.** The first version of
the calendar-drift term used the full 15-day-before / 40-day-after window to
average each ticker's historical ex-dividend events. For the monthly-paying
REITs (AGNC, O, STAG), consecutive ex-dividend dates are only ~21 trading
days apart — far shorter than the 55-day window — so each event's window
was overlapping the *neighboring* dividend cycle, contaminating the
"seasonal" average with unrelated dynamics. Caught by actually plotting the
result (a chart with plotted entry-window paths, which the session-1/2
version never rendered — a second small gap this session closed) rather
than trusting the number in isolation. Fixed by capping the calendar
window per ticker to at most half its own median trading-day gap between
events (9 days either side for the monthly REITs; the full 15/40 for TTE's
quarterly ~62-day gap), leaving no calendar signal (zero, not a
contaminated one) beyond that.

**The multi-event backtest overturned a conclusion from session 2.** The
session-2 report treated AGNC's ~9%-over-15-days pre-dividend rally as
evidence of the "pre-dividend buying ramp" the project brief describes, and
flagged the model for missing it. With the calendar-drift fix now averaging
cleanly across AGNC's **56** prior ex-dividend events (using the
non-contaminated 9-day window), the honest historical average for AGNC
going into an ex-dividend date is a mild **decline** (~−1.5% over 9 trading
days), not a ramp. The single dramatic rally used in the session-2 example
was real but was not representative — exactly the failure mode multi-event
backtesting exists to catch. TTE (quarterly dividends, wide enough gap to
need no window capping) shows the opposite pattern: its exit-side expected
path now visibly slopes upward following the calendar term, and 8/8
backtested events recovered (100% hit rate) — though TTE's own huge
pre-dividend rally in the headline event ($80→$91.50 over one specific
quarter, most likely oil-price-driven) is *also* not fully reproduced by
the entry-side forecast, appropriately, since that was a one-off macro move
rather than a recurring seasonal pattern across TTE's other dividend
cycles. Put plainly: the upgraded model now correctly distinguishes "this
ticker reliably ramps before its dividend" (not really true for any of
these four, on the evidence) from "this specific quarter happened to rally"
— which the session-2 single-event version could not tell apart.

**Net effect on the numbers**: rankings now carry `n_backtest_events`,
`hit_rate_pct`, and `std_return_per_cycle_pct` columns so a reader can see
the sample size and spread behind each score, not just a point estimate —
directly addressing the "point estimate, not a range" gap flagged in the
session-2 interface note above. The interface's calculator now shows the
backtested mean ± 1 standard deviation next to its single-event dollar
estimate for the same reason.

## Edge cases encountered

- STAG's most recent ex-dividend event showed a **negative** drop
  (`Q_ratio = −0.69`): the closing price was *higher* on the ex-dividend
  day than the day before. Plausible explanation, not a data error — STAG's
  dividend is small relative to its normal daily price noise, so on any
  given event ordinary volatility can swamp the theoretical drop. This is
  exactly the kind of thing the brief's `Q` ratio discussion anticipates
  for different sectors.
- O and STAG did not reach their recovery target within the 40-day window
  under the conservative model — reported as `>40` rather than omitted, so
  the ranking reflects "this didn't work" instead of silently excluding
  the ticker.

## Bottom line (updated session 3)

The pipeline is mechanically sound and the numbers in `output/report.md`
are real, traceable, and internally consistent. Session 3's changes made
the model more honest, not just more sophisticated: it now *has* a
mechanism to anticipate calendar-driven demand (the calendar-drift term),
and the multi-event backtest exposed that, for three of the four tickers
tested, that anticipated demand is weak-to-negative rather than the ramp
originally assumed — a real, useful, if less exciting finding than "the
model just needs a calendar feature and then it'll see the ramp." The
recovery/exit side of the forecast visibly improved (compare the
`_paths.png` charts before/after — the exit curves now slope in the right
direction rather than sitting nearly flat), and every ranking number now
carries a sample size and spread instead of being a single event's anecdote.

What the model still can't do, and shouldn't be expected to: predict a
one-off macro-driven rally (TTE's ~14% pre-dividend move in the headline
quarter) from historical price statistics alone — that's a fundamentals/
news question, out of scope for a Markov-family model regardless of how
it's tuned. The entry-timing numbers are more trustworthy than session 2's
version, but "more trustworthy" here means "correctly reports a weak
signal," not "reliably predicts a strong one."

None of this is a reason to treat the ranking as a trading signal — see the
"not investment advice" note in `CLAUDE.md`. It's a research scaffold whose
biggest remaining gap is the one named in `docs/system_architecture.md`'s
"Known limitations": GARCH's mean equation is fixed at zero, so any
directional drift beyond regime persistence and the (now properly windowed)
calendar term isn't modeled at all.

## Session 6: accuracy optimizations, and a real numerical bug

Asked, again, to research and implement accuracy improvements. Researched
first (EGARCH vs. GJR-GARCH vs. GARCH for equity volatility, Wilson score
confidence intervals for small-sample proportions — see
`docs/system_architecture.md` for citations), then implemented: EGARCH
replacing symmetric GARCH (captures the equity "leverage effect" GARCH
structurally can't represent), Wilson confidence intervals on hit rate
(both displayed and used directly in the ranking formula), and raising the
backtest sample cap from 8 to up to 50 events per ticker (runtime allowed
it — still under 20 seconds end to end).

**Testing the sample-size increase surfaced a real, previously-latent
numerical bug**, not present at the old cap by luck rather than by design:
some historical windows' EGARCH fits converge (the optimizer reports
success) to parameters that are numerically nonsensical. Traced one
specific case (`O`, fit window ending 2023-02-28): a Student-t fit's
degrees-of-freedom estimate landed at `ν≈2.08` — right at the boundary
where the Student-t distribution's variance stops being finite. This
produced `alpha=748.7`, `gamma=234.3`, `beta=1.0` (typical sane values are
all well under 1) and a forecasted variance of `e^710`, several hundred
orders of magnitude past what a `float64` can represent. The simulated
price paths overflowed to `inf`, then `inf - inf` arithmetic downstream
produced `nan`, silently corrupting that ticker's aggregate backtest
statistics.

This was **not** caught by checking `res.convergence_flag` — the optimizer
considered this fit successful. Each attempted fix was verified by
re-running the specific failing case in isolation before moving on, rather
than assuming a plausible-sounding patch had worked:
1. First attempt: clip the log-variance *recursion* to a wide band. Didn't
   fully fix it — the band (±15 in log-space) was still wide enough to
   permit an absurd sigma (~360,000% daily volatility).
2. Second attempt: clip the recursion to a *realistic* band (±4, anchored
   to the window's own empirical log-variance). Reduced but didn't
   eliminate the problem — the bootstrapped *residual pool itself*
   contained values in the hundreds (a symptom of the same degenerate fit:
   its in-sample conditional volatility estimates collapsed to near-zero
   for a few days, making `residual / near-zero-volatility` explode), so
   even a correctly-bounded sigma multiplied by an unbounded `z` still blew
   up over a 40-day compounding horizon.
3. Third attempt (the one that actually fixed it): clip the standardized
   residual pool itself to ±10 before it gets bootstrapped, **and**
   explicitly detect and reject a degenerate parameter set
   (`|alpha|>20`, `|gamma|>20`, or `|beta|≥1`) rather than trying to
   numerically patch its output into looking plausible — retry once with a
   Normal distribution (no degrees-of-freedom parameter to degenerate), and
   if that also fails, skip that one historical event from the backtest
   rather than let corrupted numbers into an aggregate.

The general lesson, consistent with this project's existing "don't guess,
verify" pattern: a downstream numerical patch (clipping the recursion) can
mask a symptom without fixing the cause, and can require multiple
iterations to even fully mask it. Rejecting a bad fit at the source, once
identified, was simpler and more honest than chasing tighter and tighter
clips.

A second, independent bug surfaced by the same higher-sample-size testing:
`_usable_event_indices` only required `PRE_WINDOW` (15) days of pre-event
history, nowhere near enough to fit a stable model (especially the
"recent" variant's 252-day lookback). Fixed with an explicit
`MIN_FIT_HISTORY = 300` floor. Both bugs were latent at the old cap of 8
events (which happened to stay within recent, well-behaved history) —
another argument, beyond the intended statistical-power motivation, for
why raising the sample size was worth doing carefully rather than assumed
safe by default.

**Also fixed in passing, unrelated to the above**: `trailing_dividend_yield`
returned `NaN` for every ticker on this session's first run.
`data_io.fetch_history` was returning a trailing row for the most recent
session with a `NaN` Close — `yfinance` occasionally appends a
not-yet-finalized row before a session's data is complete. Now dropped at
ingestion (`fetch_history` filters `Close.notna()`) rather than left to
propagate NaN into whatever downstream calculation happens to touch the
last row first.
