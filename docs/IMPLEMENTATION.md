# System implementation map

> Whole-system functor architecture-map.md → code, deduced from the component
> IMPLEMENTATION.md files. System-level rows only.

## Components → code root
| Component | Code root | Model | Code map |
| --- | --- | --- | --- |
| data-ingestion | `src/data_io.py` | [data-ingestion/ARCHITECTURE.md](data-ingestion/ARCHITECTURE.md) | [data-ingestion/IMPLEMENTATION.md](data-ingestion/IMPLEMENTATION.md) |
| markov-engine | `src/markov.py` | [markov-engine/ARCHITECTURE.md](markov-engine/ARCHITECTURE.md) | [markov-engine/IMPLEMENTATION.md](markov-engine/IMPLEMENTATION.md) |
| backtest-orchestration | `src/analysis_engine.py` | [backtest-orchestration/ARCHITECTURE.md](backtest-orchestration/ARCHITECTURE.md) | [backtest-orchestration/IMPLEMENTATION.md](backtest-orchestration/IMPLEMENTATION.md) |

## Shared objects (one Dat, DataLocs in ≥2 components)
| Object | Authoritative at | Also read by | Realised at |
| --- | --- | --- | --- |
| OHLCV + dividend history | data-ingestion | markov-engine, backtest-orchestration | `src/data_io.py:fetch_history` |
| `MarkovModel` (fitted) | markov-engine | backtest-orchestration | `src/markov.py:MarkovModel` |
| `DegenerateFitError` | markov-engine (raised) | backtest-orchestration (caught, per-event skip) | `src/markov.py:DegenerateFitError` (line 72) |

## Inter-component transmissions / ports (Trm)
| Port | carries | c_from → c_to | Realising code |
| --- | --- | --- | --- |
| `fetch_history` | OHLCV + dividend history | yahoo-finance → data-ingestion | `src/data_io.py:fetch_history` (line 12) |
| `write_interface` | ranked results JSON snapshot | backtest-orchestration → browser | `src/analysis_engine.py:write_interface` (line 519) |

## System entry points
| Entry | Trn triggered | Code |
| --- | --- | --- |
| `python src/analysis_engine.py` | `main()` → per-ticker `analyze_ticker` loop → `rank` → `classify_suitability` → `write_report`/`write_interface`/`plot_comparison_chart` | `src/analysis_engine.py:main` (line 530) |
| Opening `interface/index.html` | none — static read of the last `write_interface` snapshot, self-reloads every 60s | `src/interface_template.html` → `interface/index.html` |

## Divergences (system-level)
None found at scaffold time (2026-09-23). `analyze_ticker()` and
`fit_model()` are graphify's top two "god nodes" (10 edges each) — both are
legitimate cross-component call sites (orchestration calling into ingestion
and the model engine), not duplicated logic; see `docs/suggestions.md` #1 for
the one thing worth watching if either grows further.
