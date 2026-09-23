# Markov engine — implementation map

> The functor ARCHITECTURE.md → code. Each object/morphism → the file:symbol
> that realises it. Keep in sync WITH the code (§6.3).

## Objects (Dat) → code
| Object | Form / shape | Realised at | State |
| --- | --- | --- | --- |
| `MarkovModel` | `@dataclass` (EGARCH params + per-regime residual pools) | `src/markov.py:MarkovModel` (line 50) | built |
| `DegenerateFitError` | `class(RuntimeError)` | `src/markov.py:DegenerateFitError` (line 72) | built |

## Morphisms (Trn / relations) → code
| Morphism | Signature | Realising code | State |
| --- | --- | --- | --- |
| `_log_returns` | `Series → ndarray` | `src/markov.py:_log_returns` (line 64) | built |
| `_classify` | `(values, edges) → ndarray` | `src/markov.py:_classify` (line 68) | built |
| `_is_degenerate` | `(alpha, gamma, beta) → bool` | `src/markov.py:_is_degenerate` (line 77) | built |
| `fit_model` | `(prices, label, dist) → MarkovModel` | `src/markov.py:fit_model` (line 87) | built |
| `current_state` | `MarkovModel → int` | `src/markov.py:current_state` (line 180) | built |
| `simulate` | `(model, start_price, start_state, n_days) → ndarray` | `src/markov.py:simulate` (line 184) | built |
| `apply_calendar_drift` | `(paths, per_step_drift) → ndarray` | `src/markov.py:apply_calendar_drift` (line 245) | built |

## Composition rules → where enforced
| Rule (ARCHITECTURE §6) | Enforced at | Tested at |
| --- | --- | --- |
| `mean="Zero"` | `src/markov.py:fit_model` (EGARCH spec) | no automated test suite — verified by inspection |
| Degenerate-fit rejection (`\|alpha\|>20` etc.) | `src/markov.py:_is_degenerate` | no automated test suite; empirically verified against the session-6 `ν≈2` case (`AI_Performance_Report.md`) |
| Residuals clipped `±10` | `src/markov.py:fit_model` (bootstrap pool construction) | no automated test suite |
| Log-variance clipped `±4` | `src/markov.py:simulate` | no automated test suite |

## Notes / divergences
None found at scaffold time (2026-09-23). No automated test suite exists in
this repo — every composition rule here is verified by the documented
session-6 debugging trail (`AI_Performance_Report.md`), not by a test file.
