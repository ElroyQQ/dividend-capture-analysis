# Dividend Capture — Analysis Report

GARCH-filtered regime-bootstrap Monte Carlo (100,000 paths for the headline event, 8,000 paths × up to 50 historical events per ticker for the backtest aggregate), with antithetic variance reduction and an ex-dividend calendar-drift adjustment. See docs/system_architecture.md for the full methodology.

## Top 5 quick picks

| Ticker | Best for | Why |
|---|---|---|
| AGNC | Aggressive pick | Highest average payoff of the group (+2.3% per cycle), but outcomes swing wider (±6.4%) between events. |
| JPM | Conservative pick | Recovered in 100% of its last 14 dividend cycles, with a comparatively narrow spread of outcomes (±4.4%). |
| TTE | Aggressive pick | Highest average payoff of the group (+3.6% per cycle), but outcomes swing wider (±6.6%) between events. |
| CVX | Aggressive pick | Highest average payoff of the group (+4.7% per cycle), but outcomes swing wider (±5.6%) between events. |
| PG | Conservative pick | Recovered in 93% of its last 14 dividend cycles, with a comparatively narrow spread of outcomes (±3.7%). |

## Full ranking (all 17 analyzed, highest risk-reward score first — top 5 marked ★)

| ticker   | category                                                      |   trailing_yield_pct |   median_Q_ratio |   n_backtest_events |   hit_rate_pct | hit_rate_95ci   |   mean_return_per_cycle_pct |   std_return_per_cycle_pct |   median_recovery_days |   risk_reward_score |
|:---------|:--------------------------------------------------------------|---------------------:|-----------------:|--------------------:|---------------:|:----------------|----------------------------:|---------------------------:|-----------------------:|--------------------:|
| ★ AGNC   | hold — monthly-paying mortgage REIT                           |                14.44 |             0.71 |                  39 |           89.7 | 76–96%          |                       2.309 |                      6.403 |                    1   |              0.222  |
| ★ JPM    | hold — financials, quarterly dividend                         |                 1.7  |             0.92 |                  14 |          100   | 78–100%         |                       4.339 |                      4.355 |                    1   |              0.2128 |
| ★ TTE    | trade_exit — energy major, quarterly dividend                 |                 3.29 |             0.87 |                  13 |          100   | 77–100%         |                       3.643 |                      6.57  |                    1   |              0.1685 |
| ★ CVX    | trade_exit — energy major, quarterly dividend                 |                 3.46 |             0.91 |                  12 |           91.7 | 65–99%          |                       4.662 |                      5.596 |                    1   |              0.1636 |
| ★ PG     | hold — consumer staples, quarterly dividend                   |                 2.94 |             0.67 |                  14 |           92.9 | 69–99%          |                       2.437 |                      3.726 |                    1   |              0.1518 |
| MMM      | hold — industrials, quarterly dividend                        |                 1.86 |             1.26 |                  10 |           90   | 60–98%          |                       3.696 |                      4.574 |                   10   |              0.1096 |
| STAG     | hold — monthly-paying industrial REIT                         |                 3.39 |            -0.69 |                  34 |           85.3 | 70–94%          |                       1.961 |                      5.402 |                    1   |              0.1076 |
| SPG      | hold — retail REIT (Simon Property Group), quarterly dividend |                 4.34 |             1.03 |                  13 |           76.9 | 50–92%          |                       3.759 |                      6.267 |                    3   |              0.0808 |
| XOM      | trade_exit — energy major, quarterly dividend                 |                 2.6  |             0.71 |                  12 |           66.7 | 39–86%          |                       4.866 |                      4.738 |                    2.5 |              0.0806 |
| JNJ      | hold — healthcare, quarterly dividend                         |                 1.96 |             0.98 |                  12 |           75   | 47–91%          |                       3.118 |                      4.499 |                    1   |              0.0764 |
| DUK      | hold — utility, quarterly dividend                            |                 3.67 |             0.81 |                  13 |           84.6 | 58–96%          |                       1.691 |                      4.545 |                    1   |              0.0661 |
| O        | hold — monthly-paying REIT (Realty Income)                    |                 5.73 |             1.4  |                  42 |           76.2 | 61–87%          |                       1.468 |                      4.161 |                    1   |              0.0587 |
| SO       | hold — utility, quarterly dividend                            |                 3.51 |             0.54 |                  14 |           85.7 | 60–96%          |                       1.545 |                      4.746 |                    1   |              0.0454 |
| MAIN     | hold — monthly-paying BDC (Main Street Capital)               |                 7.68 |             0.91 |                  49 |           83.7 | 71–91%          |                       1.514 |                      3.872 |                    1   |              0.045  |
| KO       | hold — consumer staples, quarterly dividend                   |                 2.41 |             0.9  |                  14 |           92.9 | 69–99%          |                       1.161 |                      2.632 |                    1   |              0.0395 |
| VZ       | hold — telecom, quarterly dividend                            |                 5.86 |             1.25 |                  13 |           69.2 | 42–87%          |                       0.376 |                      7.382 |                    1   |              0.0054 |
| T        | hold — telecom, quarterly dividend                            |                 4.37 |             1.1  |                  12 |           75   | 47–91%          |                       0.032 |                      5.076 |                    1   |              0.0006 |

## Notes

- `n_backtest_events` / `hit_rate_pct`: how many historical ex-dividend events (capped, most recent first) were actually run through the entry/exit search, and what fraction of those recovered to breakeven within the window — the ranking's statistical sample size, not a single anecdote.
- `hit_rate_95ci`: 95% Wilson confidence interval on the hit rate — how much the true hit rate could plausibly differ from the point estimate given the sample size. A narrow interval means the hit rate is well-supported; a wide one (common at small n) means don't over-read the headline percentage.
- `mean_return_per_cycle_pct` / `std_return_per_cycle_pct`: average and spread of net return (price change + dividend, relative to entry price) across those backtested events under the conservative model.
- `median_Q_ratio`: historical ex-div price drop ÷ dividend paid, across all usable events (not just the backtested subset). <1.0 = price tends to drop by less than the dividend; >1.0 = drops by more.
- `risk_reward_score = mean_return_per_cycle_pct × (Wilson CI lower bound on hit rate) ÷ mean_hold_days` — return per day held, discounted by how reliably the backtest recovered *and* by how much sample size backs that reliability. Uses the CI lower bound rather than the raw hit rate so a small-sample "100%" doesn't outscore a larger-sample, slightly-lower hit rate that's actually better supported.
- See AI_Performance_Report.md for where this model is and isn't reliable.
