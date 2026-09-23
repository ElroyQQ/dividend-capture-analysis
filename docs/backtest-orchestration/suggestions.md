# Backtest orchestration — suggestions (category-theory derived)

> Deduced from ARCHITECTURE.md by FRAMEWORK rules. Not applied — a backlog.

| # | Rule (§) | Smell found | Proposed change | Payoff |
| --- | --- | --- | --- | --- |
| 1 | §4.5 Law 4 (advisory) | `analyze_ticker()` is graphify's #1 god node (10 edges) — it directly calls into both `data-ingestion` and `markov-engine` plus most of this file's own helpers | not urgent; if a fourth major responsibility is ever added to it, consider splitting the "fetch usable events" concern from the "run the Monte Carlo search per event" concern | keeps the orchestrator's single function from becoming the de facto integration point for every future feature |

## Detail

### 1. `analyze_ticker` as the system's central hub
Confirmed via `graphify-out/GRAPH_REPORT.md`'s "God Nodes" list: `analyze_ticker()`
(10 edges) and `fit_model()` (10 edges) are the two most-connected nodes in
the whole codebase. For a 3-module, ~50-second-runtime research prototype
this is proportionate — not a smell to fix now — but it's the first place to
look if this codebase ever grows a fourth pipeline stage.
