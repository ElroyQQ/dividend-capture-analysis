# Whole-system categorical map (Dat/Trn/Loc/Trm)

> Top-level architecture doc (§4). Names the four atoms, lists components (each
> linking to its ARCHITECTURE.md), reifies placement where it is a relation, and
> runs the §4.5 coherence checklist against the code. Detail lives in the linked
> component docs. **Deep numerical/statistical rationale lives in the existing
> prior-art doc, [system_architecture.md](system_architecture.md) — this file
> does not duplicate it, only formalizes its pipeline into the four atoms.**
> Source of record: `src/data_io.py`, `src/markov.py`, `src/analysis_engine.py`.

## 1. Why
Unlike this workspace's two static sites, this project genuinely straddles the
wire (§7.2): it fetches real market data from an external service, then hands
a generated artifact to a second, physically separate process (a browser).
Modeling `Loc`/`Trm` explicitly here is load-bearing, not decorative — it's
the difference between "the interface is live" (false) and "the interface is
a snapshot" (true, and already a documented gotcha in `CLAUDE.md`).

## 2. The four atoms (at a glance)
**Dat** — OHLCV+dividend history (`pd.DataFrame`), ex-dividend events, a fitted
`MarkovModel` (EGARCH params + per-regime residual pools), simulated price
paths (`np.ndarray`), per-ticker analysis results (`dict`), the ranked
DataFrame, interface JSON records, and the generated output files
(`report.md`, `ranking.csv`, `<ticker>_paths.png`, `interface/index.html`).

**Trn** — see each component's morphism table; the three files map directly
to the three components below.

**Loc** — three real, distinct locations:
- `local-python` — the one-shot process running `analysis_engine.py`
  (orchestrates `data_io` + `markov`)
- `yahoo-finance` — external market-data provider, reached via `yfinance`
- `browser` — wherever a human opens `interface/index.html`

**Trm** — two real cross-`Loc` transmissions:
- `fetch_history`: `yahoo-finance → local-python` (HTTP, via `yfinance`) —
  carries OHLCV + dividend history. **This is the only source of price data**
  — `CLAUDE.md`'s "no fabricated financial data" constraint is this `Trm`'s
  well-typing requirement.
- `write_interface`: `local-python → browser` (file-mediated, not a live
  push) — carries the JSON snapshot of ranked results. **Not live**: the
  browser never re-transmits or re-fetches; a page left open just re-reads
  the same static file every 60s (`location.reload()`), so it only shows new
  numbers once `local-python` has run again and overwritten the file.

## 3. Components
| Component | Owned `Trn` | Built/active when | Doc |
| --- | --- | --- | --- |
| `data-ingestion` | `fetch_history`, `ex_dividend_events`, `trailing_dividend_yield`, `seasonal_return_pattern` | always | [data-ingestion/ARCHITECTURE.md](data-ingestion/ARCHITECTURE.md) |
| `markov-engine` | `fit_model`, `_is_degenerate`, `simulate`, `apply_calendar_drift`, `_classify`, `current_state` | always | [markov-engine/ARCHITECTURE.md](markov-engine/ARCHITECTURE.md) |
| `backtest-orchestration` | `analyze_ticker`, `_entry_exit_search`, `_usable_event_indices`, `wilson_interval`, `rank`, `classify_suitability`, `build_interface_records`, `write_interface`, `write_report`, `plot_paths`, `plot_comparison_chart`, `main` | always | [backtest-orchestration/ARCHITECTURE.md](backtest-orchestration/ARCHITECTURE.md) |

Decomposition matches the pipeline diagram already in `CLAUDE.md` and
`system_architecture.md` (`data_io.py → markov.py → analysis_engine.py`) and
graphify's own community detection (`graphify-out/GRAPH_REPORT.md`): its 10
fine-grained communities cluster cleanly under these same three files
(Community 0 ≈ `data_io.py`; Communities 3–6 ≈ `markov.py`'s
`analyze`/`fit`/`simulate` split; Communities 1/2/7 ≈ `analysis_engine.py`'s
orchestration). No finer split was warranted — see §3 Consolidation below.

## 4. Placement (only where runsAt is a relation, §4.2)
| `Trn`/`Dat` | placements | why it matters |
| --- | --- | --- |
| OHLCV history | fetched at `local-python`, never cached beyond a run | re-running always re-fetches; no stale-cache drift is possible by construction |
| Interface JSON | authored at `local-python`, read at `browser` | the file is the *only* channel between the two — see Trm above |

## 5. Coherence checklist (§4.5 / §8) against the implementation
- [x] 1. Placement honesty — the interface's auto-refresh indicator explains
      itself as a page reload, not a live feed (`CLAUDE.md`, session 7) — the
      UI doesn't overclaim what the `Trm` actually does.
- [x] 2. Transmission well-typing — `fetch_history`'s `Trm` is well-typed by
      construction: every price/dividend number traces to this one call, per
      `CLAUDE.md`'s explicit "no fabricated financial data" constraint.
- [x] 3. Placement totality — every `Trn` has a named `Loc`; none is implicit.
- [~] 4. Dependency mediation — `analyze_ticker()` (10 edges) and
      `fit_model()` (10 edges) are graphify's top "god nodes" — both are
      legitimate cross-component orchestration points (backtest-orchestration
      calling into markov-engine and data-ingestion), not accidental coupling,
      but worth knowing before adding a fourth caller to either. See
      [suggestions.md](suggestions.md) #1.
- [x] 5. Composition soundness — verified per-component in each
      IMPLEMENTATION.md (Wilson interval, `risk_reward_score`, degenerate-fit
      guards).
- [x] 6. runsAt is a relation — vacuous here; nothing runs at more than one
      `Loc` (each `Dat` has exactly one authoritative `Loc`).

## 6. Modeling smells swept (§3)
No parallel objects — `data-ingestion`, `markov-engine`, and
`backtest-orchestration` own disjoint `Dat`. The three-component split matches
both the file structure and graphify's community detection, so no further
consolidation or splitting was applied.
