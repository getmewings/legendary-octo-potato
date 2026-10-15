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


def satellite_picks(
    closes: pd.DataFrame,
    universe: list[str] | None = None,
    top_n: int = 3,
    as_of: pd.Timestamp | None = None,
    lookback: int = 252,
    skip: int = 21,
) -> list[str]:
    """Sector picks in force on ``as_of`` (default: last bar).

    Picks are made once per month from the close of that month's first trading
    day, exactly as ``SectorMomentum`` does, so a mid-month call returns the
    same picks as the month's first bar.
    """
    universe = list(universe or SECTOR_ETFS)
    closes = closes if as_of is None else closes.loc[:as_of]
    last = closes.index[-1]
    in_month = (closes.index.year == last.year) & (closes.index.month == last.month)
    first_pos = int(in_month.argmax())
    ranking = momentum_ranking(closes[universe].iloc[: first_pos + 1], lookback, skip)
    return list(ranking.index[:top_n])


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


class CoreSectorTilt(SectorMomentum):
    """Core index fund plus a buy-only tilt toward the top sector ETFs.

    Each deposit is split between the core and this month's top-N sectors.
    Nothing is ever sold, so rotating picks realizes no gains in a taxable
    account. Old picks simply stop receiving new money.
    """

    buy_only = True

    def __init__(self, core: str = "SPY", core_weight: float = 0.7, **kwargs) -> None:
        super().__init__(**kwargs)
        self.core = core
        self.core_weight = core_weight
        self.name = f"{core_weight:.0%} {core} + {1 - core_weight:.0%} sector tilt (buy-only)"
        self.tickers = [core, *self.universe]

    def decide(self, history: pd.DataFrame, current: Weights | None) -> Weights | None:
        if current is None:  # first decision: don't wait for a month boundary
            picks = satellite_picks(history, self.universe, self.top_n, None, self.lookback, self.skip)
        else:
            sat = super().decide(history, current)
            if sat is None:
                return None
            picks = list(sat)
        if not picks:
            return {self.core: 1.0}
        weights = {self.core: self.core_weight}
        weights.update({t: (1.0 - self.core_weight) / len(picks) for t in picks})
        return weights
