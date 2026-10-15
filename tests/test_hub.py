import numpy as np
import pandas as pd
import pytest

from hub.backtest import run_backtest, xirr
from hub.data import Prices
from hub.sizing import plan_buys, position_size
from hub.strategies import BuyAndHold, SectorMomentum, TrendFilter, momentum_ranking, satellite_picks


def make_prices(open_, close=None, start="2020-01-01"):
    idx = pd.bdate_range(start, periods=len(next(iter(open_.values()))))
    o = pd.DataFrame(open_, index=idx, dtype=float)
    c = pd.DataFrame(close if close is not None else open_, index=idx, dtype=float)
    return Prices(open=o, close=c)


# ---- sizing -------------------------------------------------------------

def test_plan_buys_splits_cash_by_target():
    orders = plan_buys(100.0, {"A": 0.6, "B": 0.4}, {"A": 50.0, "B": 20.0})
    by = {o.ticker: o for o in orders}
    assert by["A"].shares == pytest.approx(1.2)
    assert by["B"].shares == pytest.approx(2.0)
    assert sum(o.dollars for o in orders) == pytest.approx(100.0)


def test_plan_buys_skips_overweight_and_scales_others():
    # A is already 80% of value; only B and C get money, scaled to the cash on hand.
    orders = plan_buys(
        10.0, {"A": 0.4, "B": 0.3, "C": 0.3}, {"A": 10.0, "B": 10.0, "C": 10.0}, holdings={"A": 8.0}
    )
    by = {o.ticker: o for o in orders}
    assert "A" not in by
    assert sum(o.dollars for o in orders) == pytest.approx(10.0, abs=0.01)
    assert by["B"].dollars == pytest.approx(by["C"].dollars)


def test_plan_buys_drops_tiny_orders_and_keeps_reserve():
    orders = plan_buys(100.0, {"A": 0.995, "B": 0.005}, {"A": 10.0, "B": 10.0})
    assert [o.ticker for o in orders] == ["A"]
    # weights sum to 1.0 here, but a sub-$1 order for B is dropped, leaving cash unspent
    assert orders[0].dollars < 100.0


def test_plan_buys_never_overspends():
    orders = plan_buys(33.33, {"A": 1 / 3, "B": 1 / 3, "C": 1 / 3}, {"A": 7.0, "B": 13.0, "C": 3.0})
    assert sum(o.shares * o.price for o in orders) <= 33.33 + 1e-9


def test_position_size_by_risk_and_by_cap():
    # Risk 1% of 10k = $100; $5 risk per share -> 20 shares.
    assert position_size(10_000, 0.01, entry=50.0, stop=45.0) == 20.0
    # Cap at 5% of equity = $500 = 10 shares, tighter than the risk limit.
    assert position_size(10_000, 0.01, entry=50.0, stop=45.0, max_position_pct=0.05) == 10.0
    with pytest.raises(ValueError):
        position_size(10_000, 0.01, entry=50.0, stop=55.0)


# ---- backtester ---------------------------------------------------------

def test_flat_prices_no_slippage_equity_equals_deposits():
    n = 60
    p = make_prices({"X": [100.0] * n})
    r = run_backtest(BuyAndHold("X"), p, "2020-01-01", deposit=100.0, slippage_bps=0.0)
    assert r.equity.iloc[-1] == pytest.approx(r.contributed)
    # ~84 calendar days of data -> deposits on day 0, 14, 28, ... (first trading day on/after due date)
    assert r.contributed == 100.0 * (r.deposits > 0).sum()
    assert (r.deposits > 0).sum() >= 6


def test_deposit_schedule_is_biweekly():
    p = make_prices({"X": [100.0] * 90})
    r = run_backtest(BuyAndHold("X"), p, "2020-01-01", deposit=50.0, slippage_bps=0.0)
    dates = r.deposits[r.deposits > 0].index
    gaps = [(b - a).days for a, b in zip(dates[:-1], dates[1:])]
    assert all(14 <= g <= 16 for g in gaps)


def test_signal_on_close_fills_at_next_open():
    # Close at day 0 is 100 but the next open is 200: fill must be at 200.
    n = 5
    opens = [100.0, 200.0, 200.0, 200.0, 200.0]
    closes = [100.0, 200.0, 200.0, 200.0, 200.0]
    p = make_prices({"X": opens}, {"X": closes})
    r = run_backtest(BuyAndHold("X"), p, "2020-01-01", deposit=100.0, slippage_bps=0.0)
    # $100 deposited day 0 sat in cash at open, strategy decides at day-0 close, fills day-1 open at 200.
    # Shares = 0.5, valued at 200 close -> $100 (no gain from the 100 -> 200 jump).
    assert r.equity.iloc[-1] == pytest.approx(100.0)


def test_strategy_only_sees_history_through_current_bar():
    seen = []

    class Spy:
        name = "spy"
        tickers = ["X"]

        def decide(self, history, current):
            seen.append(len(history))
            return None

    p = make_prices({"X": [100.0] * 10})
    run_backtest(Spy(), p, "2020-01-01", slippage_bps=0.0)
    assert seen == list(range(1, 10))  # one call per bar, history length grows by one, none on the last bar


def test_start_date_leaves_warmup_history_uninvested():
    p = make_prices({"X": [100.0] * 30})
    start = p.close.index[10]
    r = run_backtest(BuyAndHold("X"), p, str(start.date()), slippage_bps=0.0)
    assert r.equity.index[0] == start
    assert r.deposits.iloc[0] == 100.0


def test_slippage_reduces_ending_value():
    p = make_prices({"X": [100.0] * 60})
    free = run_backtest(BuyAndHold("X"), p, "2020-01-01", slippage_bps=0.0)
    costly = run_backtest(BuyAndHold("X"), p, "2020-01-01", slippage_bps=50.0)
    assert costly.ending_value < free.ending_value
    assert costly.cost_paid > 0


def test_trend_filter_goes_to_cash_when_below_sma():
    # Rising then crashing: after the crash the strategy should exit and stop losing.
    up = list(np.linspace(100, 200, 250))
    down = list(np.linspace(200, 100, 100))
    p = make_prices({"X": up + down})
    trend = run_backtest(TrendFilter("X", 200), p, "2020-01-01", slippage_bps=0.0)
    hold = run_backtest(BuyAndHold("X"), p, "2020-01-01", slippage_bps=0.0)
    assert trend.max_drawdown() > hold.max_drawdown()  # shallower (less negative) drawdown


def test_xirr_known_case():
    # $100 invested, worth $110 exactly one year later -> 10%.
    dep = pd.Series([100.0], index=[pd.Timestamp("2020-01-01")])
    assert xirr(dep, 110.0, pd.Timestamp("2021-01-01")) == pytest.approx(0.10, abs=0.002)


def test_twr_ignores_deposit_size():
    # Price doubles; return should be ~100% no matter when money was added.
    n = 50
    close = list(np.linspace(100, 200, n))
    p = make_prices({"X": close})
    r = run_backtest(BuyAndHold("X"), p, "2020-01-01", deposit=100.0, slippage_bps=0.0)
    assert r.twr_index().iloc[-1] == pytest.approx(2.0, rel=0.05)


# ---- strategies ---------------------------------------------------------

def test_momentum_ranking_skips_recent_month():
    # B surged in the last 21 bars; 12-1 momentum must ignore that.
    n = 300
    a = np.linspace(100, 200, n)
    b = np.concatenate([np.linspace(100, 120, n - 21), np.linspace(120, 400, 21)])
    hist = pd.DataFrame({"A": a, "B": b})
    ranking = momentum_ranking(hist)
    assert ranking.index[0] == "A"


def test_satellite_picks_are_anchored_to_first_bar_of_month():
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2019-01-01", periods=500)
    names = ["A", "B", "C", "D", "E", "F"]
    closes = pd.DataFrame(
        100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, (500, 6)), axis=0)), index=idx, columns=names
    )
    month = idx[-1]
    in_month = [d for d in idx if (d.year, d.month) == (month.year, month.month)]
    anchor = satellite_picks(closes, names, 3, as_of=in_month[0])
    assert len(in_month) > 5
    for d in in_month:
        assert satellite_picks(closes, names, 3, as_of=d) == anchor
    assert satellite_picks(closes, names, 3) == anchor
    # and it matches what the strategy itself decides on that first bar
    s = SectorMomentum(universe=names, top_n=3)
    first_pos = idx.get_loc(in_month[0])
    decided = s.decide(closes.iloc[: first_pos + 1], None)
    assert set(decided) == set(anchor)


def test_sector_momentum_only_rebalances_on_first_bar_of_month():
    idx = pd.bdate_range("2019-01-01", periods=400)
    hist = pd.DataFrame({t: np.linspace(100, 100 + i * 10, 400) for i, t in enumerate(["A", "B", "C", "D"])}, index=idx)
    s = SectorMomentum(universe=["A", "B", "C", "D"], top_n=2)
    results = [s.decide(hist.iloc[: i + 1], None) for i in range(260, 400)]
    fired = [i + 260 for i, r in enumerate(results) if r is not None]
    assert fired
    for i in fired:
        assert idx[i].month != idx[i - 1].month
    first = results[fired[0] - 260]
    assert set(first) == {"D", "C"}
    assert sum(first.values()) == pytest.approx(1.0)


def test_buy_only_strategy_never_sells_and_deploys_all_cash():
    class Flip:
        """Switches target from A to B mid-way; buy_only means A must never shrink."""

        name = "flip"
        tickers = ["A", "B"]
        buy_only = True

        def decide(self, history, current):
            if len(history) == 1:
                return {"A": 1.0}
            if len(history) == 30:
                return {"B": 1.0}
            return None

    p = make_prices({"A": [100.0] * 80, "B": [50.0] * 80})
    r = run_backtest(Flip(), p, "2020-01-01", deposit=100.0, slippage_bps=0.0)
    # Flat prices, no slippage: nothing lost, nothing left idle after the first targets exist.
    assert r.equity.iloc[-1] == pytest.approx(r.contributed)
    assert r.traded_notional == pytest.approx(r.contributed - 100.0, abs=100.0)  # only deposits were traded
    assert r.cost_paid == 0.0


def test_core_sector_tilt_splits_deposits_and_never_sells():
    from hub.strategies import CoreSectorTilt

    rng = np.random.default_rng(1)
    idx = pd.bdate_range("2019-01-01", periods=600)
    names = ["A", "B", "C", "D", "E"]
    closes = pd.DataFrame(
        100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, (600, 6)), axis=0)),
        index=idx,
        columns=["CORE", *names],
    )
    p = Prices(open=closes.copy(), close=closes)
    s = CoreSectorTilt("CORE", 0.7, universe=names, top_n=2)
    w = s.decide(closes.iloc[:400], None)
    assert w["CORE"] == pytest.approx(0.7)
    assert sum(w.values()) == pytest.approx(1.0)
    assert len(w) == 3
    r = run_backtest(s, p, str(idx[300].date()), deposit=20.0, slippage_bps=10.0)
    # Buy-only: every traded dollar is a deposit dollar. Any sale would push this above contributed.
    assert r.traded_notional == pytest.approx(r.contributed, rel=1e-6)
    assert r.cost_paid > 0
