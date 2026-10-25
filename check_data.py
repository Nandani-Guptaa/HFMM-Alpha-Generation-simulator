"""
check_data.py

Data-quality check for the depth recordings (depth_1.jsonl, depth_2.jsonl).

run_realistic.py compares each real trade with the LATEST order book snapshot.
If the book snapshot is old (the depth stream paused or lagged while trades kept
arriving), trades look like they happen far from the price and the simulated
trader gets "run over" for the wrong reason. This script checks for that.

It reports, per file:
  - the gap between consecutive book snapshots (should be ~100 ms)
  - how old the book is at the moment of each trade
  - how far each trade price is from the book's mid price
  - the 5 trades furthest from the mid, and when they happened

Usage:
    python check_data.py
    python check_data.py --files depth_1.jsonl depth_2.jsonl
"""

import argparse
import json


def pct(sorted_vals, p):
    if not sorted_vals:
        return float("nan")
    return sorted_vals[min(len(sorted_vals) - 1, int(p / 100 * len(sorted_vals)))]


def check(path):
    first_ts = last_ts = last_mid = None
    gaps, ages, dists, rows = [], [], [], []
    n_depth = n_trade = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = r["ts"]
            if first_ts is None:
                first_ts = ts
            if r["type"] == "depth":
                n_depth += 1
                if last_ts is not None:
                    gaps.append((ts - last_ts) * 1000)
                last_ts = ts
                last_mid = (r["b"][0][0] + r["a"][0][0]) / 2
            elif r["type"] == "trade" and last_mid is not None:
                n_trade += 1
                age = (ts - last_ts) * 1000
                d = abs(r["price"] - last_mid)
                ages.append(age)
                dists.append(d)
                rows.append((d, age, ts - first_ts, r["price"], last_mid))

    gaps.sort()
    ages.sort()
    dists.sort()
    print("=" * 74)
    print(f"FILE: {path}   depth snapshots={n_depth}   trades={n_trade}")
    print("=" * 74)
    print(f"Gap between book snapshots (ms):  median {pct(gaps, 50):.0f}   "
          f"99th {pct(gaps, 99):.0f}   max {gaps[-1]:.0f}   "
          f"(# gaps over 1s: {sum(1 for g in gaps if g > 1000)})")
    print(f"Book age at each trade (ms):      median {pct(ages, 50):.0f}   "
          f"99th {pct(ages, 99):.0f}   max {ages[-1]:.0f}")
    print(f"Trade price vs book mid ($):      median {pct(dists, 50):.3f}   "
          f"90th {pct(dists, 90):.3f}   99th {pct(dists, 99):.3f}   max {dists[-1]:.2f}")
    print(f"Trades more than $0.50 from mid:  {sum(1 for d in dists if d > 0.5)}   "
          f"more than $5: {sum(1 for d in dists if d > 5)}   (of {len(dists)})")
    print("\nFive trades furthest from the book mid:")
    print(f"  {'secs from start':>16}{'distance $':>12}{'book age ms':>13}{'trade px':>12}{'book mid':>12}")
    for d, age, secs, px, mid in sorted(rows, reverse=True)[:5]:
        print(f"  {secs:>16.1f}{d:>12.2f}{age:>13.0f}{px:>12.2f}{mid:>12.2f}")


def main(paths):
    for p in paths:
        check(p)
    print("\n" + "-" * 74)
    print("Healthy data: snapshot gaps near 100 ms, book age under ~200 ms, and almost")
    print("no trades more than a few cents from the mid. Seconds-long gaps or many trades")
    print("far from the mid mean the book was stale, and the trader results are not trustworthy.")
    print("-" * 74)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", nargs="+", default=["depth_1.jsonl", "depth_2.jsonl"])
    args = parser.parse_args()
    main(args.files)