"""
run_backtest_live.py

Same logic as run_backtest.py but driven by live Binance data instead of
the synthetic simulator. Run this on your own machine (needs internet
access to stream.binance.com). Stop with Ctrl+C -- it prints results on exit.

Usage:
    pip install -r ../requirements.txt
    python run_backtest_live.py
"""

import asyncio

from adverse_selection import AdverseSelectionTracker
from binance_feed import BinanceFeed
from market_maker import FixedSpreadMarketMaker


async def run(symbol: str = "btcusdt", max_ticks: int = 5000):
    feed = BinanceFeed(symbol=symbol)
    maker = FixedSpreadMarketMaker(half_spread=0.5, quote_size=0.01, max_inventory=0.1)
    adverse_tracker = AdverseSelectionTracker(horizon_ticks=10)
    mtm_history = []

    count = 0
    final_mid = None
    try:
        async for tick in feed.stream():
            mid = tick.book.mid_price()
            if mid is None:
                continue
            final_mid = mid

            adverse_tracker.record_mid(tick.t, mid)

            fill = maker.on_tick(tick.t, tick.book, tick.trade_price, tick.trade_side)
            if fill:
                adverse_tracker.record_fill(fill)

            adverse_tracker.evaluate_ready(tick.t)
            mtm_history.append(maker.state.mark_to_market(mid))

            count += 1
            if count % 200 == 0:
                print(f"[{count} ticks] mid={mid:.2f} inventory={maker.state.inventory:.4f} "
                      f"mtm={maker.state.mark_to_market(mid):.2f}")

            if count >= max_ticks:
                break
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n[Interrupted by user -- printing summary for ticks completed so far]")

    if final_mid is None:
        print("No ticks received before interrupt -- nothing to summarize.")
        return
    mtm = maker.state.mark_to_market(final_mid)
    adverse = adverse_tracker.summary()

    print("=" * 50)
    print(f"LIVE RUN COMPLETE ({symbol}, {count} ticks)")
    print(f"Total fills:        {len(maker.state.fills)}")
    print(f"Final inventory:    {maker.state.inventory:.4f}")
    print(f"Mark-to-market P&L: {mtm:.2f}")
    print(f"Fills evaluated for adverse selection: {adverse.n_fills}")
    print(f"Avg adverse move:   {adverse.avg_adverse_move:.4f}")
    print(f"%% adverse:          {adverse.pct_adverse * 100:.1f}%")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(run())