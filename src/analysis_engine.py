"""
Dividend-capture research prototype: main orchestrator.

v2 (session 3) upgrades over the original quantile-Markov version — see
docs/system_architecture.md and AI_Performance_Report.md for the reasoning
and citations behind each:

  1. GARCH(1,1)-filtered regime bootstrap (markov.py) instead of a plain
     quantile-bucketed return bootstrap — addresses the non-stationary-
     volatility limitation the project brief names explicitly.
  2. An explicit ex-dividend calendar-drift term (data_io.py) derived from
     this ticker's own prior ex-dividend events — gives the simulation
     awareness of the pre-dividend run-up / post-dividend drift pattern
     that a memoryless state model otherwise can't see.
  3. Antithetic-variate variance reduction in the Monte Carlo (markov.py).
  4. Multi-event backtesting: instead of scoring a ticker off a single
     historical ex-dividend event, every usable event in the lookback
     window (capped for runtime) is run through the full entry/exit
     search, and results are aggregated (hit rate, median recovery time,
     mean/std of net return) — the previous version's ranking was
     statistically an N=1 anecdote per ticker.

For each ticker this still:
  - Pulls 5y of daily price + dividend history (data_io.py).
  - Fits "conservative" (Student-t GARCH, full history) and "recent"
    (Normal GARCH, trailing ~252 days) model variants.
  - Finds an entry point (lowest-expected-price day in the 15 trading days
    before an ex-dividend date) and an exit point (first day after where
    expected price + dividend recovers the pre-dividend price).
  - Ranks tickers by a risk-reward score.

Output: output/report.md, output/ranking.csv, output/<ticker>_paths.png,
interface/index.html.

This is a backtesting/research tool. It does not place trades and is not
investment advice — see AI_Performance_Report.md for caveats.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import data_io
import markov
from markov import DegenerateFitError

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"
OUTPUT.mkdir(exist_ok=True)

TICKERS = {
    "TTE": "trade_exit — energy major, quarterly dividend",
    "O": "hold — monthly-paying REIT (Realty Income)",
    "AGNC": "hold — monthly-paying mortgage REIT",
    "STAG": "hold — monthly-paying industrial REIT",
}

MODEL_SPECS = {
    "conservative": dict(dist="t"),                       # heavy-tailed, full history
    "recent": dict(dist="normal", lookback_days=252),      # trailing ~1y, unfiltered
}

PRE_WINDOW = 15            # trading days before ex-div date to search for entry
POST_WINDOW = 40           # trading days after ex-div date to search for recovery
MIN_FIT_HISTORY = 300      # min trading days of pre-event history required to fit a model
N_SIMS_HEADLINE = 100_000  # most recent event only — used for the interface/chart
N_SIMS_BACKTEST = 8_000    # per historical event in the multi-event aggregate
MAX_BACKTEST_EVENTS = 50   # cap on how many past events get the full search (runtime)


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score confidence interval for a binomial proportion (hit
    rate). Unlike a naive +/- on the raw percentage, this doesn't collapse
    to zero width at 0%/100% and has much better coverage at small n — the
    exact situation an 8-or-20-event backtest is in. A reported "100% hit
    rate, n=8" without this looks far more certain than it is; see
    docs/system_architecture.md for the citation."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    margin = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def _usable_event_indices(history: pd.DataFrame, events: pd.DataFrame) -> list[int]:
    """Ex-dividend events with enough history on both sides to run the full
    search. MIN_FIT_HISTORY (comfortably more than the "recent" model's
    252-day lookback) matters, not just PRE_WINDOW — an event with only, say,
    20 days of prior history technically has "enough" for the entry-window
    search itself, but nowhere near enough for a stable GARCH fit. Events
    that early produced NaN parameters/returns when this wasn't enforced
    (caught by testing with a larger MAX_BACKTEST_EVENTS)."""
    idxs = []
    for ex_date in events.index:
        idx = history.index.get_loc(ex_date)
        if idx - PRE_WINDOW - MIN_FIT_HISTORY >= 0 and idx + POST_WINDOW < len(history):
            idxs.append(idx)
    return idxs


def _entry_exit_search(history: pd.DataFrame, ex_idx: int, dividend: float, cum_close: float,
                        ex_close: float, prior_indices: list[int], n_sims: int,
                        seed_base: int, event_gap: int, keep_paths: bool = False) -> dict:
    """Run the full entry+exit Monte Carlo search for one ex-dividend event,
    for both model variants. Returns a dict keyed by model label."""
    # Cap the calendar-drift window to (at most) half the ticker's own median
    # gap between ex-dividend events. A monthly payer's events are only ~21
    # trading days apart — the full 15/40-day entry/exit window would run
    # into the *next* dividend cycle and contaminate the "seasonal" average
    # with unrelated dynamics. Days beyond the safe window get zero drift
    # (no claimed calendar signal) rather than a contaminated one.
    safe_pre = max(3, min(PRE_WINDOW, event_gap // 2 - 1))
    safe_post = max(3, min(POST_WINDOW, event_gap // 2 - 1))
    seasonal = data_io.seasonal_return_pattern(history, prior_indices, safe_pre, safe_post)
    entry_drift = np.zeros(PRE_WINDOW)
    exit_drift = np.zeros(POST_WINDOW)
    if seasonal is not None:
        diffs = np.diff(seasonal)
        entry_drift[PRE_WINDOW - safe_pre:] = diffs[:safe_pre]
        exit_drift[:safe_post] = diffs[safe_pre:safe_pre + safe_post]

    entry_window_start_price = float(history["Close"].iloc[ex_idx - PRE_WINDOW])
    pre_slice = history["Close"].iloc[: ex_idx - PRE_WINDOW]     # no lookahead
    post_slice = history["Close"].iloc[: ex_idx + 1]             # includes ex-div day itself

    out = {}
    for label, kwargs in MODEL_SPECS.items():
        entry_model = markov.fit_model(pre_slice, label=label, **kwargs)
        entry_state = markov.current_state(entry_model)
        entry_paths = markov.simulate(entry_model, entry_window_start_price, entry_state,
                                       PRE_WINDOW, n_sims=n_sims, seed=seed_base + 1)
        entry_paths = markov.apply_calendar_drift(entry_paths, entry_drift)
        entry_mean = entry_paths.mean(axis=0)
        entry_offset = int(np.argmin(entry_mean))
        buy_price = float(entry_mean[entry_offset])

        exit_model = markov.fit_model(post_slice, label=label, **kwargs)
        exit_state = markov.current_state(exit_model)
        exit_paths = markov.simulate(exit_model, ex_close, exit_state,
                                      POST_WINDOW, n_sims=n_sims, seed=seed_base + 2)
        exit_paths = markov.apply_calendar_drift(exit_paths, exit_drift)
        exit_mean = exit_paths.mean(axis=0)

        target = cum_close - dividend
        recovered = np.where(exit_mean >= target)[0]
        recovery_days = int(recovered[recovered > 0][0]) if np.any(recovered > 0) else None
        sell_offset = recovery_days if recovery_days is not None else POST_WINDOW
        sell_price = float(exit_mean[sell_offset])

        buy_days_before_ex = PRE_WINDOW - entry_offset
        out[label] = {
            "buy_days_before_ex": buy_days_before_ex,
            "entry_price": buy_price,
            "sell_days_after_ex": recovery_days,
            "exit_price": sell_price,
            "recovered": recovery_days is not None,
            "total_hold_days": buy_days_before_ex + sell_offset,
            "net_return_pct": (sell_price + dividend - buy_price) / buy_price * 100,
        }
        if keep_paths:
            out[label]["entry_mean_path"] = entry_mean
            out[label]["exit_mean_path"] = exit_mean
    return out


def analyze_ticker(ticker: str) -> dict:
    history = data_io.fetch_history(ticker, period="5y")
    events = data_io.ex_dividend_events(history)
    if events.empty:
        raise ValueError(f"{ticker}: no dividend events found in 5y window.")

    q_ratio = events["Q_ratio"].median()
    trailing_yield = data_io.trailing_dividend_yield(history)

    usable_idxs = _usable_event_indices(history, events)
    if not usable_idxs:
        raise ValueError(f"{ticker}: no ex-div event with sufficient surrounding data.")

    headline_idx = usable_idxs[-1]
    headline_date = history.index[headline_idx]
    backtest_idxs = usable_idxs[-MAX_BACKTEST_EVENTS:]
    event_gap = int(np.median(np.diff(usable_idxs))) if len(usable_idxs) > 1 else PRE_WINDOW + POST_WINDOW

    # --- Multi-event backtest: statistical aggregate across up to MAX_BACKTEST_EVENTS ---
    per_label_events = {label: [] for label in MODEL_SPECS}
    n_skipped_degenerate = 0
    for seed_i, idx in enumerate(backtest_idxs):
        ex_date = history.index[idx]
        dividend = float(history.loc[ex_date, "Dividends"])
        cum_close = float(history["Close"].iloc[idx - 1])
        ex_close = float(history["Close"].iloc[idx])
        prior_indices = [i for i in usable_idxs if i < idx - PRE_WINDOW]
        try:
            event_result = _entry_exit_search(history, idx, dividend, cum_close, ex_close,
                                               prior_indices, n_sims=N_SIMS_BACKTEST,
                                               seed_base=100 + seed_i * 10, event_gap=event_gap)
        except DegenerateFitError:
            # Rare (see markov.DegenerateFitError) — a specific historical
            # window's EGARCH fit didn't converge to sane parameters even
            # after a distribution retry. Skip this one event rather than
            # let corrupted numbers into the aggregate; n_events in the
            # report reflects the actual sample used, not backtest_idxs'
            # length, so this stays honest rather than silently padded.
            n_skipped_degenerate += 1
            continue
        for label in MODEL_SPECS:
            per_label_events[label].append(event_result[label])

    backtest_summary = {}
    for label, ev_list in per_label_events.items():
        n = len(ev_list)
        if n == 0:
            raise ValueError(f"{ticker}/{label}: every backtested event's fit was degenerate "
                              f"({n_skipped_degenerate} skipped) — no usable sample.")
        hits = sum(e["recovered"] for e in ev_list)
        hit_rate = hits / n
        hit_rate_lo, hit_rate_hi = wilson_interval(hits, n)
        recovered_days = [e["sell_days_after_ex"] for e in ev_list if e["recovered"]]
        net_returns = np.array([e["net_return_pct"] for e in ev_list])
        hold_days = np.array([e["total_hold_days"] for e in ev_list])
        backtest_summary[label] = {
            "n_events": n,
            "n_skipped_degenerate": n_skipped_degenerate,
            "hit_rate": hit_rate,
            "hit_rate_ci": (hit_rate_lo, hit_rate_hi),
            "median_recovery_days": float(np.median(recovered_days)) if recovered_days else None,
            "mean_net_return_pct": float(net_returns.mean()),
            "std_net_return_pct": float(net_returns.std(ddof=1)) if n > 1 else 0.0,
            "mean_hold_days": float(hold_days.mean()),
        }

    # --- Headline event: full-fidelity single-event detail for the chart/interface ---
    # Try the most recent usable event first; if its fit is degenerate (rare
    # — see DegenerateFitError), fall back to the next most recent rather
    # than let one bad historical window take down the whole ticker.
    headline = None
    for candidate_idx in reversed(usable_idxs[-6:]):
        ex_date = history.index[candidate_idx]
        dividend = float(history.loc[ex_date, "Dividends"])
        cum_close = float(history["Close"].iloc[candidate_idx - 1])
        ex_close = float(history["Close"].iloc[candidate_idx])
        prior_indices = [i for i in usable_idxs if i < candidate_idx - PRE_WINDOW]
        try:
            headline = _entry_exit_search(history, candidate_idx, dividend, cum_close, ex_close,
                                           prior_indices, n_sims=N_SIMS_HEADLINE, seed_base=1,
                                           event_gap=event_gap, keep_paths=True)
            headline_idx = candidate_idx
            headline_date = ex_date
            break
        except DegenerateFitError:
            continue
    if headline is None:
        raise ValueError(f"{ticker}: the last 6 usable events all had degenerate fits — "
                          f"can't produce a headline chart/detail view.")

    # Actual price around the headline event, indexed to 100 at the ex-div
    # date — used by plot_comparison_chart() to overlay every ticker on one
    # chart. Real (not simulated) prices, since the point is to compare
    # actual historical volatility/recovery shape at a glance.
    comparison_slice = history["Close"].iloc[headline_idx - PRE_WINDOW: headline_idx + POST_WINDOW]
    comparison_x = list(range(-PRE_WINDOW, len(comparison_slice) - PRE_WINDOW))
    comparison_y = (comparison_slice.values / ex_close * 100).tolist()

    result = {
        "ticker": ticker, "q_ratio": q_ratio, "trailing_yield": trailing_yield,
        "ex_date": headline_date, "dividend": dividend, "cum_close": cum_close,
        "headline": headline, "backtest": backtest_summary,
        "comparison_series": {"x": comparison_x, "y": comparison_y},
    }
    plot_paths(ticker, history, headline_idx, result)
    return result


def plot_paths(ticker: str, history: pd.DataFrame, ex_idx: int, result: dict) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    actual = history["Close"].iloc[ex_idx - PRE_WINDOW: ex_idx + POST_WINDOW]
    x_actual = np.arange(-PRE_WINDOW, len(actual) - PRE_WINDOW)
    ax.plot(x_actual, actual.values, color="black", lw=1.5, label="Actual price")

    for label, color in [("conservative", "#2a6f77"), ("recent", "#c0563a")]:
        entry_mean = result["headline"][label]["entry_mean_path"]
        exit_mean = result["headline"][label]["exit_mean_path"]
        x_entry = np.arange(-PRE_WINDOW, 1)
        x_exit = np.arange(0, len(exit_mean))
        ax.plot(x_entry, entry_mean, color=color, lw=2, ls="--", alpha=0.8)
        ax.plot(x_exit, exit_mean, color=color, lw=2, ls="--",
                label=f"{label} model — expected path (GARCH + calendar drift)")

    ax.axvline(0, color="gray", lw=1, ls=":")
    ax.axhline(result["cum_close"] - result["dividend"], color="gray", lw=1, ls=":",
               label="Recovery target (cum price − dividend)")
    bt = result["backtest"]["conservative"]
    ci_lo, ci_hi = bt["hit_rate_ci"]
    ax.set_title(f"{ticker}: price around ex-dividend date {result['ex_date'].date()}  "
                 f"(backtest: {bt['hit_rate']*100:.0f}% hit rate [{ci_lo*100:.0f}–{ci_hi*100:.0f}%], n={bt['n_events']})")
    ax.set_xlabel("Trading days relative to ex-dividend date")
    ax.set_ylabel("Price ($)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUTPUT / f"{ticker}_paths.png", dpi=140)
    plt.close(fig)


# First 4 slots of the dataviz reference categorical palette (light-mode hexes;
# this chart is a static PNG, always rendered on a white matplotlib background
# regardless of the interface page's own light/dark theme), in the fixed order
# the palette validates for CVD-safety on adjacent pairs.
COMPARISON_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]  # blue, orange, aqua, yellow


def plot_comparison_chart(results: list[dict]) -> None:
    """Overlay every ticker's actual price around its headline ex-dividend
    event, indexed to 100 at the ex-div date, on one chart — lets a viewer
    compare volatility/recovery shape across tickers at a glance, which a
    separate chart per ticker (with its own y-axis scale) doesn't support."""
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for i, r in enumerate(results):
        cs = r["comparison_series"]
        color = COMPARISON_COLORS[i % len(COMPARISON_COLORS)]
        ax.plot(cs["x"], cs["y"], color=color, lw=2, label=r["ticker"])
        # Direct end-of-line label — the dataviz palette's yellow/aqua slots
        # don't clear 3:1 contrast on a white background, so a label next to
        # the line (not just a legend swatch) keeps the series identifiable
        # rather than relying on color alone.
        ax.annotate(r["ticker"], (cs["x"][-1], cs["y"][-1]), color=color,
                     fontsize=9, fontweight="bold", xytext=(6, 0),
                     textcoords="offset points", va="center")

    ax.axvline(0, color="gray", lw=1, ls=":")
    ax.axhline(100, color="gray", lw=1, ls=":")
    ax.set_title("Actual price around each ticker's headline ex-dividend date, indexed to 100")
    ax.set_xlabel("Trading days relative to ex-dividend date")
    ax.set_ylabel("Price (indexed, ex-div day = 100)")
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(OUTPUT / "comparison_paths.png", dpi=140)
    plt.close(fig)


def rank(results: list[dict]) -> pd.DataFrame:
    rows = []
    for r in results:
        bt = r["backtest"]["conservative"]
        hit_rate_lo, hit_rate_hi = bt["hit_rate_ci"]
        # Risk-reward: mean per-cycle return, discounted by the *lower bound*
        # of the Wilson confidence interval on hit rate (not the raw point
        # estimate) — a ticker with "100% hit rate, n=8" and one with "100%
        # hit rate, n=40" shouldn't score identically; the smaller sample's
        # true hit rate could plausibly be much lower, and the CI lower
        # bound reflects that directly in the ranking, not just in a
        # footnote. Expressed per day held.
        score = (bt["mean_net_return_pct"] * hit_rate_lo) / bt["mean_hold_days"]
        rows.append({
            "ticker": r["ticker"],
            "category": TICKERS[r["ticker"]],
            "trailing_yield_pct": round(r["trailing_yield"] * 100, 2),
            "median_Q_ratio": round(r["q_ratio"], 2),
            "n_backtest_events": bt["n_events"],
            "hit_rate_pct": round(bt["hit_rate"] * 100, 1),
            "hit_rate_95ci": f"{hit_rate_lo*100:.0f}–{hit_rate_hi*100:.0f}%",
            "mean_return_per_cycle_pct": round(bt["mean_net_return_pct"], 3),
            "std_return_per_cycle_pct": round(bt["std_net_return_pct"], 3),
            "median_recovery_days": bt["median_recovery_days"] if bt["median_recovery_days"] is not None else f">{POST_WINDOW}",
            "risk_reward_score": round(score, 4),
        })
    df = pd.DataFrame(rows).sort_values("risk_reward_score", ascending=False).reset_index(drop=True)
    return df


def classify_suitability(df: pd.DataFrame) -> dict[str, dict]:
    """Plain-language "who is this for" label per ticker, based on the
    conservative-model backtest stats already in `df`. Thresholds are
    relative to the current ticker set's own median (not fixed constants),
    so the classification stays sensible if TICKERS changes:

    - "Not recommended": historically unreliable (<60% hit rate) or
      unprofitable on average — regardless of risk appetite.
    - "Conservative pick": at-or-above-median hit rate (and at least 75%)
      AND at-or-below-median swing between events — reliability first.
    - "Aggressive pick": at-or-above-median average return but didn't
      qualify as conservative — biggest average payoff, less consistency.
    - "Balanced": everything else — middling on both counts.
    """
    median_hit = df["hit_rate_pct"].median()
    median_std = df["std_return_per_cycle_pct"].median()
    median_return = df["mean_return_per_cycle_pct"].median()
    out = {}
    for _, row in df.iterrows():
        hit, std, ret = row["hit_rate_pct"], row["std_return_per_cycle_pct"], row["mean_return_per_cycle_pct"]
        if ret <= 0 or hit < 60:
            label = "Not recommended"
            reason = f"Only a {hit:.0f}% historical hit rate" + (" and a negative average return" if ret <= 0 else "") + " — weak track record either way."
        elif hit >= max(75, median_hit) and std <= median_std:
            label = "Conservative pick"
            reason = f"Recovered in {hit:.0f}% of its last {int(row['n_backtest_events'])} dividend cycles, with a comparatively narrow spread of outcomes (±{std:.1f}%)."
        elif ret >= median_return:
            label = "Aggressive pick"
            reason = f"Highest average payoff of the group (+{ret:.1f}% per cycle), but outcomes swing wider (±{std:.1f}%) between events."
        else:
            label = "Balanced"
            reason = f"Middling on both counts — {hit:.0f}% hit rate, +{ret:.1f}% average return."
        out[row["ticker"]] = {"suitability": label, "suitabilityReason": reason}
    return out


def write_report(df: pd.DataFrame, suitability: dict[str, dict]) -> None:
    lines = ["# Dividend Capture — Analysis Report", "",
             f"GARCH-filtered regime-bootstrap Monte Carlo "
             f"({N_SIMS_HEADLINE:,} paths for the headline event, {N_SIMS_BACKTEST:,} paths "
             f"× up to {MAX_BACKTEST_EVENTS} historical events per ticker for the backtest "
             "aggregate), with antithetic variance reduction and an ex-dividend calendar-drift "
             "adjustment. See docs/system_architecture.md for the full methodology.", "",
             "## Quick picks", "",
             "| Ticker | Best for | Why |", "|---|---|---|"] + [
                 f"| {t} | {suitability[t]['suitability']} | {suitability[t]['suitabilityReason']} |"
                 for t in df["ticker"]
             ] + ["",
             "## Ranking (highest risk-reward score first)", "",
             df.to_markdown(index=False), "",
             "## Notes", "",
             "- `n_backtest_events` / `hit_rate_pct`: how many historical ex-dividend events "
             "(capped, most recent first) were actually run through the entry/exit search, and "
             "what fraction of those recovered to breakeven within the window — the ranking's "
             "statistical sample size, not a single anecdote.",
             "- `hit_rate_95ci`: 95% Wilson confidence interval on the hit rate — how much the "
             "true hit rate could plausibly differ from the point estimate given the sample size. "
             "A narrow interval means the hit rate is well-supported; a wide one (common at small "
             "n) means don't over-read the headline percentage.",
             "- `mean_return_per_cycle_pct` / `std_return_per_cycle_pct`: average and spread of "
             "net return (price change + dividend, relative to entry price) across those "
             "backtested events under the conservative model.",
             "- `median_Q_ratio`: historical ex-div price drop ÷ dividend paid, across all usable "
             "events (not just the backtested subset). <1.0 = price tends to drop by less than "
             "the dividend; >1.0 = drops by more.",
             "- `risk_reward_score = mean_return_per_cycle_pct × (Wilson CI lower bound on hit "
             "rate) ÷ mean_hold_days` — return per day held, discounted by how reliably the "
             "backtest recovered *and* by how much sample size backs that reliability. Uses the "
             "CI lower bound rather than the raw hit rate so a small-sample \"100%\" doesn't "
             "outscore a larger-sample, slightly-lower hit rate that's actually better supported.",
             "- See AI_Performance_Report.md for where this model is and isn't reliable.",
             ""]
    (OUTPUT / "report.md").write_text("\n".join(lines))


def build_interface_records(results: list[dict], df: pd.DataFrame,
                             suitability: dict[str, dict]) -> list[dict]:
    by_ticker = {r["ticker"]: r for r in results}
    records = []
    for rank_idx, row in df.iterrows():
        r = by_ticker[row["ticker"]]
        models = {}
        for label in MODEL_SPECS:
            h = r["headline"][label]
            bt = r["backtest"][label]
            models[label] = {
                "buyDaysBeforeEx": h["buy_days_before_ex"],
                "entryPrice": round(h["entry_price"], 2),
                "sellDaysAfterEx": h["sell_days_after_ex"],
                "exitPrice": round(h["exit_price"], 2),
                "recovered": h["recovered"],
                "totalHoldDays": h["total_hold_days"],
                "netReturnPct": round(h["net_return_pct"], 3),
                "backtestNEvents": bt["n_events"],
                "backtestHitRatePct": round(bt["hit_rate"] * 100, 1),
                "backtestHitRateCiLoPct": round(bt["hit_rate_ci"][0] * 100, 1),
                "backtestHitRateCiHiPct": round(bt["hit_rate_ci"][1] * 100, 1),
                "backtestMeanReturnPct": round(bt["mean_net_return_pct"], 3),
                "backtestStdReturnPct": round(bt["std_net_return_pct"], 3),
            }
        records.append({
            "rank": int(rank_idx) + 1,
            "ticker": r["ticker"],
            "category": TICKERS[r["ticker"]],
            "trailingYieldPct": round(r["trailing_yield"] * 100, 2),
            "qRatio": round(r["q_ratio"], 2),
            "exDate": str(r["ex_date"].date()),
            "dividend": round(r["dividend"], 4),
            "cumClose": round(r["cum_close"], 2),
            "riskRewardScore": round(row["risk_reward_score"], 4),
            "chart": f"../output/{r['ticker']}_paths.png",
            "suitability": suitability[r["ticker"]]["suitability"],
            "suitabilityReason": suitability[r["ticker"]]["suitabilityReason"],
            "models": models,
        })
    return records


def write_interface(records: list[dict]) -> None:
    interface_dir = ROOT / "interface"
    interface_dir.mkdir(exist_ok=True)
    template = (Path(__file__).parent / "interface_template.html").read_text()
    html = template.replace("__STOCK_DATA__", json.dumps(records, indent=2))
    html = html.replace("__GENERATED_AT__", pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"))
    html = html.replace("__POST_WINDOW__", str(POST_WINDOW))
    (interface_dir / "index.html").write_text(html)


def main() -> None:
    results = []
    for ticker in TICKERS:
        print(f"Analyzing {ticker}...")
        results.append(analyze_ticker(ticker))
    plot_comparison_chart(results)
    df = rank(results)
    df.to_csv(OUTPUT / "ranking.csv", index=False)
    suitability = classify_suitability(df)
    write_report(df, suitability)
    records = build_interface_records(results, df, suitability)
    write_interface(records)
    print(df.to_string(index=False))
    print(f"\nWrote {OUTPUT / 'report.md'}, {OUTPUT / 'ranking.csv'}, per-ticker charts to {OUTPUT}/, "
          f"and interface/index.html")


if __name__ == "__main__":
    main()
