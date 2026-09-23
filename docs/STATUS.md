# System status

> Roll-up of every <component>/STATUS.md. Detail lives in the linked file.

| Component | State | Headline gap | In flight | Detail |
| --- | --- | --- | --- | --- |
| data-ingestion | ✅ built | none | — | [data-ingestion/STATUS.md](data-ingestion/STATUS.md) |
| markov-engine | ✅ built | numerical-safety guards documented but not covered by automated tests | — | [markov-engine/STATUS.md](markov-engine/STATUS.md) |
| backtest-orchestration | ✅ built | interface auto-refresh could visually overclaim liveness if the explanatory guide panel is ever removed | — | [backtest-orchestration/STATUS.md](backtest-orchestration/STATUS.md) |

## Cross-cutting
No §4.5 law currently FAILing. `analyze_ticker()`/`fit_model()` dependency
concentration is advisory-only — see `docs/suggestions.md` #1.
