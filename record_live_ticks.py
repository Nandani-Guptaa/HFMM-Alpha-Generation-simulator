"""
record_live_ticks.py

Connects to Binance and records a sequence of real market ticks (mid-price,
trade price, trade side) to a JSON file. This recording can then be
REPLAYED identically into multiple makers (see replay_feed.py and
run_comparison_live.py) for a fair before/after comparison on real data --
something you can't do with a live stream directly, since you can't rewind
it to give a second maker the exact same market.

Run this on your own machine (needs internet access to Binance).

Usage:
    python record_live_ticks.py --ticks 3000 --symbol btcusdt --out recorded_ticks.json
    (or just: python record_live_ticks.py   -- uses sensible defaults)
"""

import argparse
import asyncio
import json

from binance_feed import BinanceFeed


async def record(symbol: str, n_ticks: int, out_path: str):
    feed = BinanceFeed(symbol=symbol)
    recorded = []

    print(f"Recording {n_ticks} ticks from {symbol}... (Ctrl+C to stop early)")
    try:
        async for tick in feed.stream():
            mid = tick.book.mid_price()
            if mid is None:
                continue
            recorded.append({
                "t": tick.t,
                "mid": mid,
                "trade_price": tick.trade_price,
                "trade_side": tick.trade_side,
            })
            if len(recorded) % 200 == 0:
                print(f"  recorded {len(recorded)} ticks...")
            if len(recorded) >= n_ticks:
                break
    except KeyboardInterrupt:
        print(f"\nStopped early with {len(recorded)} ticks recorded.")

    with open(out_path, "w") as f:
        json.dump(recorded, f)

    print(f"Saved {len(recorded)} ticks to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="btcusdt")
    parser.add_argument("--ticks", type=int, default=3000)
    parser.add_argument("--out", default="recorded_ticks.json")
    args = parser.parse_args()

    asyncio.run(record(args.symbol, args.ticks, args.out))