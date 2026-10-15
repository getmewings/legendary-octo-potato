# Investing hub

Policy, journal, backtests and sizing for a small portfolio built with recurring deposits. See `STRATEGY.md` for the rules.

```
pip install -r requirements.txt
python -m pytest                                # tests, offline
python -m hub.run_backtest --deposit 100        # benchmark vs strategies, biweekly deposits
python -m hub.plan --deposit 100                # today's signals and buy list
```

- `STRATEGY.md`: investment policy statement
- `journal/trades.csv`, `journal/THESIS_TEMPLATE.md`: record every trade and the reason for it
- `hub/`: data fetch with cache, contribution-aware backtester, strategies, fractional-share sizing

Orders are placed by hand. No brokerage credentials belong in this repo.
