# Backtest orchestration — implementation map

> The functor ARCHITECTURE.md → code. Each object/morphism → the file:symbol
> that realises it. Keep in sync WITH the code (§6.3).

## Objects (Dat) → code
| Object | Form / shape | Realised at | State |
| --- | --- | --- | --- |
| Per-ticker result | `dict` (hit_rate, wilson interval, mean/std return, median_recovery_days, n_events) | `src/analysis_engine.py:analyze_ticker` (line 191) | built |
| Ranked DataFrame | `pd.DataFrame`, ordered by `risk_reward_score` | `src/analysis_engine.py:rank` (line 368) | built |
| Interface records | `list[dict]`, JSON-shaped | `src/analysis_engine.py:build_interface_records` (line 475) | built |

## Morphisms (Trn / relations) → code
| Morphism | Signature | Realising code | State |
| --- | --- | --- | --- |
| `wilson_interval` | `(successes,n,z) → (lo,hi)` | `src/analysis_engine.py:wilson_interval` (line 94) | built |
| `_usable_event_indices` | `(history,events) → list[int]` | `src/analysis_engine.py:_usable_event_indices` (line 110) | built |
| `_entry_exit_search` | `(history,ex_idx,dividend,cum_close,...) → dict` | `src/analysis_engine.py:_entry_exit_search` (line 126) | built |
| `analyze_ticker` | `ticker → dict` | `src/analysis_engine.py:analyze_ticker` (line 191) | built |
| `plot_paths` | `(ticker,history,ex_idx,result) → None` | `src/analysis_engine.py:plot_paths` (line 299) | built |
| `plot_comparison_chart` | `list[dict] → None` | `src/analysis_engine.py:plot_comparison_chart` (line 339) | built |
| `rank` | `list[dict] → DataFrame` | `src/analysis_engine.py:rank` (line 368) | built |
| `classify_suitability` | `DataFrame → dict[str,dict]` | `src/analysis_engine.py:classify_suitability` (line 398) | built |
| `write_report` | `(df,suitability) → None` | `src/analysis_engine.py:write_report` (line 434) | built |
| `build_interface_records` | `(results,df,...) → list[dict]` | `src/analysis_engine.py:build_interface_records` (line 475) | built |
| `write_interface` | `list[dict] → None` | `src/analysis_engine.py:write_interface` (line 519) | built |
| `main` | `() → None` | `src/analysis_engine.py:main` (line 530) | built |

## Composition rules → where enforced
| Rule (ARCHITECTURE §6) | Enforced at | Tested at |
| --- | --- | --- |
| `risk_reward_score` formula | `src/analysis_engine.py:rank` | no automated test suite |
| `n_events ≤ MAX_BACKTEST_EVENTS`, degenerate events skipped | `src/analysis_engine.py:analyze_ticker` | no automated test suite |
| `isTopN = rank ≤ TOP_N`, recomputed fresh | `src/analysis_engine.py:build_interface_records` | no automated test suite; manually verified session 8 |
| Suitability independent of model toggle | `src/analysis_engine.py:classify_suitability` | no automated test suite |
| One `classify_suitability` call feeds report + interface | `src/analysis_engine.py:write_report`, `build_interface_records` | no automated test suite |

## Notes / divergences
None found at scaffold time (2026-09-23). No automated test suite exists in
this repo.
