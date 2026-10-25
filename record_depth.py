"""
record_depth.py

Records Binance BTC/USDT order book DEPTH (top 5 levels each side, ~10 snapshots
per second) together with trades, into a JSON-lines file. Depth is what OFI/VOI
features need; the trades are kept so the maker can be replayed against the same
file later.

Each line is one event:
  {"type": "depth", "ts": ..., "b": [[price, qty] x5], "a": [[price, qty] x5]}
  {"type": "trade", "ts": ..., "price": ..., "qty": ..., "side": "buy"|"sell"}

The file is written as it goes, so Ctrl+C keeps everything recorded so far.

Usage:
    python record_depth.py --snapshots 12000 --out depth_1.jsonl
    (12000 snapshots is roughly 20 minutes)
"""

import argparse
import asyncio
import json
import time

import websockets


def parse_message(raw, levels=5, now=None):
    """Turn one raw websocket message into a compact record (or None to skip)."""
    msg = json.loads(raw)
    stream = msg.get("stream", "")
    data = msg.get("data", msg)
    ts = time.time() if now is None else now

    if "bids" in data and "asks" in data:
        bids = [[float(p), float(q)] for p, q in data["bids"][:levels]]
        asks = [[float(p), float(q)] for p, q in data["asks"][:levels]]
        if len(bids) < levels or len(asks) < levels:
            return None
        return {"type": "depth", "ts": ts, "b": bids, "a": asks}

    if data.get("e") == "aggTrade" or "aggTrade" in stream:
        # "m" true means the buyer was the market maker, i.e. the aggressor SOLD
        side = "sell" if data.get("m") else "buy"
        return {"type": "trade", "ts": ts, "price": float(data["p"]),
                "qty": float(data["q"]), "side": side}
    return None


async def record(symbol, n_snapshots, out_path, levels=5):
    url = (f"wss://stream.binance.com:9443/stream?streams="
           f"{symbol}@depth20@100ms/{symbol}@aggTrade")
    n_depth = n_trades = 0
    print(f"Connecting to Binance for {symbol}...")
    try:
        with open(out_path, "w") as f:
            async with websockets.connect(url) as ws:
                print("Connected -- recording. Ctrl+C stops early and keeps what was saved.")
                async for raw in ws:
                    rec = parse_message(raw, levels)
                    if rec is None:
                        continue
                    f.write(json.dumps(rec) + "\n")
                    if rec["type"] == "depth":
                        n_depth += 1
                        if n_depth % 500 == 0:
                            f.flush()
                            print(f"  {n_depth}/{n_snapshots} snapshots, {n_trades} trades")
                        if n_depth >= n_snapshots:
                            break
                    else:
                        n_trades += 1
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nStopped early.")
    except websockets.exceptions.InvalidHandshake as e:
        print(f"Binance rejected the connection ({e}). HTTP 451 usually means a "
              f"region/VPN block -- change network or VPN and retry.")
    except websockets.exceptions.ConnectionClosed as e:
        print(f"Connection closed by the server: {e}")
    print(f"Saved {n_depth} depth snapshots and {n_trades} trades to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="btcusdt")
    parser.add_argument("--snapshots", type=int, default=12000)
    parser.add_argument("--out", default="depth_1.jsonl")
    args = parser.parse_args()
    asyncio.run(record(args.symbol.lower(), args.snapshots, args.out))
    