# CLAUDE.md

Master context file for this project. (Named `CLAUDE.md`, uppercase, so
Claude Code auto-loads it — functionally the same file the project brief
calls `Claude.md`.)

## What this is

A **research/backtesting prototype**, not a live trading system. It tests
whether a "dividend capture" strategy (buy before ex-dividend, collect the
payout, sell after) can be timed to net a gain using an EGARCH-filtered
regime-bootstrap Markov-chain Monte Carlo model of historical daily price
movements (session 6 upgraded GARCH→EGARCH for the equity "leverage
effect"), with an explicit ex-dividend calendar-drift term and multi-event
backtesting reported with Wilson confidence intervals, not bare percentages
(session 3, extended session 6). The generated dashboard
(`interface/index.html`) also includes a plain-language usage guide and a
"Quick picks" table classifying each stock as a Conservative/Aggressive/
Balanced/Not-recommended pick (session 4). See
[docs/system_architecture.md](docs/system_architecture.md) for the full
pipeline and [AI_Performance_Report.md](AI_Performance_Report.md) for an
honest assessment of where the model does and doesn't work.

## Hard constraints (do not relax these without the user explicitly asking)

- **No broker connections, no order placement, no credentials.** This
  project only reads public market data (via `yfinance`) and writes
  analysis output to `output/`. Do not add Interactive Brokers API
  integration, credential handling, or anything that submits a real order,
  even "semi-automated," unless the user explicitly asks for it in a future
  session — and even then, treat entering brokerage credentials as
  out-of-scope for an AI agent to do on the user's behalf.
- **No fabricated financial data.** Every price, dividend amount, or date
  used in analysis must come from the live `data_io.py` fetch calls, never
  typed in or "recalled" by an LLM. If `yfinance` fails for a ticker, the
  script should error, not fall back to a guessed number.
- **This is not investment advice.** Reports and rankings describe what the
  backtest found on historical data; they are not a recommendation to buy
  or sell anything. Keep that framing in any user-facing output, including
  `interface/index.html` (which carries its own disclaimer banner — don't
  remove it).
- **The interface's earnings calculator still shows a single-event dollar
  estimate** (the model's *mean* expected entry/exit price for the most
  recent event) alongside — as of session 3 — the multi-event backtest's
  mean ± std return, so the point estimate now has visible context. Don't
  remove the backtest context when touching the calculator; the dollar
  figures alone were flagged in session 2 as easy to mistake for a
  forecast.
- **EGARCH's mean equation is fixed at zero** (`mean="Zero"` in
  `markov.fit_model`) — deliberate, so the volatility model doesn't get
  conflated with a noisy naive drift estimate. Any directional signal in
  the simulation comes only from regime persistence and the explicit
  calendar-drift term. Don't add a nonzero mean without updating
  `docs/system_architecture.md`'s "Known limitations" section to match.
- **A degenerate EGARCH fit is a real, observed failure mode, not a
  hypothetical** (session 6 — see `AI_Performance_Report.md` for the full
  trail). `markov._is_degenerate()` rejects `|alpha|>20`, `|gamma|>20`, or
  `|beta|>=1`; `fit_model()` retries once with a Normal distribution and
  otherwise raises `DegenerateFitError`, which `analysis_engine.py` catches
  to skip that one historical event. Don't remove this check or widen its
  thresholds without re-verifying against the specific case documented
  there (`ν≈2` Student-t fit → `alpha=748.7`) — the optimizer's own
  `convergence_flag` does **not** catch this.
- **The standardized-residual bootstrap pool is clipped to ±10, and the
  log-variance recursion to ±4 around a data-grounded center** — both are
  load-bearing numerical safety nets (session 6), not arbitrary constants.
  Loosening either without re-running the degenerate-fit case in
  `AI_Performance_Report.md` risks reintroducing `inf`/`nan` output.
- **The calendar-drift window is capped per ticker** to at most half its
  median trading-day gap between ex-dividend events — this was a real bug
  fix (session 3), not a stylistic choice. Don't widen it back to the full
  15/40-day entry/exit window without re-checking for the
  neighboring-event contamination described in
  `docs/system_architecture.md` §3 and `AI_Performance_Report.md`.
- **The interface auto-reloads every 60s (`location.reload()`), which is
  purely a page refresh, not a live data feed** (session 7). Don't let the
  auto-refresh indicator's presence imply the page fetches anything itself
  — new numbers only appear after `analysis_engine.py` has actually been
  rerun. If a "live" data mode is ever built, that's a real architectural
  change (see `docs/system_architecture.md`), not just wiring this
  indicator up to something real.
- **The "Conservative pick" / "Aggressive pick" labels (`classify_suitability`
  in `analysis_engine.py`) are deliberately independent of the model toggle**
  (conservative/recent) — they answer "which stock suits my risk tolerance,"
  a different question from "which calculation method did the computer use."
  Both concepts use the word "conservative" for different things; the
  interface's guide panel explains the distinction explicitly (session 4) —
  don't remove that explanation if editing the guide, and don't make the
  suitability label change when the model toggle is switched.

## Running it

```bash
cd dividend-capture-analysis
.venv/bin/python src/analysis_engine.py
```

Outputs: `output/report.md`, `output/ranking.csv`, `output/<ticker>_paths.png`,
and `interface/index.html` (a generated, self-contained dashboard — see
below).

To change the ticker set, edit the `TICKERS` dict at the top of
`src/analysis_engine.py`. Full run (4 tickers, both models, headline +
up to 50-event backtest each) takes well under 20 seconds on this
machine — EGARCH fits and vectorized Monte Carlo are both cheap; if it's
ever slow, suspect a `yfinance` network stall, not the modeling code.

Dependencies (`requirements.txt`) include `arch` for GARCH modeling —
installing it pulls in `scipy`/`statsmodels`, which on a slow connection
can take several minutes even though the actual install is small; that's
normal, not a hang.

## Viewing the interface

`interface/index.html` is generated fresh by every `analysis_engine.py` run
(the data is inlined as JSON at generation time — it's a snapshot, not a
live-querying app). Open it either way:

- **Directly**: double-click it, or `open interface/index.html` — works in a
  normal browser since it just references sibling files with relative paths.
- **Served** (what this project's `.claude/launch.json` sets up for the
  Claude Code browser pane, which sandboxes bare `file://` pages one level
  up from here and breaks the chart images as a result):
  `python3 -m http.server --directory .` from the project root, then visit
  `/interface/index.html`.

It will go stale relative to `output/` if you rerun the analysis with
different tickers/window settings and forget to regenerate it — but
`analysis_engine.py` always regenerates it as part of `main()`, so a normal
run keeps it in sync automatically.

## Project structure

```
dividend-capture-analysis/
├── CLAUDE.md                    # this file
├── requirements.txt
├── .venv/                       # local virtualenv (not committed)
├── .git/                        # this project's own repo — github.com/ElroyQQ/dividend-capture-analysis
├── logs/
│   └── session_0N.md            # what happened in each build session (currently 01–07)
├── docs/
│   └── system_architecture.md   # pipeline + methodology detail
├── src/
│   ├── data_io.py                 # yfinance ingestion
│   ├── markov.py                  # state classification + Monte Carlo engine
│   ├── analysis_engine.py         # orchestration, ranking, report/chart/interface output
│   └── interface_template.html    # dashboard template (data injected at build time)
├── output/                       # generated report, csv, charts
├── interface/
│   └── index.html                # generated dashboard — ranking + earnings calculator
└── AI_Performance_Report.md
```

## Session continuity

Before starting new work in this project in a future session, read the most
recent file in `logs/` first — it records what was built, what broke, and
any modeling decisions made along the way, so you don't have to re-derive
them from the code.

## Repo status

This project is **its own git repository** (`github.com/ElroyQQ/dividend-capture-analysis`,
public), separate from the parent `Claude projects/` workspace's repo —
it was originally built untracked inside that outer repo (sessions 1–4),
then given its own history and pushed in session 5. The parent workspace's
`.gitignore` excludes this folder so it's never accidentally tracked from
there; always run `git` commands for this project from inside this folder,
not from the parent. See `logs/session_05.md` for how/why.
