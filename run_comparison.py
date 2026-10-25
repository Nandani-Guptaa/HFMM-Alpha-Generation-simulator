"""
run_comparison.py

Runs FixedSpreadMarketMaker and AvellanedaStoikovMarketMaker against the
EXACT SAME sequence of synthetic ticks (same seed, replayed independently
for each maker) so the comparison is fair -- neither maker gets an easier
or harder market by chance.

This is the script that produces your actual "before vs after" result.
"""

from adverse_selection import AdverseSelectionTracker
from avellaneda_stoikov import AvellanedaStoikovMarketMaker
from market_maker import FixedSpreadMarketMaker
from simulate_feed import SyntheticFeed


def run_maker(maker, n_ticks: int, seed: int):
    """Runs one maker over a fresh feed built from the same seed -- so every
    maker sees an identical sequence of prices and trades."""
    feed = SyntheticFeed(seed=seed)
    adverse_tracker = AdverseSelectionTracker(horizon_ticks=10)
    mtm_history = []
    final_mid = None

    for tick in feed.stream(n_ticks):
        mid = tick.book.mid_price()
        if mid is None:
            continue
        final_mid = mid

        adverse_tracker.record_mid(tick.t, mid)
        fill = maker.on_tick(tick.t, tick.book, tick.trade_price, tick.trade_side)
        if fill:
            adverse_tracker.record_fill(fill)
        adverse_tracker.evaluate_ready(tick.t)
        mtm_history.append(maker.state.mark_to_market(mid))

    mtm = maker.state.mark_to_market(final_mid) if final_mid is not None else 0.0
    adverse = adverse_tracker.summary()
    return {
        "fills": len(maker.state.fills),
        "final_inventory": maker.state.inventory,
        "mtm": mtm,
        "mtm_history": mtm_history,
        "adverse_n": adverse.n_fills,
        "adverse_avg": adverse.avg_adverse_move,
        "adverse_pct": adverse.pct_adverse * 100,
    }


def print_row(label, r):
    print(f"{label:<22} fills={r['fills']:<6} final_inv={r['final_inventory']:>7.2f} "
          f"mtm={r['mtm']:>9.2f} adverse%={r['adverse_pct']:>6.1f}")


def main(n_ticks: int = 5000, seed: int = 42):
    fixed = FixedSpreadMarketMaker(half_spread=0.5, quote_size=0.5, max_inventory=5.0)
    as_maker = AvellanedaStoikovMarketMaker(
        gamma=0.01, k=1.5, horizon_ticks=20, vol_window=50,
        quote_size=0.5, max_inventory=5.0,
    )

    fixed_result = run_maker(fixed, n_ticks, seed)
    as_result = run_maker(as_maker, n_ticks, seed)

    print("=" * 70)
    print(f"COMPARISON -- {n_ticks} synthetic ticks, seed={seed}")
    print("=" * 70)
    print_row("Fixed-spread:", fixed_result)
    print_row("Avellaneda-Stoikov:", as_result)
    print("-" * 70)

    mtm_diff = as_result["mtm"] - fixed_result["mtm"]
    adverse_diff = as_result["adverse_pct"] - fixed_result["adverse_pct"]
    print(f"P&L difference (A-S minus Fixed):        {mtm_diff:+.2f}")
    print(f"Adverse-selection %% difference (A-S - Fixed): {adverse_diff:+.1f} pp")
    if mtm_diff > 0:
        print(">> Avellaneda-Stoikov outperformed the fixed-spread baseline on this run.")
    else:
        print(">> Avellaneda-Stoikov did NOT outperform on this run -- inspect params (gamma/k/horizon).")
    print("=" * 70)


if __name__ == "__main__":
    main()