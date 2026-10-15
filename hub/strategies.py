"""Rules-based strategies.

A strategy sees only the price history up to and including the current close
and returns target weights, or ``None`` for "no change". Weights are a dict of
ticker -> fraction of the portfolio; anything unallocated is held in cash. An
empty dict means all cash. The backtester fills the order at the next open.

Parameters are fixed at textbook values and are deliberately not tuned.
"""

from __future__ import annotations

from typing import Protocol

import pandas as pd

Weights = dict[str, float]

SECTOR_ETFS = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]


class Strategy(Protocol):
    name: str
    tickers: list[str]

    def decide(self, history: pd.DataFrame, current: Weights | None) -> Weights | None: ...


class BuyAndHold:
    """Benchmark: put everything in one ticker and keep it there."""

    def __init__(self, ticker: str = "SPY") -> None:
        self.ticker = ticker
        self.name = f"{ticker} buy & hold"
        self.tickers = [ticker]

    def decide(self, history: pd.DataFrame, current: Weights | None) -> Weights | None:
        return {self.ticker: 1.0} if current is None else None


class TrendFilter:
    """Hold the index while its close is above its simple moving average, else cash."""

    def __init__(self, ticker: str = "SPY", window: int = 200) -> None:
        self.ticker = ticker
        self.window = window
        self.name = f"{ticker} {window}d SMA trend"
        self.tickers = [ticker]

    def decide(self, history: pd.DataFrame, current: Weights | None) -> Weights | None:
        if len(history) < self.window:
            return None
        px = history[self.ticker]
        sma = px.iloc[-self.window :].mean()
        desired: Weights = {self.ticker: 1.0} if px.iloc[-1] > sma else {}
        return desired if desired != current else None


def momentum_ranking(history: pd.DataFrame, lookback: int = 252, skip: int = 21) -> pd.Series:
    """12-1 momentum: return from ``lookback`` bars ago to ``skip`` bars ago, best first."""
    if len(history) < lookback + 1:
        return pd.Series(dtype=float)
    ret = history.iloc[-1 - skip] / history.iloc[-1 - lookback] - 1.0
    return ret.sort_values(ascending=False, kind="stable")


class SectorMomentum:
    """Equal-weight the top-N sector ETFs by 12-1 momentum, rebalanced monthly.

    Decides on the first trading day of each month (using that day's close), so
    the fill happens on the second trading day. No look-ahead.
    """

    def __init__(
        self,
        universe: list[str] | None = None,
        top_n: int = 3,
        lookback: int = 252,
        skip: int = 21,
    ) -> None:
        self.universe = list(universe or SECTOR_ETFS)
        self.top_n = top_n
        self.lookback = lookback
        self.skip = skip
        self.name = f"Top-{top_n} sector momentum (12-1, monthly)"
        self.tickers = self.universe

    def decide(self, history: pd.DataFrame, current: Weights | None) -> Weights | None:
        if len(history) < 2 or history.index[-1].month == history.index[-2].month:
            return None
        ranking = momentum_ranking(history[self.universe], self.lookback, self.skip)
        if ranking.empty:
            return None
        picks = list(ranking.index[: self.top_n])
        return {t: 1.0 / self.top_n for t in picks}
