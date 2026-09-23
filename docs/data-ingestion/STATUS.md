# Data ingestion — status

> Reconciles ARCHITECTURE.md (intent) vs IMPLEMENTATION.md (code).

## Headline
Built and complete. The one real external boundary in this codebase, and the
best-guarded — `fetch_history` raises rather than falls back to a guess.

## Completeness
| Object / morphism | State | Notes |
| --- | --- | --- |
| `fetch_history` | ✅ built | |
| `ex_dividend_events` | ✅ built | |
| `trailing_dividend_yield` | ✅ built | |
| `seasonal_return_pattern` | ✅ built | window-capping bug fixed in session 3 — see `system_architecture.md` §3 |

## Needs work
1. `median_Q_ratio` is computed over the full 5-year window regardless of the
   backtest's 50-event cap — a documented, deliberate known limitation, not a
   bug. See `docs/suggestions.md` #2 for the one improvement worth
   considering (surface the window in output, don't change the computation).

## Coherence
No §4.5 law FAILing.

## Where to dig
- Model: `ARCHITECTURE.md` · Code map: `IMPLEMENTATION.md`
- In flight: `openspec/changes/` (none as of scaffold) · Reviews: `reviews/` · Notes: `general/`
