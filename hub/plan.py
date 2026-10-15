"""Print the order list for the next deposit.

    python -m hub.plan --deposit 20            # core fund only (current policy)
    python -m hub.plan --deposit 20 --tilt     # optional buy-only sector tilt

The hub never talks to a brokerage; you place the orders yourself. Nothing is
ever sold here: a tilt only changes how new money is split.
"""

from __future__ import annotations

import argparse

import pandas as pd

from .data import load_prices
from .sizing import plan_buys
from .strategies import SECTOR_ETFS, momentum_ranking, satellite_picks

CORE_TICKER = "VTI"
TILT_CORE_WEIGHT = 0.70
TOP_N = 3


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--deposit", type=float, required=True)
    ap.add_argument("--tilt", action="store_true", help="split 30%% of the deposit across the top-3 sector ETFs")
    args = ap.parse_args()

    targets = {CORE_TICKER: 1.0}
    tickers = [CORE_TICKER]
    if args.tilt:
        tickers += SECTOR_ETFS
    start = (pd.Timestamp.today() - pd.Timedelta(days=500)).strftime("%Y-%m-%d")
    prices = load_prices(tickers, start=start, max_age_hours=4)
    closes = prices.close
    last = closes.iloc[-1].to_dict()
    print(f"Prices as of {closes.index[-1].date()} close")

    if args.tilt:
        picks = satellite_picks(closes, SECTOR_ETFS, TOP_N)
        print("\nSector 12-1 momentum (picks are set from the month's first trading day):")
        for t, r in momentum_ranking(closes[SECTOR_ETFS]).items():
            print(f"  {t}  {r:+.1%}{'  <- this month' if t in picks else ''}")
        targets = {CORE_TICKER: TILT_CORE_WEIGHT}
        targets.update({t: (1.0 - TILT_CORE_WEIGHT) / TOP_N for t in picks})

    orders = plan_buys(args.deposit, targets, last)
    print(f"\nBuy ${args.deposit:,.2f} (verify the broker's minimum fractional order size):")
    for o in orders:
        print(f"  BUY  {o.ticker}  ${o.dollars:,.2f}  ~{o.shares:.4f} sh @ {o.price:,.2f}")
    print(f"Unallocated: ${max(args.deposit - sum(o.dollars for o in orders), 0.0):,.2f}. Not advice.")


if __name__ == "__main__":
    main()
