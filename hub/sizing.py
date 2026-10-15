"""Fractional-share sizing helpers. Pure functions, no network."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Order:
    ticker: str
    dollars: float
    shares: float
    price: float


def _floor(x: float, decimals: int) -> float:
    factor = 10**decimals
    return math.floor(x * factor + 1e-9) / factor


def plan_buys(
    cash: float,
    targets: dict[str, float],
    prices: dict[str, float],
    holdings: dict[str, float] | None = None,
    min_order: float = 1.0,
    decimals: int = 6,
) -> list[Order]:
    """Spend ``cash`` on buys that move the portfolio toward ``targets``.

    Buy-only: nothing is sold, so overweight positions are simply skipped and
    the other gaps are scaled down to fit the cash. Orders under ``min_order``
    dollars are dropped. Weights that sum to less than 1 leave a cash reserve.
    ``holdings`` maps ticker -> shares already owned.
    """
    if cash < 0:
        raise ValueError("cash must be non-negative")
    holdings = holdings or {}
    held_value = {t: holdings.get(t, 0.0) * prices[t] for t in set(holdings) | set(targets) if t in prices}
    total = cash + sum(held_value.values())

    gaps = {
        t: max(w * total - held_value.get(t, 0.0), 0.0)
        for t, w in targets.items()
    }
    gap_sum = sum(gaps.values())
    if gap_sum <= 0 or cash == 0:
        return []
    scale = min(1.0, cash / gap_sum)

    orders = []
    for t, gap in gaps.items():
        dollars = gap * scale
        if dollars < min_order:
            continue
        shares = _floor(dollars / prices[t], decimals)
        if shares <= 0:
            continue
        orders.append(Order(t, round(shares * prices[t], 2), shares, prices[t]))
    return orders


def position_size(
    equity: float,
    risk_pct: float,
    entry: float,
    stop: float,
    max_position_pct: float = 1.0,
    decimals: int = 6,
) -> float:
    """Shares to buy so that hitting ``stop`` loses at most ``risk_pct`` of equity.

    The result is also capped so the position is at most ``max_position_pct`` of equity.
    """
    if stop >= entry:
        raise ValueError("stop must be below entry for a long position")
    if not (0 < risk_pct <= 1 and 0 < max_position_pct <= 1):
        raise ValueError("risk_pct and max_position_pct must be in (0, 1]")
    by_risk = equity * risk_pct / (entry - stop)
    by_cap = equity * max_position_pct / entry
    return _floor(min(by_risk, by_cap), decimals)
