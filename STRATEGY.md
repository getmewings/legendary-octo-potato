# Investment Policy Statement

Working draft. Numbers marked **(proposed)** are defaults to confirm or change. Nothing here is personalized financial advice, and no strategy in this repo is guaranteed to beat a plain index fund.

## Situation

- Taxable brokerage account (not an IRA).
- Starting from zero, depositing about **$20 every two weeks**.
- High risk tolerance, long horizon, US stocks only.

## Goal

Grow a portfolio from zero over a long horizon using small recurring deposits. At this size, **how steadily we deposit matters far more than which stocks we pick**: $20 every two weeks is about $520 a year, so even a 5-point edge in returns is a few dollars in the first years. The strategy work here is about not getting in the way of deposits, and learning, not about squeezing out returns.

## What the backtests say

Run `python -m hub.run_backtest` (biweekly deposits, next-open fills, 5 bps per trade, pre-tax, one historical path):

- A 70% index / 30% buy-only sector tilt did **not** beat plain SPY with the same deposits (12.7% vs 13.1% money-weighted return since 2005, and 15.1% vs 15.3% since 2015).
- A top-3 sector momentum portfolio that sells monthly beat SPY by a thin margin before tax (13.4% vs 13.1%), with about 4.5 times the trades. In a taxable account the monthly sales create short-term gains taxed as ordinary income, which likely erases that margin. **Not adopted.**
- A 200-day moving-average trend filter cut the worst drawdown from -55% to -24% but left far less money at the end. **Not adopted.**

Conclusion: there is no demonstrated reason yet to run anything but the index fund. Active ideas stay out until the account is large enough to matter and a journaled experiment shows they add something.

## Structure

**Phase 1 (now): 100% core.** Buy VTI (or another broad US total-market ETF) with every deposit. Fractional shares mean the full $20 is invested each time.

**Phase 2 (proposed trigger: portfolio over $2,000):** optional experiments, each journaled, together capped at 30% of the portfolio.
- Buy-only sector tilt: `python -m hub.plan --deposit N --tilt`. Never sells. Rotating picks only changes where new money goes.
- Discretionary stocks, under the rules below.

Phase 2 is optional. If the experiments do not beat the benchmark over a full year of journal entries, shrink them.

High risk tolerance is expressed through time in the market and the experiment sleeve, never through leverage.

## Hard limits

- **No margin. No options. No short selling.** Revisit only after a year of journaled results.
- **No leveraged or inverse ETFs.**
- Max 5% of the portfolio in any one discretionary stock, measured at cost.
- Max 3 discretionary positions while the portfolio is small.
- Max 1% of the portfolio at risk on any discretionary position (entry to invalidation level, times shares).
- No day trading.
- **Taxable account: do not sell a profitable position held under a year without a reason written in the journal.** Short-term gains are taxed as ordinary income.

## Discretionary position rules (Phase 2)

Every discretionary buy gets an entry in `journal/trades.csv` and a thesis file made from `journal/THESIS_TEMPLATE.md` **before** the order is placed. It must state:

1. Why we own it, in two sentences, and what would make the market wrong about it.
2. A target or a review date.
3. An **invalidation level**: a price or an event at which we sell without further debate.
4. Position size, computed with `hub.sizing.position_size`.

If we cannot fill these in, we do not buy.

## Contributions

- Deposit a fixed amount every two weeks **(set at $20 for now; raise it whenever income allows, since this is the biggest lever)**. Skipping a deposit is a decision that needs a journal entry.
- Each deposit: run `python -m hub.plan --deposit 20`, place the order in the broker app by hand, log it in `journal/trades.csv`.
- No selling to rebalance. Deposits and dividends steer the mix.

## Benchmark

Everything is compared to buying SPY (or VTI) with the same deposits on the same dates. Anything active that cannot beat that after costs and taxes over a full market cycle gets shrunk or dropped.

## Review cadence

- Every deposit: place the order, log it.
- Quarterly: compare actual results to the benchmark, check any discretionary position against its invalidation level.
- Annually: revisit this document. Rule changes are made here, with the reason, and not after a bad week.

## Backtest hygiene

- Signals use the close, orders fill at the next open.
- A cost of 5 bps per trade stands in for spread and slippage.
- Parameters (200-day average, 12-1 momentum, top 3) are common published values and are **not** tuned to this data.
- The universe is a fixed set of long-lived sector ETFs, which avoids single-stock survivorship bias. A universe of today's large stocks would overstate results and is not used.
- Cash earns 0% in the backtest. Taxes are not modeled.
- One historical path is weak evidence. Treat results as a sanity check, not a forecast.

## Taxes (taxable account)

- Short-term gains (held a year or less) are taxed as ordinary income. Long-term gains usually get a lower rate.
- Selling at a loss and rebuying the same or a substantially identical security within 30 days triggers the wash-sale rule.
- Low turnover helps on both counts, which is why the policy is buy-and-hold with buy-only tilts.
- Not tax advice. Confirm with a tax professional.

## Execution

The hub produces order lists. The user places the orders in the broker app by hand. There is no official Robinhood trading API, and unofficial ones require handing over account credentials, so credentials are never stored in this repo or in this environment.
