# HFMM Alpha Generation Simulator

A Python paper-trading simulator for a Bitcoin market-making strategy, built and
tested on live and recorded Binance BTC/USDT data. Real prices, fake money,
honest results — including the strategies that didn't work.

## What this is

A market maker continuously quotes a buy price and a sell price a little apart,
profiting from the gap. The risk isn't bad trades — it's holding inventory while
the market moves against you. This project builds that trader, tests it
honestly against real Bitcoin data, and looks for a signal that predicts
short-term price moves well enough to help.

## Results summary

| Strategy | depth_1.jsonl P&L | depth_2.jsonl P&L | Notes |
|---|---|---|---|
| Fixed-spread (baseline) | -$24.73 | -$0.37 | Naive, same spread always |
| Avellaneda-Stoikov | -$29.75 | -$0.70 | Textbook inventory-aware quoting — **did not beat the baseline** |
| Signal-driven (window=5, skew=1.0) | **-$9.19** | **+$4.03** | Uses order-book imbalance to lean quotes ahead of predicted moves |

All three use realistic $0.01-scale quote distances and a one-fill-per-snapshot
rule (see Limitations). Full parameter sweep in `run_signal.py`'s output.

## The story, briefly

1. **Fixed-spread baseline** loses money on real data — confirmed with a P&L
   attribution showing the loss is almost entirely from holding inventory while
   price drifts, not from bad individual trades.
2. **Avellaneda-Stoikov**, the standard "inventory-aware" improvement, was
   tested at first with a $0.50 quote distance carried over by mistake from a
   synthetic calibration — real BTC/USDT trades at a $0.01 tick. Redone at
   realistic distances, two further bugs were found and fixed (a stale quote
   being filled repeatedly during fast bursts, and an inventory-skew term that
   had grown to 6-7x the size of its own spread). With both fixed, the honest
   result holds on two separate recordings: **A-S does not beat the simple
   strategy on real data, and usually does worse.**
3. **Order-book imbalance (`imb1`)** was tested as a predictor of short-term
   price moves on two independent recordings, with several robustness checks
   (controlling for recent momentum, comparing against randomly shifted data).
   It's a small, real, short-horizon signal — not usable for a few seconds out.
4. **A signal-driven trader** was built to use `imb1` directly, and tested
   across 9 parameter combinations. One setting (`window=5, skew=1.0`)
   improved *both* recordings without either file's P&L collapsing into a pure
   directional bet — the setting chosen deliberately over higher-P&L settings
   that only worked on one file.

## Repo structure

```
src/
  order_book.py          # L2 order book data structure
  simulate_feed.py        # synthetic order flow (for offline testing)
  binance_feed.py         # live Binance WebSocket feed
  market_maker.py          # fixed-spread baseline trader
  avellaneda_stoikov.py    # Avellaneda-Stoikov trader
  signal_maker.py           # signal-driven trader (order-imbalance skew)
  adverse_selection.py      # post-fill adverse-selection tracking
  run_attribution.py         # splits P&L into edge (spread) vs drift (inventory)
  record_live_ticks.py / record_depth.py   # record real Binance data to file
  replay_feed.py / run_realistic.py / signal_maker.replay_with_signal
                              # replay recordings through the traders
  run_backtest.py / run_backtest_live.py   # synthetic / live quick tests
  run_comparison.py / run_comparison_live.py / run_realistic.py / run_signal.py
                              # head-to-head comparisons at various stages
  ofi_signal_test.py / ofi_robustness.py    # signal predictive-power tests
  check_data.py / diagnose_as.py / diagnose_as_realistic.py
                              # diagnostics used to catch the bugs above
```

## Running it

```bash
pip install -r requirements.txt

# Quick synthetic test (no internet needed)
python src/run_backtest.py

# Record real data (needs internet)
python src/record_depth.py --snapshots 12000 --out depth_1.jsonl

# Signal predictive-power test
python src/ofi_signal_test.py --file depth_1.jsonl --holdout depth_2.jsonl

# Full strategy comparison on real data
python src/run_realistic.py
python src/run_signal.py
```

## Limitations (read before trusting any number here)

- **No trading fees.** Spread-capture profits are on the order of cents;
  real exchange fees would likely exceed them.
- **Simplified fills.** At tight quote distances the simulation assumes
  front-of-queue execution — optimistic compared to a real exchange queue.
- **Two real recordings, one asset.** The signal-driven result generalized
  across both, but a third, independent recording (not used for tuning) is
  the next honest validation step before treating this as settled.
- **No queue position, no partial fills, no latency modeling.**

This project is a research exercise in honest strategy testing, not a
production trading system.
