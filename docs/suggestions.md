# System suggestions (roll-up)

> Roll-up of every `<component>/suggestions.md`, highest payoff first. Detail
> lives in the linked file.

| # | Component | Rule (§) | Smell | Proposed change |
| --- | --- | --- | --- | --- |
| 1 | backtest-orchestration / markov-engine | §4.5 Law 4 (advisory) | `analyze_ticker()` and `fit_model()` are graphify's top two "god nodes" (10 edges each) | not urgent — both are legitimate orchestration points, not duplicated logic — but a fourth or fifth caller of either would be worth re-checking against §4.4 (ports & strategy) before adding |
| 2 | data-ingestion | §5 One source of truth (advisory) | `median_Q_ratio` is computed over the full 5-year window while the backtest's other stats (`hit_rate`, `mean`/`std` return) use the capped 50-event window — a fact already documented in `system_architecture.md`'s "Known limitations," not newly discovered here | make the window each stat was computed over visible in the output artifacts (`ranking.csv`/`report.md`) themselves, not only in prose docs, so a reader comparing two numbers for the same ticker can tell they're not from the same sample |

Detail: [backtest-orchestration/suggestions.md](backtest-orchestration/suggestions.md),
[data-ingestion/suggestions.md](data-ingestion/suggestions.md)

## System-wide reductions
None — the three components own disjoint `Dat`/`Trn` with no parallel-object
smell between them.
