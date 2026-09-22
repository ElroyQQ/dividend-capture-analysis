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

### 2. GARCH-filtered regime-bootstrap Markov / Monte Carlo engine — `src/markov.py`

Upgraded in session 3 from a plain quantile-bucketed return bootstrap to a
**filtered historical simulation** — a standard technique for capturing
volatility clustering (see references at the end of this file):

- A **GARCH(1,1)** model (via the `arch` package) is fit to daily log
  returns first. `conservative` uses a Student-t error distribution on the
  full price history (down-weights the influence of extreme spikes on the
  fitted parameters — replacing the old ad hoc return-winsorizing);
  `recent` uses a Normal distribution on the trailing ~252 trading days.
  Mean equation is fixed at zero (`mean="Zero"`) — GARCH here models
  volatility only; any directional drift comes from the regime bootstrap's
  own skew and, separately and deliberately, the calendar-drift term below.
- The model's **standardized residuals** (`return / conditional_volatility`)
  — not raw returns — are bucketed into 5 quantile-based states. Stripping
  out volatility before classifying states makes the regime signal closer
  to stationary than classifying raw returns directly, which is what the
  project brief's own limitation note ("financial markets exhibit
  non-stationary distributions... must often be augmented") was flagging.
- `simulate()` is a **regime bootstrap on top of a live GARCH variance
  recursion**: at each simulated day, the next state is drawn from the
  transition matrix, an actual historical standardized residual from that
  state's pool is resampled, scaled by the *current* GARCH-forecasted
  volatility (not a flat historical average), and the GARCH variance
  recursion (`σ²_t = ω + α·ε²_{t-1} + β·σ²_{t-1}`) is rolled forward
  per simulated path. Default: 100,000 paths for the headline event.
- **Antithetic variates**: half the paths are simulated normally; the other
  half mirrors them by negating each day's drawn shock. Because the GARCH
  variance recursion depends on `ε²` (sign-invariant), the mirrored path's
  volatility trajectory is identical — only the return signs flip — so this
  is a cheap, exact variance-reduction technique here, not an approximation.
- `apply_calendar_drift()`: multiplies a deterministic, ticker-specific
  seasonal adjustment into the simulated paths (see below) — kept separate
  from the random GARCH process since it's not a random shock.

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

### 4. Multi-event backtest + orchestration — `src/analysis_engine.py`

The original version scored each ticker off a single historical ex-dividend
event — statistically an N=1 anecdote. Now, for every ticker:

- **Backtest loop**: the most recent `MAX_BACKTEST_EVENTS` (8) usable
  ex-dividend events each get the full entry/exit Monte Carlo search
  (8,000 paths each, for runtime — antithetic variates make this still a
  reasonably low-noise estimate). Results are aggregated into `hit_rate`
  (fraction that recovered within the 40-day window), `mean`/`std` of net
  return per cycle, and `median_recovery_days`.
- **Headline event**: the single most recent event additionally gets a
  full 100,000-path run (`keep_paths=True`) purely for the interface's
  chart and "buy/sell this specific event" display numbers.
- **Entry search**: lowest mean-expected-price day in the 15 trading days
  before the ex-div date (now GARCH + calendar-drift driven, not a flat
  bootstrap).
- **Exit search**: first day after the ex-div date where mean expected
  price + dividend ≥ pre-dividend price.
- **Ranking**: `risk_reward_score = mean_return_per_cycle% × hit_rate ÷
  mean_hold_days` (conservative model) — return per day held, discounted by
  how reliably the backtest actually recovered, backed by up to 8 historical
  trials instead of one.

Outputs land in `output/`: `report.md` (human-readable), `ranking.csv`
(machine-readable), and one `<ticker>_paths.png` chart per ticker showing
actual price vs. both models' expected paths (now spanning the *entry* and
exit windows) around the headline event, annotated with the backtest hit
rate.

### References consulted for this session's methodology

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

### 4. Interface — `src/interface_template.html` → `interface/index.html`

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

## Known limitations (updated session 3)

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
- **GARCH's mean equation is fixed at zero.** Any general (non-calendar,
  non-regime) directional drift a ticker might have is not modeled — a
  deliberate choice to avoid conflating a noisy naive drift estimate with
  the volatility model, but it does mean the simulation won't reproduce a
  sustained trend that isn't captured by regime persistence or the
  calendar term.
- **The backtest is capped at 8 events per ticker** for runtime, most
  recent first — for TTE's quarterly dividends that's 2 years of history;
  for the monthly REITs, about 8 months. Longer history is available (see
  `median_Q_ratio`, computed over the *full* 5y window) but isn't run
  through the full Monte Carlo search.

See `AI_Performance_Report.md` for what these look like empirically,
including a specific example where the multi-event backtest overturned a
conclusion the single-event version of this tool had drawn.
