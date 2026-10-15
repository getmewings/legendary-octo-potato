"""Contribution-aware backtester.

Model:
- A fixed deposit arrives every ``period_days`` calendar days (on the first
  trading day on or after the due date) and lands at that day's open.
- Strategies decide at a close; orders fill at the NEXT bar's open.
- Every trade pays ``slippage_bps`` of its notional (spread/slippage proxy).
- Fractional shares; cash earns 0%.
- A deposit on a day with no rebalance is spent on the current target weights.
- Strategies with ``buy_only = True`` never sell: a new target only changes how
  future deposits are split (the tax-friendly mode for a taxable account).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .data import Prices
from .strategies import Strategy, Weights


@dataclass
class Result:
    name: str
    equity: pd.Series  # portfolio value at each close
    deposits: pd.Series  # cash deposited on each day (0 on most days)
    trades: int
    traded_notional: float
    cost_paid: float

    @property
    def contributed(self) -> float:
        return float(self.deposits.sum())

    @property
    def ending_value(self) -> float:
        return float(self.equity.iloc[-1])

    def twr_index(self) -> pd.Series:
        """Time-weighted return index (deposit-neutral), starting at 1.0."""
        prev = self.equity.shift(1).fillna(0.0) + self.deposits
        ret = (self.equity / prev.replace(0.0, np.nan)).fillna(1.0) - 1.0
        return (1.0 + ret).cumprod()

    def max_drawdown(self) -> float:
        idx = self.twr_index()
        return float((idx / idx.cummax() - 1.0).min())

    def twr_cagr(self) -> float:
        idx = self.twr_index()
        years = (idx.index[-1] - idx.index[0]).days / 365.25
        return float(idx.iloc[-1] ** (1.0 / years) - 1.0) if years > 0 else float("nan")

    def xirr(self) -> float:
        return xirr(self.deposits[self.deposits > 0], self.ending_value, self.equity.index[-1])


def xirr(deposits: pd.Series, ending_value: float, end_date: pd.Timestamp) -> float:
    """Money-weighted annual return for dated deposits plus a final value."""
    if deposits.empty or ending_value <= 0:
        return float("nan")
    t_dep = np.array([(d - deposits.index[0]).days / 365.0 for d in deposits.index])
    t_end = (end_date - deposits.index[0]).days / 365.0
    amounts = deposits.to_numpy(dtype=float)

    def npv(rate: float) -> float:
        return float(ending_value / (1.0 + rate) ** t_end - (amounts / (1.0 + rate) ** t_dep).sum())

    lo, hi = -0.99, 10.0
    if npv(lo) * npv(hi) > 0:
        return float("nan")
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2.0


def run_backtest(
    strategy: Strategy,
    prices: Prices,
    start: str,
    deposit: float = 100.0,
    period_days: int = 14,
    slippage_bps: float = 5.0,
) -> Result:
    """Simulate ``strategy`` from ``start`` with recurring deposits.

    Price history before ``start`` is visible to the strategy (for warm-up) but
    no money is invested before ``start``.
    """
    opens, closes = prices.open, prices.close
    dates = closes.index
    first = int(dates.searchsorted(pd.Timestamp(start)))
    if first >= len(dates):
        raise ValueError("start is after the last available bar")
    slip = slippage_bps / 10_000.0
    buy_only = bool(getattr(strategy, "buy_only", False))

    tickers = list(closes.columns)
    shares = {t: 0.0 for t in tickers}
    cash = 0.0
    next_deposit = dates[first]
    decided: Weights | None = None  # last target the strategy asked for
    pending: Weights | None = None  # target to execute at the next open
    executed: Weights | None = None  # target currently in force
    trades = 0
    traded = 0.0
    cost = 0.0

    equity, dep_log = {}, {}

    for i in range(first, len(dates)):
        d = dates[i]
        px = opens.iloc[i]

        dep = 0.0
        if d >= next_deposit:
            dep = deposit
            cash += dep
            next_deposit += pd.Timedelta(days=period_days)

        promoted = False
        if buy_only and pending is not None:
            executed, pending, promoted = pending, None, True

        if pending is not None:
            # Rebalance everything to the pending target.
            total = cash + sum(shares[t] * px[t] for t in tickers)
            target_value = {t: total * pending.get(t, 0.0) for t in tickers}
            for t in tickers:  # sells first
                excess = shares[t] * px[t] - target_value[t]
                if excess > 0.01:
                    cash += excess * (1.0 - slip)
                    shares[t] -= excess / px[t]
                    trades += 1
                    traded += excess
                    cost += excess * slip
            wants = {t: target_value[t] - shares[t] * px[t] for t in tickers}
            wants = {t: v for t, v in wants.items() if v > 0.01}
            outlay = sum(wants.values()) * (1.0 + slip)
            scale = min(1.0, cash / outlay) if outlay > 0 else 0.0
            for t, v in wants.items():
                spend = v * scale
                shares[t] += spend / px[t]
                cash -= spend * (1.0 + slip)
                trades += 1
                traded += spend
                cost += spend * slip
            executed, pending = pending, None
        elif (dep or promoted) and executed:
            # No rebalance: spend idle cash on the current target weights.
            avail = cash
            for t, w in executed.items():
                spend = avail * w
                if spend > 0.01:
                    shares[t] += spend / (px[t] * (1.0 + slip))
                    cash -= spend
                    trades += 1
                    traded += spend
                    cost += spend - spend / (1.0 + slip)

        equity[d] = cash + sum(shares[t] * closes.iloc[i][t] for t in tickers)
        dep_log[d] = dep

        if i < len(dates) - 1:
            want = strategy.decide(closes.iloc[: i + 1], decided)
            if want is not None:
                pending = want
                decided = want

    return Result(
        name=strategy.name,
        equity=pd.Series(equity),
        deposits=pd.Series(dep_log),
        trades=trades,
        traded_notional=traded,
        cost_paid=cost,
    )
