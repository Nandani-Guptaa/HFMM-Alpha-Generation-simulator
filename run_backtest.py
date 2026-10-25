"""
run_backtest.py

Ties everything together: feed -> order book -> market maker -> P&L + adverse
selection tracking. Runs on the SYNTHETIC feed by default so it works with
zero setup. Swap in binance_feed.py (see README) once you want live data.

Usage:
    python run_backtest.py
"""

from adverse_selection import AdverseSelectionTracker
from market_maker import FixedSpreadMarketMaker
from simulate_feed import SyntheticFeed


def run(n_ticks: int = 5000, seed: int = 42):
    feed = SyntheticFeed(seed=seed)
    maker = FixedSpreadMarketMaker(half_spread=0.5, quote_size=0.5, max_inventory=5.0)
    adverse_tracker = AdverseSelectionTracker(horizon_ticks=10)

    mtm_history = []

    for tick in feed.stream(n_ticks):
        mid = tick.book.mid_price()
        if mid is None:
            continue

        adverse_tracker.record_mid(tick.t, mid)

        fill = maker.on_tick(tick.t, tick.book, tick.trade_price, tick.trade_side)
        if fill:
            adverse_tracker.record_fill(fill)

        adverse_tracker.evaluate_ready(tick.t)

        mtm_history.append(maker.state.mark_to_market(mid))

    final_mid = mid
    mtm = maker.state.mark_to_market(final_mid)
    adverse = adverse_tracker.summary()

    print("=" * 50)
    print("FIXED-SPREAD MARKET MAKER -- BASELINE RESULTS")
    print("=" * 50)
    print(f"Ticks simulated:        {n_ticks}")
    print(f"Total fills:            {len(maker.state.fills)}")
    print(f"Final inventory:        {maker.state.inventory:.2f}")
    print(f"Final cash:             {maker.state.cash:.2f}")
    print(f"Mark-to-market P&L:     {mtm:.2f}")
    print(f"Peak MtM:               {max(mtm_history):.2f}" if mtm_history else "n/a")
    print(f"Trough MtM:             {min(mtm_history):.2f}" if mtm_history else "n/a")
    print("-" * 50)
    print("ADVERSE SELECTION (did price move against us after fills?)")
    print(f"Fills evaluated:        {adverse.n_fills}")
    print(f"Avg adverse move:       {adverse.avg_adverse_move:.4f}  (positive = bad for maker)")
    print(f"%% of fills adverse:     {adverse.pct_adverse * 100:.1f}%")
    print("=" * 50)

    return {
        "mtm": mtm,
        "fills": len(maker.state.fills),
        "adverse": adverse,
        "mtm_history": mtm_history,
    }


if __name__ == "__main__":
    run()
