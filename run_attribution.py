import argparse

from avellaneda_stoikov import AvellanedaStoikovMarketMaker
from market_maker import FixedSpreadMarketMaker
from replay_feed import replay
from simulate_feed import SyntheticFeed


def run_with_attribution(maker, ticks, max_inventory):
    prev_mid = None
    final_mid = None
    edge = 0.0
    inv_pnl = 0.0
    buys = sells = 0
    at_cap = 0
    n = 0
    abs_inv_sum = 0.0

    for tick in ticks:
        mid = tick.book.mid_price()
        if mid is None:
            continue

        # inventory held going INTO this tick earns/loses the mid move
        if prev_mid is not None:
            inv_pnl += maker.state.inventory * (mid - prev_mid)

        fill = maker.on_tick(tick.t, tick.book, tick.trade_price, tick.trade_side)
        if fill:
            if fill.side == "buy":
                edge += (mid - fill.price) * fill.size
                buys += 1
            else:
                edge += (fill.price - mid) * fill.size
                sells += 1

        prev_mid = mid
        final_mid = mid
        n += 1
        inv = maker.state.inventory
        abs_inv_sum += abs(inv)
        if abs(inv) >= max_inventory - 1e-6:
            at_cap += 1

    total = maker.state.mark_to_market(final_mid)
    fills = buys + sells
    return {
        "total": total,
        "edge": edge,
        "inv_pnl": inv_pnl,
        "residual": total - (edge + inv_pnl),
        "buys": buys,
        "sells": sells,
        "edge_per_unit": edge / (fills * maker.quote_size) if fills else 0.0,
        "pct_at_cap": 100.0 * at_cap / n if n else 0.0,
        "avg_abs_inv": abs_inv_sum / n if n else 0.0,
        "final_inv": maker.state.inventory,
    }


def show(title, a, b):
    print("=" * 66)
    print(title)
    print("=" * 66)
    print(f"{'':<34}{'Fixed-spread':>15}{'Avellaneda-S.':>15}")

    def row(label, key, fmt):
        print(f"{label:<34}{format(a[key], fmt):>15}{format(b[key], fmt):>15}")

    row("Total mark-to-market P&L ($)", "total", "+.2f")
    row("  = Edge captured at fills ($)", "edge", "+.2f")
    row("  + Inventory / drift P&L ($)", "inv_pnl", "+.2f")
    print("-" * 66)
    row("Buy fills", "buys", "d")
    row("Sell fills", "sells", "d")
    row("Avg edge per unit traded ($)", "edge_per_unit", ".3f")
    row("Avg |inventory|", "avg_abs_inv", ".4f")
    row("Time at inventory limit (%)", "pct_at_cap", ".1f")
    row("Final inventory", "final_inv", "+.4f")
    print("-" * 66)
    print(f"Check (total - edge - inventory): {a['residual']:+.2e} / {b['residual']:+.2e}")
    print("=" * 66)


def main(path):
    if path:
        # live-scale settings, same as run_comparison_live.py
        qs, mi = 0.01, 0.1
        make_ticks = lambda: replay(path)
        title = f"P&L ATTRIBUTION -- recorded data: {path}"
    else:
        qs, mi = 0.5, 5.0
        make_ticks = lambda: SyntheticFeed(seed=42).stream(5000)
        title = "P&L ATTRIBUTION -- synthetic, 5000 ticks, seed=42"

    fixed = FixedSpreadMarketMaker(half_spread=0.5, quote_size=qs, max_inventory=mi)
    as_maker = AvellanedaStoikovMarketMaker(
        gamma=0.01, k=1.5, horizon_ticks=20, vol_window=50,
        quote_size=qs, max_inventory=mi,
    )
    a = run_with_attribution(fixed, make_ticks(), mi)
    b = run_with_attribution(as_maker, make_ticks(), mi)
    show(title, a, b)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=None,
                        help="recorded tick file; omit to use the synthetic feed")
    args = parser.parse_args()
    main(args.file)
    