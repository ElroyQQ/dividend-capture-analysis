"""GARCH-filtered regime-bootstrap Markov chain + Monte Carlo engine.

Method (upgraded from a plain quantile-bucketed return bootstrap — see
docs/system_architecture.md and AI_Performance_Report.md for why):

1. Fit a GARCH(1,1) model to daily log returns (via the `arch` package) to
   capture volatility clustering — the "financial markets exhibit
   non-stationary distributions... must often be augmented" limitation the
   project brief names explicitly for plain first-order Markov chains.
2. Classify the model's *standardized residuals* (return / conditional
   volatility) into N_STATES quantile buckets, instead of classifying raw
   returns. Standardized residuals are much closer to stationary than raw
   returns, so the regime transition matrix built on them is more
   meaningful than one built on raw up/down-day buckets.
3. Simulate forward as a "filtered historical simulation": at each step,
   draw the next regime state from the transition matrix, bootstrap an
   actual historical standardized residual from that state's pool, scale it
   by the *current* GARCH-forecasted volatility (not a flat historical
   average), and roll the GARCH variance recursion forward per path.
4. Use antithetic variates for variance reduction: simulate half the paths,
   then mirror each one by negating its drawn shocks (the GARCH variance
   recursion depends on shock^2, so the mirrored path's volatility
   trajectory is identical — only the sign of each day's return flips).
   This roughly halves Monte Carlo noise for the same simulation budget.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from arch import arch_model

N_STATES = 5
STATE_LABELS = ["big_down", "down", "flat", "up", "big_up"]
RETURN_SCALE = 100.0  # arch fits more reliably on returns scaled to ~O(1) percent units


@dataclass
class MarkovModel:
    edges: np.ndarray           # quantile bin edges over standardized residuals
    transition: np.ndarray      # (N_STATES, N_STATES) row-stochastic matrix
    state_resid: list           # per-state array of historical standardized residuals to bootstrap
    omega: float
    alpha: float
    beta: float
    last_std_resid: float       # most recent standardized residual (for current_state)
    next_variance: float        # GARCH-forecasted variance for the day after the fit window
    label: str


def _log_returns(prices: pd.Series) -> np.ndarray:
    return np.diff(np.log(prices.values)) * RETURN_SCALE


def _classify(values: np.ndarray, edges: np.ndarray) -> np.ndarray:
    return np.clip(np.digitize(values, edges[1:-1]), 0, N_STATES - 1)


def fit_model(prices: pd.Series, label: str, dist: str = "normal",
              lookback_days: int | None = None) -> MarkovModel:
    """Fit a GARCH(1,1)-filtered regime model on `prices`.

    dist: "t" (Student's t) down-weights the influence of extreme spikes on
        the fitted GARCH parameters — used for the "conservative" variant in
        place of the old ad hoc return-winsorizing.
    lookback_days: if set, fit only on the most recent N trading days — the
        "recent movement" variant.
    """
    returns = _log_returns(prices)
    if lookback_days is not None:
        returns = returns[-lookback_days:]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        am = arch_model(returns, mean="Zero", vol="Garch", p=1, q=1, dist=dist, rescale=False)
        res = am.fit(disp="off")

    std_resid = np.asarray(res.std_resid)
    std_resid = std_resid[~np.isnan(std_resid)]
    edges = np.quantile(std_resid, np.linspace(0, 1, N_STATES + 1))
    states = _classify(std_resid, edges)

    transition = np.ones((N_STATES, N_STATES))  # Laplace smoothing avoids zero-prob dead ends
    for prev, nxt in zip(states[:-1], states[1:]):
        transition[prev, nxt] += 1
    transition = transition / transition.sum(axis=1, keepdims=True)

    state_resid = [std_resid[states == s] if np.any(states == s) else std_resid for s in range(N_STATES)]

    next_var = res.forecast(horizon=1, reindex=False).variance.iloc[-1, 0]

    return MarkovModel(
        edges=edges, transition=transition, state_resid=state_resid,
        omega=float(res.params["omega"]), alpha=float(res.params["alpha[1]"]),
        beta=float(res.params["beta[1]"]), last_std_resid=float(std_resid[-1]),
        next_variance=float(next_var), label=label,
    )


def current_state(model: MarkovModel) -> int:
    return int(_classify(np.array([model.last_std_resid]), model.edges)[0])


def simulate(model: MarkovModel, start_price: float, start_state: int, n_days: int,
             n_sims: int = 100_000, seed: int = 7, antithetic: bool = True) -> np.ndarray:
    """Filtered-historical-simulation Monte Carlo with antithetic variance
    reduction. Returns an (n_sims, n_days+1) array of simulated price paths,
    column 0 = start_price."""
    rng = np.random.default_rng(seed)
    half = n_sims // 2 if antithetic else n_sims
    states = np.full(half, start_state, dtype=int)
    variance = np.full(half, model.next_variance)
    log_returns = np.empty((half, n_days))       # base-path log returns per day (RETURN_SCALE units)

    for day in range(n_days):
        next_states = np.empty(half, dtype=int)
        for s in range(N_STATES):
            mask = states == s
            count = mask.sum()
            if count == 0:
                continue
            next_states[mask] = rng.choice(N_STATES, size=count, p=model.transition[s])
        states = next_states

        z = np.empty(half)
        for s in range(N_STATES):
            mask = states == s
            count = mask.sum()
            if count == 0:
                continue
            z[mask] = rng.choice(model.state_resid[s], size=count, replace=True)

        eps = z * np.sqrt(variance)
        log_returns[:, day] = eps
        variance = model.omega + model.alpha * eps**2 + model.beta * variance

    if antithetic:
        all_log_returns = np.vstack([log_returns, -log_returns])
    else:
        all_log_returns = log_returns

    cum = np.cumsum(all_log_returns, axis=1) / RETURN_SCALE
    paths = np.empty((all_log_returns.shape[0], n_days + 1))
    paths[:, 0] = start_price
    paths[:, 1:] = start_price * np.exp(cum)
    return paths


def apply_calendar_drift(paths: np.ndarray, per_step_drift: np.ndarray | None) -> np.ndarray:
    """Multiply a deterministic seasonal (calendar-day-relative-to-ex-div)
    drift into simulated paths. `per_step_drift[i]` is the expected
    incremental log return from day i to day i+1; None/zero leaves paths
    unchanged. See data_io.seasonal_return_pattern for where this comes from."""
    if per_step_drift is None:
        return paths
    cum_drift = np.concatenate([[0.0], np.cumsum(per_step_drift)])
    return paths * np.exp(cum_drift)[None, :]
