"""
order_book.py

Maintains a live L2 order book (price -> size) for bids and asks.
Works identically whether updates come from a real exchange feed
(Binance depth stream) or a synthetic simulator -- both just call
apply_snapshot() / apply_update().

This is the foundation every other module reads from.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class OrderBook:
    # price -> size, kept sorted on read (not on every insert -- cheaper)
    bids: Dict[float, float] = field(default_factory=dict)
    asks: Dict[float, float] = field(default_factory=dict)
    last_trade_price: float = None
    last_update_id: int = 0

    def apply_update(self, side: str, price: float, size: float) -> None:
        """
        Apply a single price-level update.
        size == 0 means the level is removed (standard exchange convention).
        side: 'bid' or 'ask'
        """
        book = self.bids if side == "bid" else self.asks
        if size <= 0:
            book.pop(price, None)
        else:
            book[price] = size

    def apply_snapshot(self, bids: List[Tuple[float, float]], asks: List[Tuple[float, float]]) -> None:
        """Replace the book wholesale (used for initial snapshot or simulator resets)."""
        self.bids = {p: s for p, s in bids if s > 0}
        self.asks = {p: s for p, s in asks if s > 0}

    def best_bid(self) -> Tuple[float, float]:
        if not self.bids:
            return None, 0.0
        p = max(self.bids)
        return p, self.bids[p]

    def best_ask(self) -> Tuple[float, float]:
        if not self.asks:
            return None, 0.0
        p = min(self.asks)
        return p, self.asks[p]

    def mid_price(self) -> float:
        bb, _ = self.best_bid()
        ba, _ = self.best_ask()
        if bb is None or ba is None:
            return None
        return (bb + ba) / 2.0

    def spread(self) -> float:
        bb, _ = self.best_bid()
        ba, _ = self.best_ask()
        if bb is None or ba is None:
            return None
        return ba - bb

    def top_n(self, n: int = 5) -> Dict[str, List[Tuple[float, float]]]:
        """Return top-n levels each side, sorted best-first. Useful for OFI/VOI later."""
        sorted_bids = sorted(self.bids.items(), key=lambda x: -x[0])[:n]
        sorted_asks = sorted(self.asks.items(), key=lambda x: x[0])[:n]
        return {"bids": sorted_bids, "asks": sorted_asks}

    def record_trade(self, price: float) -> None:
        self.last_trade_price = price
