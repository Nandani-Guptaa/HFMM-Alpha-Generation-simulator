"""
avellaneda_stoikov.py

Implements the Avellaneda-Stoikov (2008) optimal market making model.

Core idea, in plain terms: instead of quoting a fixed spread around the
mid-price (like FixedSpreadMarketMaker), this maker:
  1. Shifts its "center" price (the reservation price) away from mid,
     in the direction that makes it easier to offload inventory it's
     already carrying too much of.
  2. Widens its spread when volatility is high or a lot of time
     remains in the current risk horizon, and narrows it near the end
     of the horizon (less time = less risk to worry about).

This is exactly the mechanism that should have prevented the one-sided
bleed you saw in the fixed-spread live run: if inventory keeps building
short (or long), the reservation price skews to make the OPPOSITE side
more attractive, discouraging further one-directional fills.

Formulas (standard A-S, finite-horizon form):
    reservation_price = mid - q * gamma * sigma^2 * (T - t)
    optimal_spread     = gamma * sigma^2 * (T - t) + (2/gamma) * ln(1 + gamma/k)
    bid = reservation_price - optimal_spread / 2
    ask = reservation_price + optimal_spread / 2

Where:
    q      = current inventory (maker's own state)
    gamma  = risk aversion (higher = more aggressive inventory management)
    sigma  = volatility of the asset (estimated from recent mid-price returns)
    T - t  = "time remaining" in the current risk horizon (ticks)
    k      = market order arrival intensity (liquidity proxy; higher = tighter spread)

IMPORTANT SIMPLIFICATION: the classic A-S model assumes one finite trading
session ending at time T (e.g. end of day, at which point you MUST be
flat). A live, always-on feed has no natural "end of day", so this
implementation uses a repeating horizon: every `horizon_ticks`, T resets
by wrapping. This is a common practical approximation, not the original
paper's exact setting -- be upfront about this if you write this up.
"""

import math
from collections import deque
from dataclasses import dataclass
from typing import Optional

from market_maker import Fill, MarketMakerState
from order_book import OrderBook


class RollingVolatility:
    """Estimates sigma (std dev of mid-price returns) over a rolling window."""

    def __init__(self, window: int = 50):
        self.window = window
        self._prices = deque(maxlen=window + 1)

    def update(self, price: float) -> None:
        self._prices.append(price)

    def sigma(self, default: float = 1.0) -> float:
        if len(self._prices) < 3:
            return default  # not enough data yet -- fall back to a sane default
        prices = list(self._prices)
        returns = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
        n = len(returns)
        mean = sum(returns) / n
        variance = sum((r - mean) ** 2 for r in returns) / max(1, n - 1)
        std = math.sqrt(variance)
        return std if std > 1e-8 else default


class AvellanedaStoikovMarketMaker:
    """
    Same interface as FixedSpreadMarketMaker (on_tick, .state) so it can be
    dropped into the exact same backtest harness for direct comparison.
    """

    def __init__(
        self,
        gamma: float = 0.1,
        k: float = 1.5,
        horizon_ticks: int = 500,
        vol_window: int = 50,
        quote_size: float = 0.5,
        max_inventory: float = 5.0,
    ):
        self.gamma = gamma
        self.k = k
        self.horizon_ticks = horizon_ticks
        self.quote_size = quote_size
        self.max_inventory = max_inventory
        self.vol = RollingVolatility(window=vol_window)
        self.state = MarketMakerState()
        self._t_in_horizon = 0

    def _time_remaining(self) -> float:
        """Ticks remaining until the current horizon 'resets'. Never lets this hit
        exactly zero (which would collapse the spread formula)."""
        remaining = self.horizon_ticks - self._t_in_horizon
        return max(1, remaining)

    def current_quotes(self, mid_price: float):
        q = self.state.inventory / self.max_inventory * 5.0
        sigma = self.vol.sigma()
        tau = self._time_remaining()

        reservation_price = mid_price - q * self.gamma * (sigma ** 2) * tau
        optimal_spread = (
            self.gamma * (sigma ** 2) * tau
            + (2.0 / self.gamma) * math.log(1 + self.gamma / self.k)
        )
        bid = round(reservation_price - optimal_spread / 2, 2)
        ask = round(reservation_price + optimal_spread / 2, 2)
        return bid, ask

    def on_tick(self, t: int, book: OrderBook, trade_price: Optional[float],
                trade_side: Optional[str]) -> Optional[Fill]:
        mid = book.mid_price()
        if mid is None:
            return None

        self.vol.update(mid)
        self._t_in_horizon = (self._t_in_horizon + 1) % self.horizon_ticks

        if trade_price is None:
            return None

        bid, ask = self.current_quotes(mid)
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