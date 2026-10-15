"""Monthly review: compare the trade journal to the same cash put into SPY.

    python -m hub.review [--journal journal/trades.csv]

Reads ``date,ticker,side,shares,price,...,fees`` rows, values the holdings at
the latest close, and shows what the same dollars on the same dates would be
worth in SPY. Orders are still placed by hand; this only reads the journal.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .backtest import xirr
from .data import load_prices

BENCHMARK = "SPY"
REQUIRED = ["date", "ticker", "side", "shares", "price"]


def load_trades(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"journal is missing columns: {missing}")
    df = df.dropna(subset=["date"]).copy()
    df["date"] = pd.to_datetime(df["date"])
    df["ticker"] = df["ticker"].str.upper().str.strip()
    df["side"] = df["side"].str.lower().str.strip()
    bad = df[~df["side"].isin(["buy", "sell"])]
    if not bad.empty:
        raise ValueError(f"side must be buy or sell, got: {sorted(set(bad['side']))}")
    df["fees"] = df["fees"].fillna(0.0) if "fees" in df.columns else 0.0
    return df.sort_values("date", kind="stable").reset_index(drop=True)


def cash_flows(trades: pd.DataFrame) -> pd.Series:
    """Signed money put in (+) or taken out (-) of the portfolio, by trade date."""
    gross = trades["shares"] * trades["price"]
    amount = gross.where(trades["side"] == "buy", -gross) + trades["fees"]
    return pd.Series(amount.to_numpy(), index=pd.DatetimeIndex(trades["date"]))


def holdings(trades: pd.DataFrame) -> dict[str, float]:
    signed = trades["shares"].where(trades["side"] == "buy", -trades["shares"])
    net = signed.groupby(trades["ticker"]).sum()
    return {t: float(s) for t, s in net.items() if abs(s) > 1e-9}


def benchmark_shares(flows: pd.Series, bench_open: pd.Series) -> float:
    """Benchmark shares bought with the same dollars at the open on/after each date."""
    total = 0.0
    for date, amount in flows.items():
        pos = bench_open.index.searchsorted(date)
        if pos >= len(bench_open):
            continue  # trade is after the last bar
        total += amount / float(bench_open.iloc[pos])
    return total


def deposit_gaps(trades: pd.DataFrame, max_days: int = 21) -> list[tuple[pd.Timestamp, int]]:
    """Gaps between consecutive buy dates longer than ``max_days`` (a missed deposit or two)."""
    dates = sorted(set(trades.loc[trades["side"] == "buy", "date"]))
    return [(b, (b - a).days) for a, b in zip(dates[:-1], dates[1:]) if (b - a).days > max_days]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--journal", default="journal/trades.csv")
    args = ap.parse_args()

    trades = load_trades(args.journal)
    if trades.empty:
        raise SystemExit("Journal is empty. Add a row to journal/trades.csv after your first buy.")

    held = holdings(trades)
    tickers = sorted({*held, *trades["ticker"], BENCHMARK})
    start = (trades["date"].min() - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
    prices = load_prices(tickers, start=start, max_age_hours=4)
    last = prices.close.iloc[-1]
    end = prices.close.index[-1]

    flows = cash_flows(trades)
    value = sum(sh * float(last[t]) for t, sh in held.items())
    invested = float(flows.sum())  # net money in
    my_irr = xirr(flows, value, end)

    bench_value = benchmark_shares(flows, prices.open[BENCHMARK]) * float(last[BENCHMARK])
    bench_irr = xirr(flows, bench_value, end)

    print(f"Review as of {end.date()} close, {len(trades)} journal rows since {trades['date'].min().date()}\n")
    print(f"Net invested     ${invested:>10,.2f}")
    print(f"Portfolio value  ${value:>10,.2f}   gain ${value - invested:+,.2f}")
    print(f"Same cash in {BENCHMARK}  ${bench_value:>10,.2f}   gain ${bench_value - invested:+,.2f}")
    print(f"You vs {BENCHMARK}: ${value - bench_value:+,.2f}")
    if (end - flows.index.min()).days >= 365:
        print(f"Annualized: you {my_irr:.1%}, {BENCHMARK} {bench_irr:.1%}")
    else:
        print("Annualized returns hidden until there is a year of history; they are not meaningful before then.")

    print("\nHoldings:")
    for t, sh in sorted(held.items(), key=lambda kv: -kv[1] * float(last[kv[0]])):
        print(f"  {t:<6} {sh:>12.6f} sh  ${sh * float(last[t]):>10,.2f}")

    gaps = deposit_gaps(trades)
    days_since = (end - trades["date"].max()).days
    print(f"\nLast trade {days_since} days ago.", end=" ")
    print(f"Gaps over 21 days between buys: {len(gaps)}." if gaps else "No gaps over 21 days between buys.")

    if "review_date" in trades.columns:
        due = trades[(trades["side"] == "buy") & (pd.to_datetime(trades["review_date"], errors="coerce") <= end)]
        due = due[~due["ticker"].isin(["VTI", BENCHMARK])]
        if not due.empty:
            print("\nPositions due for thesis review:")
            for _, r in due.iterrows():
                print(f"  {r['ticker']}  invalidation: {r.get('invalidation', 'n/a')}")
    print("\nSingle-period snapshot, pre-tax. Not advice.")


if __name__ == "__main__":
    main()
