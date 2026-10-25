"""
run_comparison_live.py

Same idea as run_comparison.py, but replays RECORDED REAL Binance data
(from record_live_ticks.py) instead of the synthetic feed. Both makers see
the exact same recorded sequence, so it's a fair comparison on real data.

Usage:
    python record_live_ticks.py --ticks 3000   # do this first, on your machine
    python run_comparison_live.py --file recorded_ticks.json
"""

import argparse

from adverse_selection import AdverseSelectionTracker
from avellaneda_stoikov import AvellanedaStoikovMarketMaker
from market_maker import FixedSpreadMarketMaker
from replay_feed import replay


def run_maker_on_replay(maker, path: str):
    adverse_tracker = AdverseSelectionTracker(horizon_ticks=10)
    final_mid = None

    for tick in replay(path):
        mid = tick.book.mid_price()
        if mid is None:
            continue
        final_mid = mid

        adverse_tracker.record_mid(tick.t, mid)
        fill = maker.on_tick(tick.t, tick.book, tick.trade_price, tick.trade_side)
        if fill:
            adverse_tracker.record_fill(fill)
        adverse_tracker.evaluate_ready(tick.t)

    mtm = maker.state.mark_to_market(final_mid) if final_mid is not None else 0.0
    adverse = adverse_tracker.summary()
    return {
        "fills": len(maker.state.fills),
        "final_inventory": maker.state.inventory,
        "mtm": mtm,
        "adverse_pct": adverse.pct_adverse * 100,
    }


def print_row(label, r):
    print(f"{label:<22} fills={r['fills']:<6} final_inv={r['final_inventory']:>7.4f} "
          f"mtm={r['mtm']:>9.2f} adverse%={r['adverse_pct']:>6.1f}")


def main(path: str):
    fixed = FixedSpreadMarketMaker(half_spread=0.5, quote_size=0.01, max_inventory=0.1)
    as_maker = AvellanedaStoikovMarketMaker(
        gamma=0.01, k=1.5, horizon_ticks=20, vol_window=50,
        quote_size=0.01, max_inventory=0.1,
    )

    fixed_result = run_maker_on_replay(fixed, path)
    as_result = run_maker_on_replay(as_maker, path)

    print("=" * 70)
    print(f"COMPARISON ON RECORDED REAL DATA -- {path}")
    print("=" * 70)
    print_row("Fixed-spread:", fixed_result)
    print_row("Avellaneda-Stoikov:", as_result)
    print("-" * 70)
    mtm_diff = as_result["mtm"] - fixed_result["mtm"]
    print(f"P&L difference (A-S minus Fixed): {mtm_diff:+.2f}")
    if mtm_diff > 0:
        print(">> A-S outperformed on this REAL recorded data too.")
    else:
        print(">> A-S did NOT outperform here -- worth investigating why (params? too little data?).")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="recorded_ticks.json")
    args = parser.parse_args()
    main(args.file)