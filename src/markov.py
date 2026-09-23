"""EGARCH-filtered regime-bootstrap Markov chain + Monte Carlo engine.

Method (upgraded in session 6 from a plain symmetric GARCH(1,1) — see
docs/system_architecture.md and AI_Performance_Report.md for why):

1. Fit an EGARCH(1,1,1) model to daily log returns (via the `arch` package)
   to capture volatility clustering *and* the well-documented "leverage
   effect": a down move of a given size tends to raise future volatility
   more than an up move of the same size. Plain GARCH(1,1) can't represent
   that asymmetry at all; EGARCH does, via its `gamma` term, and is
   reported in the literature as producing the best equity volatility
   forecasts among the common GARCH-family models (see references in
   docs/system_architecture.md).
2. Classify the model's *standardized residuals* (return / conditional
   volatility) into N_STATES quantile buckets, instead of classifying raw
   returns — closer to stationary, so the regime transition matrix is more
   meaningful than one built on raw up/down-day buckets.
3. Simulate forward as a "filtered historical simulation": at each step,
   draw the next regime state from the transition matrix, bootstrap an
   actual historical standardized residual from that state's pool, scale it
   by the *current* EGARCH-forecasted volatility, and roll the EGARCH
   log-variance recursion forward per path.
4. Antithetic variates for variance reduction: half the paths are simulated
   normally; the other half reuses the *same drawn shock magnitudes*,
   negated. Unlike symmetric GARCH, EGARCH's variance recursion is not
   invariant to the sign of the shock (that asymmetry is the entire point
   of using it) — so, unlike the session-3 version of this file, the
   mirrored path's volatility trajectory is *not* reused wholesale; both
   signs run their own log-variance recursion from the same starting point,
   sharing only the drawn |z| magnitudes and state sequence. Still a valid,
   cheap variance-reduction pairing (the return draws are exactly
   antithetic; the volatility paths differ deliberately, by design).
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
    alpha: float                # magnitude (|z|) response
    gamma: float                # sign/asymmetry (leverage) response — the EGARCH addition over GARCH
    beta: float                 # persistence
    mean_abs_std_resid: float   # E|z|, estimated empirically from this fit's own residuals
    last_std_resid: float       # most recent standardized residual (for current_state)
    next_log_variance: float    # EGARCH-forecasted ln(variance) for the day after the fit window
    label: str


def _log_returns(prices: pd.Series) -> np.ndarray:
    return np.diff(np.log(prices.values)) * RETURN_SCALE


def _classify(values: np.ndarray, edges: np.ndarray) -> np.ndarray:
    return np.clip(np.digitize(values, edges[1:-1]), 0, N_STATES - 1)


class DegenerateFitError(RuntimeError):
    """Raised when an EGARCH fit converges (no optimizer error) but lands on
    parameters that are not physically sane — see fit_model()."""


def _is_degenerate(alpha: float, gamma: float, beta: float) -> bool:
    # Typical fitted EGARCH parameters for daily equity returns: alpha and
    # |gamma| well under 1, |beta| < 1 (log-variance stationarity). Found
    # empirically (backtesting many historical windows) a Student-t fit
    # whose degrees-of-freedom landed near the finite-variance boundary
    # (nu ~ 2) produced alpha=748.7, gamma=234.3, beta=1.0 — nothing near
    # those thresholds should ever occur from a well-posed fit.
    return abs(alpha) > 20.0 or abs(gamma) > 20.0 or abs(beta) >= 1.0


def fit_model(prices: pd.Series, label: str, dist: str = "normal",
              lookback_days: int | None = None) -> MarkovModel:
    """Fit an EGARCH(1,1,1)-filtered regime model on `prices`.

    dist: "t" (Student's t) down-weights the influence of extreme spikes on
        the fitted EGARCH parameters — used for the "conservative" variant.
    lookback_days: if set, fit only on the most recent N trading days — the
        "recent movement" variant.

    Raises DegenerateFitError if the optimizer converges to nonsensical
    parameters (rare, but real — see _is_degenerate) even after retrying
    once with a Normal-distribution fit (a Student-t fit can degenerate via
    a pathological degrees-of-freedom estimate; Normal has no such
    parameter). Callers backtesting many historical events should catch
    this and skip that one event rather than let corrupted numbers into an
    aggregate — see analysis_engine.py.
    """
    returns = _log_returns(prices)
    if lookback_days is not None:
        returns = returns[-lookback_days:]

    def _fit(d: str):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            am = arch_model(returns, mean="Zero", vol="EGARCH", p=1, o=1, q=1, dist=d, rescale=False)
            # EGARCH's likelihood surface is less well-behaved than plain
            # GARCH's; the default iteration budget occasionally isn't
            # enough to converge.
            return am.fit(disp="off", options={"maxiter": 500})

    res = _fit(dist)
    if _is_degenerate(res.params["alpha[1]"], res.params["gamma[1]"], res.params["beta[1]"]):
        if dist != "normal":
            res = _fit("normal")
        if _is_degenerate(res.params["alpha[1]"], res.params["gamma[1]"], res.params["beta[1]"]):
            raise DegenerateFitError(
                f"EGARCH fit for label={label!r} did not converge to sane parameters "
                f"(alpha={res.params['alpha[1]']:.3g}, gamma={res.params['gamma[1]']:.3g}, "
                f"beta={res.params['beta[1]']:.3g}) even after a Normal-distribution retry."
            )

    std_resid = np.asarray(res.std_resid)
    std_resid = std_resid[~np.isnan(std_resid)]
    # A well-behaved standardized residual is roughly unit-scale — even a
    # genuine fat-tail crash day rarely exceeds +/-8ish. Values far beyond
    # that (found empirically: one degenerate fit produced residuals in the
    # hundreds, because its own in-sample conditional volatility collapsed
    # to near-zero for a few days) are a numerical artifact of a bad fit,
    # not real market behavior — clip before this pool gets bootstrapped
    # into the simulation, rather than letting an artifact dominate it.
    std_resid = np.clip(std_resid, -10.0, 10.0)
    edges = np.quantile(std_resid, np.linspace(0, 1, N_STATES + 1))
    states = _classify(std_resid, edges)

    transition = np.ones((N_STATES, N_STATES))  # Laplace smoothing avoids zero-prob dead ends
    for prev, nxt in zip(states[:-1], states[1:]):
        transition[prev, nxt] += 1
    transition = transition / transition.sum(axis=1, keepdims=True)

    state_resid = [std_resid[states == s] if np.any(states == s) else std_resid for s in range(N_STATES)]

    next_var = res.forecast(horizon=1, reindex=False).variance.iloc[-1, 0]
    next_log_var = float(np.log(next_var))

    # Safety net for a degenerate fit: the optimizer can report success
    # (convergence_flag == 0) while landing on a pathological solution —
    # found empirically on one historical window where a Student-t fit's
    # degrees-of-freedom landed near 2 (the boundary of finite variance),
    # producing alpha/gamma two orders of magnitude outside any reasonable
    # range and a forecasted variance around e^700. `convergence_flag`
    # alone doesn't catch this, so anchor the starting log-variance to the
    # window's own empirical log-variance instead of trusting the fit
    # blindly — a data-grounded reference that's always sane regardless of
    # why the optimizer misbehaved.
    # ±4 in log-variance space means a 7x-either-direction swing in daily
    # sigma around the window's own realized level (sigma=1 -> up to ~7.4,
    # already an extreme single-day move in RETURN_SCALE=percent units) —
    # generous for real volatility regimes, nowhere near wide enough to
    # accommodate the pathological fit that motivated this clip in the
    # first place (that one had a forecasted sigma in the hundreds).
    empirical_log_var = float(np.log(np.var(returns)))
    next_log_var = float(np.clip(next_log_var, empirical_log_var - 4.0, empirical_log_var + 4.0))

    return MarkovModel(
        edges=edges, transition=transition, state_resid=state_resid,
        omega=float(res.params["omega"]), alpha=float(res.params["alpha[1]"]),
        gamma=float(res.params["gamma[1]"]), beta=float(res.params["beta[1]"]),
        mean_abs_std_resid=float(np.mean(np.abs(std_resid))),
        last_std_resid=float(std_resid[-1]), next_log_variance=next_log_var,
        label=label,
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
    log_var_pos = np.full(half, model.next_log_variance)
    log_var_neg = np.full(half, model.next_log_variance)
    returns_pos = np.empty((half, n_days))
    returns_neg = np.empty((half, n_days)) if antithetic else None

    # Numerical safety: a poorly-converged fit on some historical windows can
    # produce EGARCH parameters where the log-variance recursion drifts
    # without bound over a multi-day simulation, overflowing to inf/nan
    # (caught empirically backtesting many historical events). Clip
    # log-variance to a band around its own (already sanity-clamped, see
    # fit_model) starting point — ±4 lets daily sigma swing up to ~7x
    # either direction, generous for real volatility regimes without
    # leaving room for the runaway values a degenerate fit can produce.
    log_var_lo, log_var_hi = model.next_log_variance - 4.0, model.next_log_variance + 4.0

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

        abs_term = model.alpha * (np.abs(z) - model.mean_abs_std_resid)  # sign-invariant

        returns_pos[:, day] = z * np.sqrt(np.exp(log_var_pos))
        log_var_pos = np.clip(model.omega + model.beta * log_var_pos + abs_term + model.gamma * z,
                               log_var_lo, log_var_hi)

        if antithetic:
            returns_neg[:, day] = -z * np.sqrt(np.exp(log_var_neg))
            log_var_neg = np.clip(model.omega + model.beta * log_var_neg + abs_term - model.gamma * z,
                                   log_var_lo, log_var_hi)

    all_log_returns = np.vstack([returns_pos, returns_neg]) if antithetic else returns_pos

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
