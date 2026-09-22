# Dividend Capture — Analysis Report

GARCH-filtered regime-bootstrap Monte Carlo (100,000 paths for the headline event, 8,000 paths × up to 8 historical events per ticker for the backtest aggregate), with antithetic variance reduction and an ex-dividend calendar-drift adjustment. See docs/system_architecture.md for the full methodology.

## Quick picks

| Ticker | Best for | Why |
|---|---|---|
| AGNC | Conservative pick | Recovered in 88% of its last 8 dividend cycles, with a comparatively narrow spread of outcomes (±4.7%). |
| TTE | Aggressive pick | Highest average payoff of the group (+4.3% per cycle), but outcomes swing wider (±7.3%) between events. |
| O | Balanced | Middling on both counts — 75% hit rate, +2.2% average return. |
| STAG | Not recommended | Only a 50% historical hit rate — weak track record either way. |

## Ranking (highest risk-reward score first)

| ticker   | category                                      |   trailing_yield_pct |   median_Q_ratio |   n_backtest_events |   hit_rate_pct |   mean_return_per_cycle_pct |   std_return_per_cycle_pct |   median_recovery_days |   risk_reward_score |
|:---------|:----------------------------------------------|---------------------:|-----------------:|--------------------:|---------------:|----------------------------:|---------------------------:|-----------------------:|--------------------:|
| AGNC     | hold — monthly-paying mortgage REIT           |                14.44 |             0.71 |                   8 |           87.5 |                       4.136 |                      4.725 |                      1 |              0.5909 |
| TTE      | trade_exit — energy major, quarterly dividend |                 3.29 |             0.87 |                   8 |          100   |                       4.313 |                      7.298 |                      1 |              0.5309 |
| O        | hold — monthly-paying REIT (Realty Income)    |                 5.73 |             1.4  |                   8 |           75   |                       2.182 |                      3.777 |                      1 |              0.1149 |
| STAG     | hold — monthly-paying industrial REIT         |                 3.39 |            -0.69 |                   8 |           50   |                       1.245 |                      5.235 |                      1 |              0.0242 |

## Notes

- `n_backtest_events` / `hit_rate_pct`: how many historical ex-dividend events (capped, most recent first) were actually run through the entry/exit search, and what fraction of those recovered to breakeven within the window — the ranking's statistical sample size, not a single anecdote.
- `mean_return_per_cycle_pct` / `std_return_per_cycle_pct`: average and spread of net return (price change + dividend, relative to entry price) across those backtested events under the conservative model.
- `median_Q_ratio`: historical ex-div price drop ÷ dividend paid, across all usable events (not just the backtested subset). <1.0 = price tends to drop by less than the dividend; >1.0 = drops by more.
- `risk_reward_score = mean_return_per_cycle_pct × hit_rate ÷ mean_hold_days` — return per day held, discounted by how reliably the backtest actually recovered.
- See AI_Performance_Report.md for where this model is and isn't reliable.
