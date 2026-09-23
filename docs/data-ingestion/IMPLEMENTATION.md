# Data ingestion — implementation map

> The functor ARCHITECTURE.md → code. Each object/morphism → the file:symbol
> that realises it. Keep in sync WITH the code (§6.3).

## Objects (Dat) → code
| Object | Form / shape | Realised at | State |
| --- | --- | --- | --- |
| OHLCV + dividend history | `pd.DataFrame`, tz-naive date index | `src/data_io.py:fetch_history` (line 12) | built |
| Ex-dividend events | `pd.DataFrame` (`cum_close`, `ex_close`, drop, `Q_ratio`) | `src/data_io.py:ex_dividend_events` (line 27) | built |

## Morphisms (Trn / relations) → code
| Morphism | Signature | Realising code | State |
| --- | --- | --- | --- |
| `fetch_history` | `(ticker, period) → DataFrame` | `src/data_io.py:fetch_history` (line 12) | built |
| `ex_dividend_events` | `DataFrame → DataFrame` | `src/data_io.py:ex_dividend_events` (line 27) | built |
| `trailing_dividend_yield` | `DataFrame → float` | `src/data_io.py:trailing_dividend_yield` (line 41) | built |
| `seasonal_return_pattern` | `(history, event_indices, ...) → drift curve` | `src/data_io.py:seasonal_return_pattern` (line 48) | built |

## Composition rules → where enforced
| Rule (ARCHITECTURE §6) | Enforced at | Tested at |
| --- | --- | --- |
| No fabricated price/dividend data | `src/data_io.py:fetch_history` (raises on `yfinance` failure) | no automated test suite in this repo — enforced by code review discipline (`CLAUDE.md` hard constraint) |
| Seasonal window capped to `event_gap // 2 - 1`, floor 3 | `src/data_io.py:seasonal_return_pattern` | no automated test suite |

## Notes / divergences
None found at scaffold time (2026-09-23).
