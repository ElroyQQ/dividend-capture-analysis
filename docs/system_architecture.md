# System Architecture

## Purpose

Research/backtesting prototype for a dividend-capture strategy: buy before an
ex-dividend date, collect the payout, and determine (via simulation) how long
a position should realistically be held afterward to recover the ex-dividend
price drop. This is **not** a live trading system — it does not place orders
or hold API credentials for a broker.

## Pipeline

```
data_io.py          →  markov.py              →  analysis_engine.py
(fetch real prices)    (fit models, simulate)     (entry/exit search, ranking, report)
```

### 1. Data ingestion — `src/data_io.py`

- `fetch_history(ticker, period="5y")`: pulls daily OHLCV + dividend history
  from Yahoo Finance via `yfinance`. No prices are ever typed in by hand or
  guessed by an LLM — every number traces back to this API call.
- `ex_dividend_events(history)`: for every day a dividend was paid, records
  the prior close (`cum_close`), same-day close (`ex_close`), the drop, and
  `Q_ratio = drop / dividend` (see Technical Appendix in the project brief —
  `Q_ratio` near 1.0 means the price drop matched the dividend almost
  exactly; below 1.0 means the stock historically "shrugs off" more of the
  dividend than theory predicts).
- `trailing_dividend_yield(history)`: trailing-12-month dividends ÷ latest
  close.

### 2. EGARCH-filtered regime-bootstrap Markov / Monte Carlo engine — `src/markov.py`

Session 3 upgraded this from a plain quantile-bucketed return bootstrap to a
**filtered historical simulation** using symmetric GARCH(1,1). **Session 6
upgraded GARCH → EGARCH(1,1,1)** to capture the well-documented equity
"leverage effect" (a down move raises future volatility more than an equal-
sized up move) — plain GARCH can't represent that asymmetry at all, and
EGARCH is reported in the literature as producing the best equity
volatility forecasts among the common GARCH-family models (see references
at the end of this file):

- An **EGARCH(1,1,1)** model (via the `arch` package) is fit to daily log
  returns first. `conservative` uses a Student-t error distribution on the
  full price history (down-weights the influence of extreme spikes on the
  fitted parameters); `recent` uses a Normal distribution on the trailing
  ~252 trading days. Mean equation is fixed at zero (`mean="Zero"`) —
  volatility only; any directional drift comes from the regime bootstrap's
  own skew and, separately and deliberately, the calendar-drift term below.
- The model's **standardized residuals** (`return / conditional_volatility`)
  — not raw returns — are bucketed into 5 quantile-based states. Stripping
  out volatility before classifying states makes the regime signal closer
  to stationary than classifying raw returns directly, which is what the
  project brief's own limitation note ("financial markets exhibit
  non-stationary distributions... must often be augmented") was flagging.
- `simulate()` rolls the EGARCH **log-variance recursion**
  (`ln σ²_t = ω + β·ln σ²_{t-1} + α·(|z_{t-1}| − E|z|) + γ·z_{t-1}`, where
  `γ` is the asymmetry/leverage term GARCH doesn't have) forward per
  simulated path, drawing each day's shock `z` from the current regime
  state's bootstrapped residual pool and scaling by the *current*
  EGARCH-forecasted volatility. `E|z|` is estimated empirically from the
  fit's own residuals rather than assumed from a parametric distribution,
  consistent with bootstrapping empirical residuals elsewhere. Default:
  100,000 paths for the headline event.
- **Antithetic variates**: half the paths are simulated normally; the other
  half reuses the *same drawn shock magnitudes*, negated. Unlike symmetric
  GARCH (where this made the mirrored path's whole volatility trajectory
  identical to the base path's), EGARCH's recursion is *not* invariant to
  the shock's sign — that asymmetry is the entire point of using it — so
  both signs run their own log-variance recursion from the same starting
  point, sharing only the drawn `|z|` magnitudes and state sequence. Still
  a valid, cheap variance-reduction pairing on the return draws themselves.
- `apply_calendar_drift()`: multiplies a deterministic, ticker-specific
  seasonal adjustment into the simulated paths (see below) — kept separate
  from the random EGARCH process since it's not a random shock.

**Numerical safety net (session 6)**: backtesting many historical windows
surfaced a real failure mode — a Student-t fit whose degrees-of-freedom
estimate landed near the finite-variance boundary (`ν≈2`) produced
parameters two-plus orders of magnitude outside any sane range (`alpha≈749`,
`gamma≈234`), which blew the simulated price paths up to `inf`/`nan` over a
40-day horizon. `convergence_flag == 0` (the optimizer's own "success"
signal) did **not** catch this — it's a degenerate optimum, not a failed
search. Three layers now guard against it, in order of how far upstream
they act:
1. `_is_degenerate()` rejects a fit outright if `|alpha| > 20`, `|gamma| >
   20`, or `|beta| ≥ 1` — a Student-t fit that fails this gets one retry
   with a Normal distribution (which has no degrees-of-freedom parameter to
   degenerate); if that also fails, `fit_model()` raises
   `DegenerateFitError` and the caller skips that one historical event
   rather than let corrupted numbers into an aggregate.
2. Standardized residuals are clipped to `±10` before being bootstrapped —
   a well-behaved residual is roughly unit-scale, so a value in the
   hundreds (found empirically on the degenerate fit above) is a numerical
   artifact, not real market behavior.
3. The starting and per-step log-variance are each clipped to a `±4` band
   around a data-grounded reference (the window's own empirical
   log-variance, and the simulation's own starting point, respectively) —
   generous for real volatility regimes (daily sigma up to ~7x either
   direction) without leaving room for runaway values.

### 3. Ex-dividend calendar drift — `data_io.seasonal_return_pattern()`

Addresses the specific blind spot flagged after session 2: a memoryless
Markov chain has no notion that a dividend date is approaching, so it can't
reproduce a pre-dividend run-up or post-dividend drift even if one exists.
For each ex-dividend event, this averages the aligned cumulative-log-return
curve from all of that ticker's *prior* ex-dividend events (no lookahead),
producing a plain event-study seasonal average (not a CAPM/market-model
abnormal return — no benchmark index is subtracted).

**Important correction made during this session**: the naive version of
this (window = the full 15 pre / 40 post trading days) badly overlapped
neighboring events for monthly-paying tickers — AGNC/O/STAG pay dividends
roughly every 21 trading days, far shorter than the 55-day window, so each
event's "post" period bled into the *next* event's pre-ramp and vice versa.
The window is now capped per ticker to at most half its own median
trading-day gap between ex-dividend events (`event_gap // 2 - 1`, floor 3
days) — 9 days either side for the monthly REITs, the full 15/40 for TTE's
~62-trading-day quarterly gap. Days beyond the safe window get zero
calendar drift rather than a contaminated one.

### 3.5. Ticker universe and the "top N" (session 8)

Until session 8, `TICKERS` was a fixed 4-symbol starter set, and the
dashboard just ranked those 4 against each other — there was no sense in
which a "top 5" could change, since only 4 tickers ever existed to rank.
Prompted by a user question ("how would it update if the top 5 changes"),
`TICKERS` is now a diversified **17-symbol universe** (energy, REITs of
several kinds, telecom, consumer staples, healthcare, utilities, a BDC,
industrials, financials), and `TOP_N` (5) controls how many of those,
by `risk_reward_score`, count as "top":

- `main()` now ranks **before** generating the comparison chart, so
  `plot_comparison_chart()` can be told which tickers are actually
  top-N this run (`df["ticker"].iloc[:TOP_N]`) — the chart shows only
  those, both for legibility (17 overlaid lines would be unreadable) and
  because that's the comparison a viewer actually wants.
- `build_interface_records()` stamps each record with `isTopN`
  (`rank <= TOP_N`), which the interface uses to filter the "Top N quick
  picks" table to just those and to badge them (★, gold border) in the
  full "All ranked stocks" list, which shows every analyzed ticker.
- **This is the actual answer to "how does it update if the top 5
  changes":** the top 5 is computed fresh every run of `analysis_engine.py`
  from `risk_reward_score` — if a ticker's backtest results shift enough
  (or you add/remove tickers from `TICKERS`) to change the ranking, the
  quick-picks table, the comparison chart, and every "★ TOP N" badge all
  follow automatically on the next run. There's still no *automatic*
  discovery of new candidate tickers from the broader market (`TICKERS`
  is edited by hand) — only the ranking *among* whatever's in `TICKERS` is
  dynamic.
- Runtime scales roughly linearly with ticker count: ~50s for 17 tickers
  vs. ~18s for 4, still comfortably interactive.

### 4. Multi-event backtest + orchestration — `src/analysis_engine.py`

The original version scored each ticker off a single historical ex-dividend
event — statistically an N=1 anecdote. Now, for every ticker:

- **Event eligibility (`_usable_event_indices`, tightened session 6)**: an
  ex-dividend event needs both enough post-event data for the search window
  *and* `MIN_FIT_HISTORY` (300 trading days) of **pre**-event history — not
  just `PRE_WINDOW`. An event with only 20 days of prior history technically
  has enough for the entry-window search itself, but nowhere near enough to
  fit a stable EGARCH model (particularly the "recent" variant's 252-day
  lookback). Events that early were a second, independent source of the
  bad-fit problem described above, found the same way: by testing with a
  larger `MAX_BACKTEST_EVENTS` and tracing the resulting `NaN` back to its
  source rather than assuming it away.
- **Backtest loop**: the most recent `MAX_BACKTEST_EVENTS` (**50**, raised
  from 8 in session 6 — full pipeline runtime is still under 20 seconds, so
  the original cap was leaving statistical power on the table) usable
  ex-dividend events each get the full entry/exit Monte Carlo search (8,000
  paths each). Results are aggregated into `hit_rate` (with a **95% Wilson
  confidence interval**, see below), `mean`/`std` of net return per cycle,
  and `median_recovery_days`. Events whose fit is rejected as degenerate
  (see above) are skipped, not padded with a guess — `n_events` in the
  output reflects the actual usable sample, which can be meaningfully
  smaller than `MAX_BACKTEST_EVENTS` (e.g. TTE, with only ~19 quarterly
  events in 5 years total).
- **Headline event**: the most recent event that produces a *non-degenerate*
  fit (tries up to the 6 most recent before giving up) gets a full
  100,000-path run (`keep_paths=True`) purely for the interface's chart and
  "buy/sell this specific event" display numbers.
- **Entry search**: lowest mean-expected-price day in the 15 trading days
  before the ex-div date (EGARCH + calendar-drift driven, not a flat
  bootstrap).
- **Exit search**: first day after the ex-div date where mean expected
  price + dividend ≥ pre-dividend price.
- **`wilson_interval(successes, n)`**: a 95% Wilson score confidence
  interval on the hit rate — chosen over a naive ± on the raw percentage
  because it has much better coverage at small `n` and doesn't collapse to
  zero width at 0%/100% (a naive interval would report "100% hit rate,
  ±0%" off an `n=8` sample, which is not remotely justified). See
  references below.
- **Ranking**: `risk_reward_score = mean_return_per_cycle% × wilson_lower_bound(hit_rate)
  ÷ mean_hold_days` (conservative model) — return per day held, discounted
  by the Wilson interval's *lower* bound rather than the raw hit rate, so a
  ticker whose "100%" is backed by only a handful of events doesn't
  automatically outrank one with a slightly lower but much better-supported
  rate.

Outputs land in `output/`: `report.md` (human-readable), `ranking.csv`
(machine-readable), and one `<ticker>_paths.png` chart per ticker showing
actual price vs. both models' expected paths (now spanning the *entry* and
exit windows) around the headline event, annotated with the backtest hit
rate.

### References consulted (session 3 + session 6)

- Filtered historical simulation (GARCH + bootstrap): `arch` package docs
  (bashtage.github.io/arch), and the general FHS approach described in
  risk-management literature (e.g. MathWorks' bootstrapping/FHS example).
- Ex-dividend price run-up / event-study methodology: academic event-study
  literature on dividend announcement effects (e.g. Frontiers in Applied
  Mathematics and Statistics, 2025; Review of Quantitative Finance and
  Accounting on calendar anomalies and dividend announcements).
- Antithetic variates for Monte Carlo variance reduction: standard
  technique, e.g. Columbia IEOR E4703 lecture notes on Monte Carlo variance
  reduction.
- Multi-event/walk-forward backtest aggregation: standard practice in
  quantitative strategy validation (e.g. QuantInsti, Interactive Brokers'
  Quant News "Walk Forward Analysis").
- EGARCH vs. GJR-GARCH vs. GARCH for equity volatility (leverage effect):
  academic comparisons (e.g. a 2025 realized-EGARCH study on the Nikkei
  225) reporting EGARCH as producing the best equity volatility forecasts
  among the common GARCH-family variants.
- Wilson score confidence intervals for small-sample binomial proportions
  (hit rate): standard statistics reference (e.g. statisticshowto.com),
  chosen specifically for its coverage advantage over a naive Wald interval
  at small `n` and at proportions near 0%/100%.

### 5. Interface — `src/interface_template.html` → `interface/index.html`

`build_interface_records()` reshapes the per-ticker results (both model
variants) into a JSON array — rank, category, trailing yield, buy/sell
timing in trading days relative to the ex-dividend date, expected
entry/exit prices, net return per cycle, and a path to that ticker's chart.
`write_interface()` injects that JSON into `src/interface_template.html`
(replacing the `__STOCK_DATA__`/`__GENERATED_AT__`/`__POST_WINDOW__`
placeholders) and writes the result to `interface/index.html` — a static,
dependency-free page (vanilla JS, no build step, consistent with the rest
of this project).

The page has two parts:
- **Ranked list** (cards or table view): sorted by `risk_reward_score`,
  toggleable between the conservative and recent-movement models, each
  entry linking to its `output/<ticker>_paths.png` chart.
- **Earnings calculator**: given a deposit amount and a chosen ticker, computes
  shares purchased at the model's expected entry price, dividend received,
  price gain/loss to the expected exit price, and total estimated earnings —
  using the *same* numbers already in `ranking.csv`, just multiplied through
  by a dollar amount. It does not run a new simulation; it's arithmetic on
  the existing per-model entry/exit price estimates, so it inherits every
  limitation described below and in `AI_Performance_Report.md`.

Because the JSON is inlined at generation time, the page is a **snapshot**:
rerunning `analysis_engine.py` regenerates it from fresh data, but the file
itself doesn't fetch anything live when opened.

**`classify_suitability(df)`** (session 4) adds a plain-language "who is
this for" label per ticker — `Conservative pick` / `Aggressive pick` /
`Balanced` / `Not recommended` — computed from the conservative model's
backtest stats only (hit rate, mean return, std of return), using
thresholds relative to the current ticker set's own median rather than
fixed constants:
- `Not recommended` if hit rate < 60% or mean return ≤ 0, regardless of
  everything else.
- `Conservative pick` if hit rate is at/above both 75% and the group's
  median, **and** the return's std dev is at/below the group's median —
  reliable and comparatively low-swing.
- `Aggressive pick` if mean return is at/above the group's median but it
  didn't qualify as conservative — biggest average payoff, less consistent.
- `Balanced`: everything else.

This label is deliberately independent of the conservative/recent model
toggle (it doesn't change when the viewer switches models) — it's meant to
answer "which stock suits my risk tolerance," a different question from
"which calculation method did the computer use," and mixing the two would
undermine the point of labeling it at all. The interface's guide panel
explains this distinction explicitly, since both concepts use the word
"conservative" and are easy to conflate.

A companion `## Quick picks` table (ticker → best-for label → one-line
reason) is written into `output/report.md` from the same function, so the
CSV/report/interface all agree.

**`plot_comparison_chart()` / `output/comparison_paths.png`** (session 7):
overlays every ticker's *actual* (not simulated) price around its headline
ex-dividend date, indexed to 100 on that day, on one chart — lets a viewer
compare volatility and recovery shape across tickers at a glance, which
separate per-ticker charts (each with its own y-axis scale) don't support.
Colors are the first four slots of the dataviz reference categorical
palette in their validated fixed order; each line also gets a direct
end-of-line label, since two of those four slots (aqua, yellow) don't
clear 3:1 contrast on the chart's white background and shouldn't rely on
a legend swatch alone.

**Auto-refresh (session 7)**: the page reloads itself from disk every 60
seconds, with a visible pulsing-dot countdown indicator in the header. This
is a plain `location.reload()` — the page still doesn't fetch live data or
re-run the analysis itself (it's a generated snapshot, per above); it only
shows new numbers once something else has regenerated `interface/index.html`
in the meantime. The guide panel explains this distinction explicitly, so
the indicator doesn't imply more liveness than the architecture actually
has.

## Known limitations (updated session 6)

- **The calendar-drift term is a historical average, not a forecast of
  future demand.** It corrects the "the model can't see the calendar at
  all" blind spot, but it can only reproduce a pre-dividend ramp if one
  actually, reliably occurred in that ticker's own history. It cannot and
  should not predict a one-off macro-driven rally (see the TTE finding in
  `AI_Performance_Report.md`) — that would require a market/fundamentals
  model this project doesn't have.
- **The safe calendar window for monthly payers is short (9 trading days
  either side)** by construction, to avoid contaminating the estimate with
  the neighboring dividend cycle. Days further out than that in the 15/40
  entry/exit window get no calendar signal at all, not a best-effort one.
- **EGARCH's mean equation is fixed at zero.** Any general (non-calendar,
  non-regime) directional drift a ticker might have is not modeled — a
  deliberate choice to avoid conflating a noisy naive drift estimate with
  the volatility model, but it does mean the simulation won't reproduce a
  sustained trend that isn't captured by regime persistence or the
  calendar term. Unchanged by the GARCH→EGARCH upgrade — EGARCH fixed the
  *volatility* model's symmetry assumption, not this one.
- **The backtest is capped at 50 events per ticker** (raised from 8 in
  session 6), most recent first, and further limited by `MIN_FIT_HISTORY` —
  for TTE's quarterly dividends that's its full ~5-year usable history
  (~13-14 events); for the monthly REITs, roughly 3 years. `median_Q_ratio`
  alone is still computed over the full 5y window regardless of the
  backtest cap.
- **A small fraction of historical windows produce a fit degenerate enough
  to reject outright** (see the numerical-safety-net note above) — those
  events are silently absent from `n_events`, not flagged individually in
  the output. If a ticker's `n_events` looks surprisingly low relative to
  its total dividend history, this is the likely reason; it isn't currently
  surfaced as its own statistic.

See `AI_Performance_Report.md` for what these look like empirically,
including a specific example where the multi-event backtest overturned a
conclusion the single-event version of this tool had drawn, and the
session-6 debugging trail for the degenerate-fit numerical issue.
