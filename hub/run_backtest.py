"""Run the benchmark and strategies under biweekly deposits.

    python -m hub.run_backtest --start 2005-01-03 --deposit 20
"""

from __future__ import annotations

import argparse

import pandas as pd

from .backtest import run_backtest
from .data import load_prices
from .strategies import BuyAndHold, CoreSectorTilt, SectorMomentum, TrendFilter

WARMUP_DAYS = 450  # calendar days of history fetched before --start


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2005-01-03")
    ap.add_argument("--end", default=None)
    ap.add_argument("--deposit", type=float, default=20.0)
    ap.add_argument("--period-days", type=int, default=14)
    ap.add_argument("--slippage-bps", type=float, default=5.0)
    args = ap.parse_args()

    strategies = [BuyAndHold("SPY"), CoreSectorTilt("SPY", 0.7), SectorMomentum(), TrendFilter("SPY", 200)]
    tickers = sorted({t for s in strategies for t in s.tickers})
    fetch_from = (pd.Timestamp(args.start) - pd.Timedelta(days=WARMUP_DAYS)).strftime("%Y-%m-%d")
    prices = load_prices(tickers, start=fetch_from, end=args.end)

    rows = []
    for s in strategies:
        r = run_backtest(s, prices, args.start, args.deposit, args.period_days, args.slippage_bps)
        rows.append(
            {
                "strategy": r.name,
                "contributed": r.contributed,
                "ending": r.ending_value,
                "xirr": r.xirr(),
                "twr_cagr": r.twr_cagr(),
                "max_dd": r.max_drawdown(),
                "trades": r.trades,
                "cost_paid": r.cost_paid,
            }
        )
    df = pd.DataFrame(rows).set_index("strategy")
    fmt = {
        "contributed": "${:,.0f}".format,
        "ending": "${:,.0f}".format,
        "xirr": "{:.1%}".format,
        "twr_cagr": "{:.1%}".format,
        "max_dd": "{:.1%}".format,
        "cost_paid": "${:,.0f}".format,
    }
    print(f"Data: {prices.close.index[0].date()} to {prices.close.index[-1].date()}, "
          f"backtest from {args.start}, ${args.deposit:,.0f} every {args.period_days} days, "
          f"{args.slippage_bps:g} bps per trade")
    print(df.to_string(formatters=fmt))
    print("\nSingle-period result. Past returns do not predict future returns.")
    print("Sector ETFs avoid single-stock survivorship bias but not look-back bias in choosing these ideas.")


if __name__ == "__main__":
    main()
