"""
binance_feed.py

Live order book + trade feed from Binance's public WebSocket API (free, no
API key needed for market data). Produces the SAME Tick shape as
simulate_feed.py so you can swap this in without touching run_backtest.py's
logic -- only the loop that drives it changes (async instead of sync).

Requires: pip install websockets

NOTE: this needs outbound internet access, so it will not run inside a
sandboxed environment without network access to stream.binance.com -- run
it on your own machine.

Usage sketch (see also run_backtest_live.py):

    import asyncio
    from binance_feed import BinanceFeed

    async def main():
        feed = BinanceFeed(symbol="btcusdt")
        async for tick in feed.stream():
            ...  # same tick.book, tick.trade_price, tick.trade_side, tick.t

    asyncio.run(main())
"""

import asyncio
import json
from dataclasses import dataclass
from typing import AsyncIterator, Optional

import websockets

from order_book import OrderBook


@dataclass
class Tick:
    book: OrderBook
    trade_price: Optional[float]
    trade_side: Optional[str]
    t: int


class BinanceFeed:
    """
    Combines the depth20@100ms stream (order book) and the aggTrade stream
    (trades) for a single symbol into one unified tick stream.

    Binance combined stream endpoint:
    wss://stream.binance.com:9443/stream?streams=<symbol>@depth20@100ms/<symbol>@aggTrade
    """

    def __init__(self, symbol: str = "btcusdt"):
        self.symbol = symbol.lower()
        self.url = (
            f"wss://stream.binance.com:9443/stream?streams="
            f"{self.symbol}@depth20@100ms/{self.symbol}@aggTrade"
        )
        self.book = OrderBook()
        self._t = 0

    def _handle_depth(self, data: dict) -> None:
        bids = [(float(p), float(q)) for p, q in data.get("bids", [])]
        asks = [(float(p), float(q)) for p, q in data.get("asks", [])]
        self.book.apply_snapshot(bids, asks)

    def _handle_trade(self, data: dict) -> Optional[Tick]:
        price = float(data["p"])
        # Binance aggTrade: "m" = true means the buyer is the market maker,
        # i.e. the SELLER was the aggressor. So m==True -> aggressor sold.
        trade_side = "sell" if data.get("m") else "buy"
        self.book.record_trade(price)
        self._t += 1
        return Tick(book=self.book, trade_price=price, trade_side=trade_side, t=self._t)

    async def stream(self) -> AsyncIterator[Tick]:
        async with websockets.connect(self.url) as ws:
            async for raw in ws:
                msg = json.loads(raw)
                stream_name = msg.get("stream", "")
                data = msg.get("data", {})

                if "depth" in stream_name:
                    self._handle_depth(data)
                elif "aggTrade" in stream_name:
                    tick = self._handle_trade(data)
                    if tick:
                        yield tick
