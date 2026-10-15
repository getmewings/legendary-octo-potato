# Investment Policy Statement

Working draft. Numbers marked **(proposed)** are defaults to confirm or change. Nothing here is personalized financial advice, and no strategy in this repo is guaranteed to beat a plain index fund.

## Goal

Grow a portfolio from zero over a long horizon using small recurring deposits. At this account size, **how much and how consistently we deposit matters far more than which stocks we pick** for the first several years. The strategy work is about not getting in the way of that, and adding a modest edge on top.

## Edges we actually control

1. Account type. If eligible, a Roth IRA shelters gains from tax. Retirement-account incentives such as contribution matches change over time, so verify current terms with the broker before relying on them.
2. Costs. Commission-free trading, but spreads and slippage still cost money, so keep turnover low.
3. Every deposit gets invested. Fractional shares mean no cash sits idle waiting for a whole share.
4. Written rules. Decisions are made here, in advance, not in the middle of a drawdown.

## Structure (proposed)

| Sleeve | Target | What it holds | How it is managed |
|---|---|---|---|
| Core | 60% | Broad US total-market ETF (VTI) | Buy on every deposit, never time it |
| Systematic satellite | 30% | Top-3 sector ETFs by 12-1 momentum, equal weight | Rebalance monthly, rules in `hub/strategies.py` |
| Discretionary | 10% | Individual stocks we research | Journaled thesis required, see below |

High risk tolerance is expressed through the satellite and discretionary sleeves (40% in total), not through leverage.

## Hard limits

- **No margin. No options. No short selling** in v1. Revisit only after a year of journaled results.
- **No leveraged or inverse ETFs.**
- Max 5% of the portfolio in any one discretionary stock, measured at cost.
- Max 3 discretionary positions until the portfolio is large enough that 5% is worth the research time.
- Max 1% of the portfolio at risk on any discretionary position (distance from entry to invalidation level, times shares).
- Do not day-trade. Minimum holding period for a discretionary position is until its thesis or invalidation level is hit, not a number of hours.

## Discretionary position rules

Every discretionary buy gets an entry in `journal/trades.csv` and a thesis file made from `journal/THESIS_TEMPLATE.md` **before** the order is placed. It must state:

1. Why we own it, in two sentences, and what would make the market wrong about it.
2. A target or a review date.
3. An **invalidation level**: a price or an event at which we sell without further debate.
4. Position size, computed with `hub.sizing.position_size`.

If we cannot fill these in, we do not buy.

## Contributions and rebalancing

- Deposit a fixed amount every two weeks **(amount to be set, backtests assume $100)**. Skipping a deposit is a decision that needs a journal entry.
- Each deposit buys toward the targets above using `python -m hub.plan --deposit <amount>`. Deposits are buy-only, so they naturally pull the portfolio back toward target without selling.
- Satellite: reselect the top 3 sector ETFs once a month, on the first trading day of the month.
- Full rebalance of all sleeves to target once per year, or when any sleeve is more than 10 percentage points off target. In a taxable account, prefer fixing drift with new deposits to avoid realizing gains.

## Benchmark

Everything is compared to buying SPY (or VTI) with the same deposits on the same dates. If the active sleeves cannot beat that after costs over a full market cycle, we shrink them. `python -m hub.run_backtest` does this comparison for the rules in the repo.

## Review cadence

- Every deposit: run the plan, place the orders, log them.
- Monthly: satellite rebalance, update the journal, check each discretionary position against its invalidation level.
- Quarterly: compare actual results to the benchmark.
- Annually: revisit this document. Changes to rules are made here, with the reason, and not after a bad week.

## Backtest hygiene

- Signals use the close, orders fill at the next open.
- A cost of 5 bps per trade stands in for spread and slippage.
- Parameters (200-day average, 12-1 momentum, top 3) are common published values and are **not** tuned to this data.
- The backtest universe is a fixed set of long-lived sector ETFs, which avoids single-stock survivorship bias. A universe of today's large stocks would overstate results and is not used.
- Cash earns 0% in the backtest, which understates the trend filter when interest rates are high.
- One historical path is weak evidence. Treat results as a sanity check, not a forecast.

## Taxes

- Taxable account: short-term gains are taxed as ordinary income, and selling at a loss then rebuying the same security within 30 days triggers the wash-sale rule. Low turnover helps on both counts.
- Roth IRA: neither applies inside the account. Check contribution limits and eligibility for the tax year.
- Keep this in mind, not as tax advice. Confirm with a tax professional.

## Execution

The hub produces signals and order lists. The user places the orders in the broker app by hand. There is no official Robinhood trading API, and unofficial ones require handing over account credentials, so credentials are never stored in this repo or in this environment.
