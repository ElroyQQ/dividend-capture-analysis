# Data ingestion — suggestions (category-theory derived)

> Deduced from ARCHITECTURE.md by FRAMEWORK rules. Not applied — a backlog.

| # | Rule (§) | Smell found | Proposed change | Payoff |
| --- | --- | --- | --- | --- |
| 1 | §5 One source of truth (advisory) | `median_Q_ratio` uses the full 5y window while backtest stats (`hit_rate`, `mean`/`std` return) use the capped 50-event window for the same ticker | surface which window backs which number directly in `ranking.csv`/`report.md`, not only in `system_architecture.md`'s prose | a reader comparing two stats for one ticker can currently misread them as computed over the same sample; this is a documentation/output-shape fix, not a computation change |

## Detail

### 1. Mixed-window stats, undisclosed at the point of use
This is an already-documented known limitation (`system_architecture.md`,
"Known limitations"), not a new finding. It's recorded here specifically
because it fits a named FRAMEWORK smell (§5: two numbers presented side by
side that implicitly assume the same authoritative source/window, when they
don't) — worth a small output-shape fix (an extra column or footnote) rather
than a deeper change to either window's computation, both of which are
independently well-justified in `system_architecture.md`.
