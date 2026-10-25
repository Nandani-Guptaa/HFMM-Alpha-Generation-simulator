"""
replay_feed.py

Reads a JSON file produced by record_live_ticks.py and replays it as a
sequence of Tick objects with the SAME shape simulate_feed.py produces --
so the exact same maker code (FixedSpreadMarketMaker, AvellanedaStoikovMarketMaker)
runs unmodified against recorded real data.

We only recorded mid-price + trade info (not full book depth), so we
reconstruct a minimal single-level OrderBook snapshot around each recorded
mid -- sufficient because our makers only ever call book.mid_price(),
never the deeper book levels. If you later build OFI/VOI features that need
real depth, you'll need to record full depth snapshots instead (extend
record_live_ticks.py's _handle_depth capture accordingly).
"""

import json
from dataclasses import dataclass
from typing import Iterator, Optional

from order_book import OrderBook


@dataclass
class Tick:
    book: OrderBook
    trade_price: Optional[float]
    trade_side: Optional[str]
    t: int


def replay(path: str) -> Iterator[Tick]:
    with open(path) as f:
        records = json.load(f)

    for r in records:
        mid = r["mid"]
        book = OrderBook()
        # Reconstruct a minimal single-level book centered on the recorded mid.
        # The 0.5 offset is arbitrary -- it only needs to make mid_price() correct;
        # our makers don't read deeper book levels.
        book.apply_snapshot(bids=[(mid - 0.5, 1.0)], asks=[(mid + 0.5, 1.0)])
        if r["trade_price"] is not None:
            book.record_trade(r["trade_price"])
        yield Tick(book=book, trade_price=r["trade_price"], trade_side=r["trade_side"], t=r["t"])