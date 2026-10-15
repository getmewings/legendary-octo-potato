"""Print today's signals and an order list for the next deposit.

    python -m hub.plan --deposit 100 [--holdings holdings.csv]

holdings.csv has two columns, ``ticker,shares``. The hub never talks to a
brokerage; you place the orders yourself.

Order list follows the backtested rule: sector ETFs held but not in this
month's picks are sold, then the deposit plus proceeds buy toward targets.
"""

from __future__ import annotations

import argparse
import csv

import pandas as pd

from .data import load_prices
from .sizing import plan_buys
from .strategies import SECTOR_ETFS, momentum_ranking, satellite_picks

# Policy targets, see STRATEGY.md.
CORE_TICKER = "VTI"
SATELLITE_WEIGHT = 0.30
DISCRETIONARY_CAP = 0.10
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

    holdings = read_holdings(args.holdings)
    discretionary = [t for t in holdings if t != CORE_TICKER and t not in SECTOR_ETFS]
    tickers = [CORE_TICKER, *SECTOR_ETFS, *discretionary]
    start = (pd.Timestamp.today() - pd.Timedelta(days=500)).strftime("%Y-%m-%d")
    prices = load_prices(tickers, start=start, max_age_hours=4)
    closes = prices.close
    last = closes.iloc[-1].to_dict()
    print(f"Prices as of {closes.index[-1].date()} close")

    picks = satellite_picks(closes, SECTOR_ETFS, TOP_N)
    ranking = momentum_ranking(closes[SECTOR_ETFS])
    print("\nSector 12-1 momentum, as of today (picks are set from the month's first trading day):")
    for t, r in ranking.items():
        print(f"  {t}  {r:+.1%}{'  <- hold this month' if t in picks else ''}")

    sells = {t: sh for t, sh in holdings.items() if t in SECTOR_ETFS and t not in picks and sh > 0}
    proceeds = sum(sh * last[t] for t, sh in sells.items())
    kept = {t: sh for t, sh in holdings.items() if t not in sells}
    cash = args.deposit + proceeds

    total = cash + sum(sh * last[t] for t, sh in kept.items())
    disc_weight = min(sum(kept[t] * last[t] for t in discretionary) / total, DISCRETIONARY_CAP)
    # While the discretionary sleeve is unfilled, its share goes to core.
    targets = {CORE_TICKER: 1.0 - SATELLITE_WEIGHT - disc_weight}
    targets.update({t: SATELLITE_WEIGHT / TOP_N for t in picks})

    print("\nOrders (verify the broker's minimum fractional order size):")
    for t, sh in sells.items():
        print(f"  SELL {t}  {sh:.4f} sh @ {last[t]:,.2f}  (~${sh * last[t]:,.2f}, not in this month's picks)")
    buys = plan_buys(cash, targets, last, kept)
    for o in buys:
        print(f"  BUY  {o.ticker}  ${o.dollars:,.2f}  ~{o.shares:.4f} sh @ {o.price:,.2f}")
    print(f"\nCash to deploy: ${cash:,.2f}. Unallocated after these orders: ${max(cash - sum(o.dollars for o in buys), 0.0):,.2f}")
    print("Taxable account: each SELL realizes a gain or loss, see STRATEGY.md. Not advice.")


if __name__ == "__main__":
    main()
