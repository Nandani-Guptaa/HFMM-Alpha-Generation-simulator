"""
run_realistic.py

Fixes the mistake from Step 7: our earlier real-data tests quoted $0.50 from the
price, while the real Binance BTC/USDT gap between best buy and best sell is
about $0.01 (one tick). This script replays the depth recordings (real order book
+ real trades) and runs the fixed-spread trader and the Avellaneda-Stoikov trader
at many quote distances, from "right at the best price" to 50 ticks back.

"ticks back" = how many ticks behind the best bid/ask our quotes sit.
  0  = we quote exactly at the best price
  50 = about $0.50 away (what we used before)

For each distance it prints fills, total P&L, and the split into
  edge  = gap profit earned at the moment of each fill
  drift = profit/loss from holding Bitcoin while price moved
plus the % of time at the inventory limit.

FILL RULE (new): a resting quote can only be hit ONCE per side per book snapshot.
After that it has to be re-quoted from the next snapshot (~100 ms later). Before this
fix, one stale quote could be filled dozens of times during a fast burst, which is
unrealistic and made the traders pile up inventory at stale prices. Use
--allow-repeat-fills to reproduce the old behaviour.

HONEST LIMITS: at 0-1 ticks back the fill model assumes we are FIRST in the queue
(every trade at our price fills us), which is optimistic. Trade size is not modelled,
there are no fees, and the trader only sees a ~100 ms snapshot of the book, so it
behaves like a SLOW market maker. Treat tight-quote results as rough.

Usage:
    python run_realistic.py
    python run_realistic.py --files depth_1.jsonl depth_2.jsonl
    python run_realistic.py --allow-repeat-fills      # old behaviour, for comparison
"""

import argparse
import json

from avellaneda_stoikov import AvellanedaStoikovMarketMaker
from market_maker import FixedSpreadMarketMaker
from order_book import OrderBook
from replay_feed import Tick
from run_attribution import run_with_attribution

QUOTE_SIZE = 0.01
MAX_INV = 0.1
# distance of our quote from MID in dollars: best price is 0.005 from mid, so
# h = 0.005 + 0.01 * (ticks back)
TICKS_BACK = [0, 1, 4, 10, 25, 50]


class OneFillPerSidePerSnapshot:
    """Wraps a maker so each side can be filled at most once per book snapshot."""

    def __init__(self, maker):
        self._maker = maker
        self._snap = None
        self._done = set()

    def __getattr__(self, name):  # state, quote_size, ... come from the real maker
        return getattr(self._maker, name)

    def on_tick(self, t, book, trade_price, trade_side):
        snap = getattr(book, "snap_id", None)
        if snap != self._snap:
            self._snap = snap
            self._done = set()
        if trade_price is not None and trade_side in self._done:
            return self._maker.on_tick(t, book, None, None)  # already filled this side
        fill = self._maker.on_tick(t, book, trade_price, trade_side)
        if fill is not None:
            self._done.add(trade_side)
        return fill


def replay_depth(path):
    """Yield one Tick per real trade, using the latest real order book snapshot."""
    book = OrderBook()
    have_book = False
    t = 0
    snap = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("type") == "depth":
                book = OrderBook()
                book.apply_snapshot([(p, q) for p, q in r["b"]],
                                    [(p, q) for p, q in r["a"]])
                snap += 1
                book.snap_id = snap
                have_book = True
            elif r.get("type") == "trade" and have_book:
                t += 1
                book.record_trade(r["price"])
                yield Tick(book=book, trade_price=r["price"],
                           trade_side=r["side"], t=t)


# gamma=0.01 was only ever validated at h=0.505 (the old wide setting from Step 5/7).
# diagnose_as_realistic.py showed that holding it fixed as h shrinks makes the inventory
# skew swamp the spread (up to 675% of it at h=0.005). Scaling gamma down with h keeps
# the skew a similar FRACTION of the spread at every distance instead.
GAMMA_REF, H_REF = 0.003, 0.505


def run_one(path, ticks_back, kind, one_fill=True):
    h = 0.005 + 0.01 * ticks_back
    if kind == "fixed":
        maker = FixedSpreadMarketMaker(half_spread=h, quote_size=QUOTE_SIZE,
                                       max_inventory=MAX_INV)
    else:
        gamma = GAMMA_REF * (h / H_REF)
        # k = 1/h makes the A-S base half-spread roughly equal to h
        maker = AvellanedaStoikovMarketMaker(gamma=gamma, k=1.0 / h, horizon_ticks=20,
                                             vol_window=50, quote_size=QUOTE_SIZE,
                                             max_inventory=MAX_INV)
    if one_fill:
        maker = OneFillPerSidePerSnapshot(maker)
    return run_with_attribution(maker, replay_depth(path), MAX_INV)


def main(paths, one_fill=True):
    worst = 0.0
    for path in paths:
        n_trades = sum(1 for _ in replay_depth(path))
        print("=" * 100)
        mode = "one fill per side per snapshot" if one_fill else "repeat fills allowed (old)"
        print(f"FILE: {path}   ({n_trades} real trades replayed)   fill rule: {mode}")
        print("=" * 100)
        print(f"{'ticks':>6} | {'FIXED-SPREAD':^40} | {'AVELLANEDA-STOIKOV':^40}")
        print(f"{'back':>6} | {'fills':>6}{'P&L':>9}{'edge':>9}{'drift':>9}{'cap%':>7} "
              f"| {'fills':>6}{'P&L':>9}{'edge':>9}{'drift':>9}{'cap%':>7}")
        print("-" * 100)
        for tb in TICKS_BACK:
            a = run_one(path, tb, "fixed", one_fill)
            b = run_one(path, tb, "as", one_fill)
            worst = max(worst, abs(a["residual"]), abs(b["residual"]))

            def cells(r):
                return (f"{r['buys'] + r['sells']:>6}{r['total']:>+9.3f}{r['edge']:>+9.3f}"
                        f"{r['inv_pnl']:>+9.3f}{r['pct_at_cap']:>7.1f}")
            print(f"{tb:>6} | {cells(a)} | {cells(b)}")
        print("-" * 100)
    print(f"Check: largest (total - edge - drift) residual = {worst:.1e} (should be ~0)")
    print("All values in dollars. Tight quotes (0-1 ticks back) assume front-of-queue fills: optimistic.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", nargs="+", default=["depth_1.jsonl", "depth_2.jsonl"])
    parser.add_argument("--allow-repeat-fills", action="store_true",
                        help="old behaviour: a stale quote can be filled repeatedly")
    args = parser.parse_args()
    main(args.files, one_fill=not args.allow_repeat_fills)