"""Daily price loading with a small on-disk cache.

Prices are split/dividend adjusted (yfinance ``auto_adjust=True``). Opens are
needed because the backtester fills orders at the next bar's open.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"


@dataclass
class Prices:
    open: pd.DataFrame
    close: pd.DataFrame

    def __post_init__(self) -> None:
        if not self.open.index.equals(self.close.index):
            raise ValueError("open and close must share the same index")
        if list(self.open.columns) != list(self.close.columns):
            raise ValueError("open and close must share the same columns")


def _flatten(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for field in ("Open", "Close"):
        for ticker in df[field].columns:
            out[f"{field}|{ticker}"] = df[field][ticker]
    return out


def _unflatten(flat: pd.DataFrame) -> Prices:
    def pick(field: str) -> pd.DataFrame:
        cols = [c for c in flat.columns if c.startswith(f"{field}|")]
        sub = flat[cols].copy()
        sub.columns = [c.split("|", 1)[1] for c in cols]
        return sub

    return Prices(open=pick("Open"), close=pick("Close"))


def load_prices(
    tickers: list[str],
    start: str,
    end: str | None = None,
    max_age_hours: float = 20.0,
) -> Prices:
    """Fetch (or load from cache) adjusted daily open/close for ``tickers``.

    Rows where any ticker is missing are dropped, so the usable history starts
    at the youngest ticker's first bar.
    """
    tickers = sorted(set(tickers))
    key = hashlib.md5(f"{','.join(tickers)}|{start}|{end}".encode()).hexdigest()[:12]
    path = CACHE_DIR / f"prices_{key}.csv"

    fresh = path.exists() and (time.time() - path.stat().st_mtime) < max_age_hours * 3600
    if fresh:
        flat = pd.read_csv(path, index_col=0, parse_dates=True)
        return _unflatten(flat)

    import yfinance as yf  # imported lazily so tests and sizing work offline

    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    if raw.empty:
        raise RuntimeError(f"No data returned for {tickers}")
    flat = _flatten(raw).dropna(how="any")
    CACHE_DIR.mkdir(exist_ok=True)
    flat.to_csv(path)
    return _unflatten(flat)
