"""
signal_maker.py

The Phase 3 trader: uses the order-book imbalance signal (imb1 -- the feature
that survived the robustness checks in ofi_robustness.py on both recordings)
to shift its quotes ahead of the predicted short-term move, instead of only
reacting to its own inventory like Avellaneda-Stoikov does.

imb1 = (best_bid_qty - best_ask_qty) / (best_bid_qty + best_ask_qty)
A positive imb1 (more size waiting to buy) predicted the price would rise over
the next 0.5-2 seconds in both depth_1.jsonl and depth_2.jsonl. So when imb1 is
positive we shift BOTH quotes up: more eager to buy (price about to rise, so
buying is favourable), less eager to sell (selling now would be selling right
before the price rises further).

The skew is expressed as a FRACTION of the quote's own half-spread
(max_skew_frac), not as a separate dollar formula -- this avoids the exact
calibration mistake found in avellaneda_stoikov.py, where a skew formula with
its own scale silently grew to dominate the spread at small h.

    skew = max_skew_frac * half_spread * avg_imb1   (avg_imb1 in [-1, 1])
    bid  = mid - half_spread + skew
    ask  = mid + half_spread + skew
"""

import json
from collections import deque
from dataclasses import dataclass
from typing import Optional

from market_maker import Fill, MarketMakerState
from order_book import OrderBook
from replay_feed import Tick


class SignalMarketMaker:
    """Same on_tick/.state interface as FixedSpreadMarketMaker and
    AvellanedaStoikovMarketMaker, so it drops into the same harness."""

    def __init__(self, half_spread: float, quote_size: float, max_inventory: float,
                max_skew_frac: float = 0.5):
        self.half_spread = half_spread
        self.quote_size = quote_size
        self.max_inventory = max_inventory
        self.max_skew_frac = max_skew_frac
        self.state = MarketMakerState()

    def current_quotes(self, mid_price: float, avg_imb1: float):
        skew = self.max_skew_frac * self.half_spread * avg_imb1
        bid = round(mid_price - self.half_spread + skew, 4)
        ask = round(mid_price + self.half_spread + skew, 4)
        return bid, ask

    def on_tick(self, t: int, book: OrderBook, trade_price: Optional[float],
                trade_side: Optional[str]) -> Optional[Fill]:
        mid = book.mid_price()
        if mid is None or trade_price is None:
            return None
        avg_imb1 = getattr(book, "imb1_avg", 0.0)
        bid, ask = self.current_quotes(mid, avg_imb1)
        fill = None

        if trade_side == "buy" and trade_price >= ask and self.state.inventory - self.quote_size >= -self.max_inventory:
            self.state.inventory -= self.quote_size
            self.state.cash += ask * self.quote_size
            fill = Fill(t=t, side="sell", price=ask, size=self.quote_size, mid_at_fill=mid)
        elif trade_side == "sell" and trade_price <= bid and self.state.inventory + self.quote_size <= self.max_inventory:
            self.state.inventory += self.quote_size
            self.state.cash -= bid * self.quote_size
            fill = Fill(t=t, side="buy", price=bid, size=self.quote_size, mid_at_fill=mid)

        if fill:
            self.state.fills.append(fill)
        return fill


def replay_with_signal(path, window=10):
    """Like run_realistic.replay_depth, but ALSO walks every depth snapshot (not
    just the ones at trade time) to keep a rolling average of imb1, and attaches
    it to each yielded Tick's book as book.imb1_avg, plus book.snap_id for the
    one-fill-per-snapshot rule."""
    book = OrderBook()
    have_book = False
    t = 0
    snap = 0
    imb1_hist = deque(maxlen=window)
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
                bq, aq = r["b"][0][1], r["a"][0][1]
                tot = bq + aq
                imb1_hist.append((bq - aq) / tot if tot > 0 else 0.0)
                have_book = True
            elif r.get("type") == "trade" and have_book:
                t += 1
                book.record_trade(r["price"])
                book.imb1_avg = sum(imb1_hist) / len(imb1_hist) if imb1_hist else 0.0
                yield Tick(book=book, trade_price=r["price"],
                           trade_side=r["side"], t=t)