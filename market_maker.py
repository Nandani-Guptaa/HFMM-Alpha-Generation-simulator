"""
market_maker.py

Phase 1 baseline: a market maker that quotes a FIXED spread around mid-price,
gets filled when trades cross its quotes, and tracks inventory + P&L.

This is deliberately simple. It exists to be the baseline you compare
everything else against later (Avellaneda-Stoikov, OFI/VOI signals, etc.).
Do not skip building this properly -- without a working, trusted baseline,
you can't prove any "improvement" actually improves anything.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from order_book import OrderBook


@dataclass
class Fill:
    t: int
    side: str          # 'buy' or 'sell' from the MAKER's perspective
    price: float
    size: float
    mid_at_fill: float


@dataclass
class MarketMakerState:
    inventory: float = 0.0
    cash: float = 0.0
    fills: List[Fill] = field(default_factory=list)

    def mark_to_market(self, mid_price: float) -> float:
        """Unrealized + realized P&L at current mid price."""
        return self.cash + self.inventory * mid_price


class FixedSpreadMarketMaker:
    """
    Quotes bid = mid - half_spread, ask = mid + half_spread.
    Fixed quote size each side. No inventory-aware skew (that's the point --
    this is the naive baseline that Avellaneda-Stoikov should beat).
    """

    def __init__(self, half_spread: float = 1.5, quote_size: float = 0.5,
                 max_inventory: float = 5.0):
        self.half_spread = half_spread
        self.quote_size = quote_size
        self.max_inventory = max_inventory
        self.state = MarketMakerState()

    def current_quotes(self, mid_price: float):
        bid = round(mid_price - self.half_spread, 2)
        ask = round(mid_price + self.half_spread, 2)
        return bid, ask

    def on_tick(self, t: int, book: OrderBook, trade_price: Optional[float],
                trade_side: Optional[str]) -> Optional[Fill]:
        """
        Simplified fill logic: if a trade happens and its price crosses our
        quote, we get filled at OUR quoted price (standard maker assumption --
        we don't chase, we get hit/lifted).
        Respects max_inventory as a hard risk limit (stop quoting past it).
        """
        mid = book.mid_price()
        if mid is None or trade_price is None:
            return None

        bid, ask = self.current_quotes(mid)
        fill = None

        # aggressor BUY (lifts offers) -> we get filled on our ASK (we sell)
        if trade_side == "buy" and trade_price >= ask and self.state.inventory - self.quote_size >= -self.max_inventory:
            self.state.inventory -= self.quote_size
            self.state.cash += ask * self.quote_size
            fill = Fill(t=t, side="sell", price=ask, size=self.quote_size, mid_at_fill=mid)

        # aggressor SELL (hits bids) -> we get filled on our BID (we buy)
        elif trade_side == "sell" and trade_price <= bid and self.state.inventory + self.quote_size <= self.max_inventory:
            self.state.inventory += self.quote_size
            self.state.cash -= bid * self.quote_size
            fill = Fill(t=t, side="buy", price=bid, size=self.quote_size, mid_at_fill=mid)

        if fill:
            self.state.fills.append(fill)
        return fill
