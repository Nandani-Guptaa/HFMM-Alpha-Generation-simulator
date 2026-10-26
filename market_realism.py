"""
market_realism.py

Wraps any trader (FixedSpreadMarketMaker, AvellanedaStoikovMarketMaker,
SignalMarketMaker) with two layers of realism that the earlier results did
NOT include:

1. TRADING FEES. Every fill now pays a fee (default 10 bps / 0.1%, Binance's
   standard spot maker/taker rate with no BNB discount), charged on both
   sides, subtracted from cash at the moment of the fill.

2. QUEUE POSITION. Earlier results assumed front-of-queue: any trade that
   crossed our price filled us immediately. In reality, if other resting
   orders are already sitting at our price, trades have to eat through THEM
   first. This wrapper reads the actual displayed size at our quote's price
   level in the real recorded order book and only allows a fill once enough
   trade volume has crossed that level to plausibly reach us.

HONEST LIMITS OF THE QUEUE MODEL:
- We only recorded the top 5 price levels (record_depth.py). A quote placed
  further from the market than the 5th level has no queue data, so it falls
  back to the old front-of-queue assumption for that case -- flagged in the
  output as "no queue data" so it's never silently treated as realistic.
- We see a snapshot every ~100ms, not every individual order add/cancel, so
  the queue-ahead estimate is the displayed size at the start of each
  snapshot, not a true order-by-order FIFO reconstruction. This is the best
  that's possible from Binance's public depth stream (which doesn't expose
  per-order IDs) -- a real HFT firm has exchange-provided order-level data
  we don't have access to here.
- We assume our own resting size never appears in that displayed quantity
  (i.e. we're never counted among it), which is reasonable since we're a
  simulated, not a real, participant.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from market_maker import Fill
from order_book import OrderBook

DEFAULT_FEE_BPS = 10.0  # 0.1%, Binance spot standard rate, no fee discount applied


@dataclass
class RealismStats:
    total_fees: float = 0.0
    fills_allowed: int = 0
    fills_blocked_by_queue: int = 0
    fills_with_no_queue_data: int = 0


class RealisticMaker:
    """Wraps a maker's on_tick so fills additionally require clearing a queue
    (when depth data is available) and pay a trading fee."""

    def __init__(self, maker, fee_bps: float = DEFAULT_FEE_BPS, model_queue: bool = True):
        self._maker = maker
        self.fee_bps = fee_bps
        self.model_queue = model_queue
        self.stats = RealismStats()
        self._snap = None
        self._consumed: Dict[str, float] = {"buy": 0.0, "sell": 0.0}
        self._queue_ahead: Dict[str, Optional[float]] = {"buy": None, "sell": None}
        self._done_this_snap: set = set()

    def __getattr__(self, name):
        return getattr(self._maker, name)

    def _queue_ahead_for(self, book: OrderBook, price: float, side: str) -> Optional[float]:
        """side here is the BOOK side our resting order sits on: a maker's bid
        sits on the book's bid side, its ask on the book's ask side."""
        levels = book.bids if side == "bid" else book.asks
        key = round(price, 2)
        for p, q in levels.items():
            if round(p, 2) == key:
                return q
        return None  # not in the top levels we have -- no queue data

    def on_tick(self, t: int, book: OrderBook, trade_price: Optional[float],
                trade_side: Optional[str]) -> Optional[Fill]:
        snap = getattr(book, "snap_id", None)
        if snap != self._snap:
            self._snap = snap
            self._consumed = {"buy": 0.0, "sell": 0.0}
            self._queue_ahead = {"buy": None, "sell": None}
            self._done_this_snap = set()

        if trade_price is None or trade_side is None:
            return self._maker.on_tick(t, book, None, None)

        if trade_side in self._done_this_snap:
            return self._maker.on_tick(t, book, None, None)  # already filled this side

        if not self.model_queue:
            fill = self._maker.on_tick(t, book, trade_price, trade_side)
            if fill:
                self._apply_fee(fill)
                self.stats.fills_allowed += 1
                self._done_this_snap.add(trade_side)
            return fill

        # Figure out what price we'd quote right now, without letting it fill yet
        mid = book.mid_price()
        probe_fn = getattr(self._maker, "current_quotes", None)
        if probe_fn is None or mid is None:
            fill = self._maker.on_tick(t, book, trade_price, trade_side)
            if fill:
                self._apply_fee(fill)
                self.stats.fills_allowed += 1
                self._done_this_snap.add(trade_side)
            return fill

        try:
            bid, ask = probe_fn(mid, getattr(book, "imb1_avg", 0.0))
        except TypeError:
            bid, ask = probe_fn(mid)

        our_price = ask if trade_side == "buy" else bid
        book_side = "ask" if trade_side == "buy" else "bid"
        does_cross = (trade_price >= ask) if trade_side == "buy" else (trade_price <= bid)
        if not does_cross:
            return self._maker.on_tick(t, book, None, None)

        if self._queue_ahead[trade_side] is None:
            qa = self._queue_ahead_for(book, our_price, book_side)
            if qa is None:
                self.stats.fills_with_no_queue_data += 1
                qa = 0.0  # no data -> fall back to front-of-queue for this fill only
            self._queue_ahead[trade_side] = qa

        trade_qty = getattr(trade_price, "qty", None)  # Tick doesn't carry qty today
        # Our replay layer doesn't pass per-trade size, so approximate consumption
        # with the maker's own quote_size per trade event -- conservative (tends to
        # make the queue clear SLOWER, i.e. understate fills, not overstate them).
        self._consumed[trade_side] += getattr(self._maker, "quote_size", 0.01)

        if self._consumed[trade_side] < self._queue_ahead[trade_side]:
            self.stats.fills_blocked_by_queue += 1
            return self._maker.on_tick(t, book, None, None)

        fill = self._maker.on_tick(t, book, trade_price, trade_side)
        if fill:
            self._apply_fee(fill)
            self.stats.fills_allowed += 1
            self._done_this_snap.add(trade_side)
        return fill

    def _apply_fee(self, fill: Fill) -> None:
        fee = (self.fee_bps / 10000.0) * fill.price * fill.size
        self._maker.state.cash -= fee
        self.stats.total_fees += fee