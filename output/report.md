# Dividend Capture — Analysis Report

GARCH-filtered regime-bootstrap Monte Carlo (100,000 paths for the headline event, 8,000 paths × up to 50 historical events per ticker for the backtest aggregate), with antithetic variance reduction and an ex-dividend calendar-drift adjustment. See docs/system_architecture.md for the full methodology.

## Quick picks

| Ticker | Best for | Why |
|---|---|---|
| AGNC | Aggressive pick | Highest average payoff of the group (+2.3% per cycle), but outcomes swing wider (±6.4%) between events. |
| TTE | Aggressive pick | Highest average payoff of the group (+3.6% per cycle), but outcomes swing wider (±6.6%) between events. |
| STAG | Balanced | Middling on both counts — 85% hit rate, +2.0% average return. |
| O | Balanced | Middling on both counts — 76% hit rate, +1.5% average return. |

## Ranking (highest risk-reward score first)

| ticker   | category                                      |   trailing_yield_pct |   median_Q_ratio |   n_backtest_events |   hit_rate_pct | hit_rate_95ci   |   mean_return_per_cycle_pct |   std_return_per_cycle_pct |   median_recovery_days |   risk_reward_score |
|:---------|:----------------------------------------------|---------------------:|-----------------:|--------------------:|---------------:|:----------------|----------------------------:|---------------------------:|-----------------------:|--------------------:|
| AGNC     | hold — monthly-paying mortgage REIT           |                14.44 |             0.71 |                  39 |           89.7 | 76–96%          |                       2.309 |                      6.403 |                      1 |              0.222  |
| TTE      | trade_exit — energy major, quarterly dividend |                 3.29 |             0.87 |                  13 |          100   | 77–100%         |                       3.643 |                      6.57  |                      1 |              0.1685 |
| STAG     | hold — monthly-paying industrial REIT         |                 3.39 |            -0.69 |                  34 |           85.3 | 70–94%          |                       1.961 |                      5.402 |                      1 |              0.1076 |
| O        | hold — monthly-paying REIT (Realty Income)    |                 5.73 |             1.4  |                  42 |           76.2 | 61–87%          |                       1.468 |                      4.161 |                      1 |              0.0587 |

## Notes

- `n_backtest_events` / `hit_rate_pct`: how many historical ex-dividend events (capped, most recent first) were actually run through the entry/exit search, and what fraction of those recovered to breakeven within the window — the ranking's statistical sample size, not a single anecdote.
- `hit_rate_95ci`: 95% Wilson confidence interval on the hit rate — how much the true hit rate could plausibly differ from the point estimate given the sample size. A narrow interval means the hit rate is well-supported; a wide one (common at small n) means don't over-read the headline percentage.
- `mean_return_per_cycle_pct` / `std_return_per_cycle_pct`: average and spread of net return (price change + dividend, relative to entry price) across those backtested events under the conservative model.
- `median_Q_ratio`: historical ex-div price drop ÷ dividend paid, across all usable events (not just the backtested subset). <1.0 = price tends to drop by less than the dividend; >1.0 = drops by more.
- `risk_reward_score = mean_return_per_cycle_pct × (Wilson CI lower bound on hit rate) ÷ mean_hold_days` — return per day held, discounted by how reliably the backtest recovered *and* by how much sample size backs that reliability. Uses the CI lower bound rather than the raw hit rate so a small-sample "100%" doesn't outscore a larger-sample, slightly-lower hit rate that's actually better supported.
- See AI_Performance_Report.md for where this model is and isn't reliable.
