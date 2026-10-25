"""
simulate_feed.py

Generates a synthetic but realistic order book + trade stream, so you can
develop and test the market maker WITHOUT needing a live exchange connection.

Model: mid-price follows a random walk with occasional short "informed"
drift bursts (simulates toxic/informed flow that should trigger adverse
selection). Book depth is regenerated each tick around the mid-price.

This is deliberately simple -- the point is to have *something* that
behaves like a real feed so you can validate your maker + metrics logic
before pointing it at Binance.
"""

import random
from dataclasses import dataclass
from typing import Iterator, Optional

from order_book import OrderBook


@dataclass
class Tick:
    book: OrderBook
    trade_price: Optional[float]  # None if no trade this tick
    trade_side: Optional[str]     # 'buy' or 'sell' (aggressor side), if trade_price set
    t: int


class SyntheticFeed:
    def __init__(
        self,
        start_price: float = 50000.0,
        tick_vol: float = 2.0,          # std dev of random-walk step per tick
        n_levels: int = 5,
        level_gap: float = 1.0,         # price gap between book levels
        level_size_mean: float = 1.5,
        trade_prob: float = 0.35,       # chance a trade happens this tick
        informed_burst_prob: float = 0.01,  # chance a toxic-flow burst starts
        informed_burst_len: int = 8,
        informed_drift: float = 3.0,    # extra directional push during a burst
        seed: int = 42,
    ):
        self.price = start_price
        self.tick_vol = tick_vol
        self.n_levels = n_levels
        self.level_gap = level_gap
        self.level_size_mean = level_size_mean
        self.trade_prob = trade_prob
        self.informed_burst_prob = informed_burst_prob
        self.informed_burst_len = informed_burst_len
        self.informed_drift = informed_drift
        self.rng = random.Random(seed)

        self._burst_remaining = 0
        self._burst_direction = 0
        self._t = 0

    def _step_price(self) -> None:
        # base random walk
        step = self.rng.gauss(0, self.tick_vol)

        # maybe start an informed-flow burst (this is what should hurt a naive maker)
        if self._burst_remaining == 0 and self.rng.random() < self.informed_burst_prob:
            self._burst_remaining = self.informed_burst_len
            self._burst_direction = self.rng.choice([-1, 1])

        if self._burst_remaining > 0:
            step += self._burst_direction * self.informed_drift
            self._burst_remaining -= 1

        self.price = max(1.0, self.price + step)

    def _build_book(self) -> OrderBook:
        book = OrderBook()
        bids, asks = [], []
        for i in range(1, self.n_levels + 1):
            bid_price = round(self.price - i * self.level_gap, 2)
            ask_price = round(self.price + i * self.level_gap, 2)
            bids.append((bid_price, max(0.01, self.rng.gauss(self.level_size_mean, 0.4))))
            asks.append((ask_price, max(0.01, self.rng.gauss(self.level_size_mean, 0.4))))
        book.apply_snapshot(bids, asks)
        return book

    def stream(self, n_ticks: int) -> Iterator[Tick]:
        for _ in range(n_ticks):
            self._step_price()
            book = self._build_book()

            trade_price = None
            trade_side = None
            if self.rng.random() < self.trade_prob:
                # during an informed burst, trades are biased in the burst direction
                if self._burst_remaining > 0:
                    trade_side = "buy" if self._burst_direction > 0 else "sell"
                else:
                    trade_side = self.rng.choice(["buy", "sell"])
                trade_price = book.best_ask()[0] if trade_side == "buy" else book.best_bid()[0]
                book.record_trade(trade_price)

            self._t += 1
            yield Tick(book=book, trade_price=trade_price, trade_side=trade_side, t=self._t)
