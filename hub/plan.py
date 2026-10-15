"""Print today's signals and a buy list for the next deposit.

    python -m hub.plan --deposit 100 [--holdings holdings.csv]

holdings.csv has two columns, ``ticker,shares``. The hub never talks to a
brokerage; you place the orders yourself.
"""

from __future__ import annotations

import argparse
import csv

import pandas as pd

from .data import load_prices
from .sizing import plan_buys
from .strategies import SECTOR_ETFS, momentum_ranking

# Policy targets, see STRATEGY.md. The remaining 10% is the discretionary sleeve.
CORE_TICKER = "VTI"
CORE_WEIGHT = 0.60
SATELLITE_WEIGHT = 0.30
TOP_N = 3


def read_holdings(path: str | None) -> dict[str, float]:
    if not path:
        return {}
    with open(path, newline="") as f:
        return {row["ticker"].upper(): float(row["shares"]) for row in csv.DictReader(f)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--deposit", type=float, required=True)
    ap.add_argument("--holdings", default=None)
    args = ap.parse_args()

    tickers = [CORE_TICKER, *SECTOR_ETFS]
    start = (pd.Timestamp.today() - pd.Timedelta(days=500)).strftime("%Y-%m-%d")
    prices = load_prices(tickers, start=start, max_age_hours=4)
    closes = prices.close
    last = closes.iloc[-1]
    print(f"Prices as of {closes.index[-1].date()} close")

    ranking = momentum_ranking(closes[SECTOR_ETFS])
    if ranking.empty:
        raise SystemExit("Not enough history for 12-1 momentum")
    picks = list(ranking.index[:TOP_N])
    print("\nSector 12-1 momentum (best first):")
    for t, r in ranking.items():
        print(f"  {t}  {r:+.1%}{'  <- hold' if t in picks else ''}")

    targets = {CORE_TICKER: CORE_WEIGHT, **{t: SATELLITE_WEIGHT / TOP_N for t in picks}}
    holdings = read_holdings(args.holdings)
    orders = plan_buys(args.deposit, targets, last.to_dict(), holdings)

    print(f"\nBuy plan for ${args.deposit:,.2f} (buy-only; verify minimum order size with your broker):")
    for o in orders:
        print(f"  BUY {o.ticker}  ${o.dollars:,.2f}  ~{o.shares:.4f} sh @ {o.price:,.2f}")
    stale = [t for t in holdings if t not in targets]
    if stale:
        print(f"\nHeld but no longer in targets (review at monthly rebalance, not necessarily sell): {', '.join(stale)}")
    print("\nNot advice. Orders are yours to place and verify.")


if __name__ == "__main__":
    main()
