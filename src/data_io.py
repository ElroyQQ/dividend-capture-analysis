"""Historical price/dividend data ingestion via yfinance. No hardcoded prices —
everything here is a live query against Yahoo Finance so numbers can't drift
from reality or get hallucinated by an LLM."""

from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf


def fetch_history(ticker: str, period: str = "5y") -> pd.DataFrame:
    """Daily OHLCV + dividends for `ticker` over `period`. Index is tz-naive date."""
    df = yf.Ticker(ticker).history(period=period, auto_adjust=False)
    if df.empty:
        raise ValueError(f"No data returned for {ticker!r} — check the symbol.")
    df.index = df.index.tz_localize(None)
    # yfinance sometimes appends a row for the most recent session before it has
    # fully finalized (NaN Close) — drop it rather than let NaN propagate into
    # every downstream calculation that assumes the last row is a real price.
    df = df[df["Close"].notna()]
    if df.empty:
        raise ValueError(f"{ticker!r}: all rows had a NaN Close after filtering.")
    return df


def ex_dividend_events(history: pd.DataFrame) -> pd.DataFrame:
    """Rows of `history` where a dividend was paid, with columns for the
    cum-dividend close (prior trading day) and ex-dividend close (same day)."""
    events = history.loc[history["Dividends"] > 0, ["Dividends"]].copy()
    closes = history["Close"]
    events["cum_close"] = [closes.loc[:d].iloc[-2] if len(closes.loc[:d]) > 1 else None
                            for d in events.index]
    events["ex_close"] = closes.loc[events.index]
    events = events.dropna()
    events["drop"] = events["cum_close"] - events["ex_close"]
    events["Q_ratio"] = events["drop"] / events["Dividends"]
    return events


def trailing_dividend_yield(history: pd.DataFrame) -> float:
    """Trailing-12-month dividends per share / latest close."""
    last_date = history.index[-1]
    trailing = history.loc[history.index > last_date - pd.Timedelta(days=365), "Dividends"].sum()
    return trailing / history["Close"].iloc[-1]


def seasonal_return_pattern(history: pd.DataFrame, event_indices: list[int],
                             pre_window: int, post_window: int) -> np.ndarray | None:
    """Average cumulative log-return curve around a set of prior ex-dividend
    events, aligned so index `pre_window` = the ex-dividend day. This is a
    plain event-study seasonal average (not a market-model/CAPM-adjusted
    abnormal return — no benchmark index is subtracted), used to give the
    Markov simulation explicit awareness of the historical pre-dividend
    run-up / post-dividend drift pattern for this specific ticker, which a
    memoryless state-transition model can't otherwise see. Returns None if
    fewer than 2 usable events are given (too little history to estimate a
    pattern without just overfitting one event)."""
    closes = history["Close"].values
    n = len(closes)
    curves = []
    for idx in event_indices:
        if idx - pre_window < 0 or idx + post_window >= n:
            continue
        window = closes[idx - pre_window: idx + post_window + 1]
        curves.append(np.log(window / window[0]))
    if len(curves) < 2:
        return None
    return np.mean(curves, axis=0)
