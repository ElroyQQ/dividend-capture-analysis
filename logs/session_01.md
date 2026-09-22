# Session 01 — 2026-09-22

## Goal
Build the initial research prototype described in the project brief: a
Markov-chain/Monte Carlo backtester for a dividend-capture strategy, scoped
to a research prototype (no broker integration, no real orders), using free
`yfinance` data, on a representative starter set of tickers.

## Decisions made
- **Tickers**: TTE (TotalEnergies, "trade & exit" energy case from the
  brief) + O, AGNC, STAG (three monthly-paying REITs, "hold" case). Chosen
  to cover both asset-allocation categories the brief calls out.
- **States**: 5 quantile-based buckets on daily log returns, fit
  per-ticker rather than using a fixed % threshold, so volatile REITs
  (AGNC) and a steadier energy major (TTE) get comparably meaningful
  buckets.
- **Two model variants**: "conservative" (full 5y history, returns
  winsorized at 5th/95th percentile) and "recent" (trailing 252 trading
  days, unfiltered) — both required by the brief.
- **Simulation method**: regime bootstrap (draw next state from the
  transition matrix, then resample an actual historical return from that
  state) rather than a parametric return distribution per state. Chosen
  because it can't produce a return magnitude that never actually happened
  historically, which felt like the more defensible default for a first
  version.
- **Entry/exit windows**: 15 trading days before the ex-div date to search
  for an entry trough; 40 trading days after to search for recovery. Picked
  as round numbers consistent with the brief's own `t+20`-style example,
  with margin either side.
- **Ranking score**: `trailing_yield% / recovery_days`, using the
  conservative model's recovery time. Simple and interpretable; a ticker
  that never recovered within 40 days is penalized (treated as 120 days)
  rather than silently dropped from the ranking.

## What happened / edge cases

- Initial run completed in ~11s CPU for 4 tickers × 2 models × 100k paths —
  fast enough that there was no need to reduce simulation count.
- **Important finding, not a bug**: for AGNC and TTE, the "recovery" showed
  up as 1 trading day. This is real — both have a historical median
  `Q_ratio` < 1 (0.71 and 0.87 respectively), meaning their prices
  historically drop by *less* than the dividend paid, so the recovery
  threshold is already satisfied almost immediately by the actual
  ex-dividend price itself, before the simulation even has to do any work.
  Verified this against the raw price series (see `AI_Performance_Report.md`)
  rather than assuming it was a code error.
- **Model limitation surfaced by inspection**: plotted the conservative
  model's expected entry-window path against AGNC's actual prices
  (see `output/AGNC_paths.png`). Actual prices rallied from ~10.11 to 11.00
  over the 15 days before the ex-div date (the "pre-dividend buying ramp"
  the brief describes) while the model's expected path stayed almost flat.
  The Markov model has no explicit concept of an upcoming dividend date, so
  it can't anticipate calendar-driven demand — it only reacts to whatever
  drift already exists in the recent state-transition statistics. Documented
  in `AI_Performance_Report.md` as the main thing to fix next.
- `O` and `STAG` did not recover to the target price within the 40-day
  window under the conservative model (`>40`), consistent with their
  `Q_ratio` being ≥1 (1.40 and, oddly, −0.69 for STAG — STAG's ex-div price
  rose rather than dropped in the most recent event, likely because its
  dividend is small relative to daily noise).

## State for next session
- Code and docs are complete and working end-to-end as of this commit.
- Biggest open item: the model has no dividend-awareness — see
  "Known architectural limitation" in `docs/system_architecture.md`. A
  natural next step would be adding a calendar-distance feature to the
  state definition (days-to-next-ex-div) so the transition matrix can
  actually learn the pre-dividend ramp pattern, rather than treating every
  day identically.
- No broker integration exists and none should be added without an
  explicit, separate request — see the hard constraints in `CLAUDE.md`.
