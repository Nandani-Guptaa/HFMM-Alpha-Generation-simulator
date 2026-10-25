"""
adverse_selection.py

For every fill, checks what the mid-price does N ticks later.
If the maker consistently loses money on this "post-fill drift", that's
adverse selection -- the maker is trading against informed/toxic flow.

This is the metric that separates "my market maker made money" from
"my market maker made money on this run but is structurally getting picked off".
Track it from day one, don't bolt it on after the fact.
"""

from dataclasses import dataclass
from typing import Dict, List

from market_maker import Fill


@dataclass
class AdverseSelectionResult:
    n_fills: int
    avg_adverse_move: float   # positive = mid moved against the maker, on average
    pct_adverse: float        # fraction of fills where mid moved against the maker
    per_fill: List[Dict]


class AdverseSelectionTracker:
    def __init__(self, horizon_ticks: int = 10):
        self.horizon_ticks = horizon_ticks
        self._pending: List[Fill] = []
        self._mid_history: Dict[int, float] = {}   # t -> mid_price
        self.results: List[Dict] = []

    def record_mid(self, t: int, mid_price: float) -> None:
        self._mid_history[t] = mid_price

    def record_fill(self, fill: Fill) -> None:
        self._pending.append(fill)

    def evaluate_ready(self, current_t: int) -> None:
        """Check any pending fills whose horizon has now passed."""
        still_pending = []
        for fill in self._pending:
            target_t = fill.t + self.horizon_ticks
            if target_t <= current_t and target_t in self._mid_history:
                future_mid = self._mid_history[target_t]
                # If we SOLD (maker side='sell'), adverse = price rising after we sold.
                # If we BOUGHT (maker side='buy'), adverse = price falling after we bought.
                if fill.side == "sell":
                    adverse_move = future_mid - fill.mid_at_fill
                else:
                    adverse_move = fill.mid_at_fill - future_mid
                self.results.append({
                    "t": fill.t, "side": fill.side, "fill_price": fill.price,
                    "mid_at_fill": fill.mid_at_fill, "future_mid": future_mid,
                    "adverse_move": adverse_move,
                })
            else:
                still_pending.append(fill)
        self._pending = still_pending

    def summary(self) -> AdverseSelectionResult:
        if not self.results:
            return AdverseSelectionResult(0, 0.0, 0.0, [])
        n = len(self.results)
        avg = sum(r["adverse_move"] for r in self.results) / n
        pct_adverse = sum(1 for r in self.results if r["adverse_move"] > 0) / n
        return AdverseSelectionResult(n, avg, pct_adverse, self.results)
