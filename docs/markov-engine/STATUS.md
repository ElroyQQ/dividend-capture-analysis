# Markov engine — status

> Reconciles ARCHITECTURE.md (intent) vs IMPLEMENTATION.md (code).

## Headline
Built and complete, including the session-6 numerical hardening. No known
open defects — the degenerate-fit failure mode that prompted the hardening
is now guarded, not just documented.

## Completeness
| Object / morphism | State | Notes |
| --- | --- | --- |
| `fit_model` / `_is_degenerate` | ✅ built | GARCH→EGARCH upgrade (session 6) |
| `simulate` | ✅ built | antithetic variates, per-sign log-variance recursion |
| `apply_calendar_drift` | ✅ built | |

## Needs work
1. No automated tests cover the three numerical safety nets (residual clip,
   log-variance clip, degenerate-fit rejection) — currently verified only by
   the documented session-6 debugging trail. Not currently planned; flagged
   for visibility only, per `docs/STATUS.md`'s system-level headline gap.

## Coherence
No §4.5 law FAILing.

## Where to dig
- Model: `ARCHITECTURE.md` · Code map: `IMPLEMENTATION.md`
- In flight: `openspec/changes/` (none as of scaffold) · Reviews: `reviews/` · Notes: `general/`
