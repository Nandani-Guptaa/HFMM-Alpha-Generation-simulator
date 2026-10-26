"""
run_fees_queue.py

The most realistic version of the comparison yet: fixed-spread, calibrated
Avellaneda-Stoikov, and the signal-driven trader, all run with TRADING FEES
and QUEUE-POSITION modeling (see market_realism.py for exactly what that
does and does not capture).

Uses the same realistic quote distance (4 ticks back) and the same locked
signal setting (window=5, skew=1.0) chosen earlier -- nothing is re-tuned
here. The point of this script is to see whether those earlier conclusions
survive two more doses of reality, not to find new best settings.

Usage:
    python run_fees_queue.py
    python run_fees_queue.py --files depth_1.jsonl depth_2.jsonl depth_3.jsonl
    python run_fees_queue.py --fee-bps 0        # fees off, queue still on
    python run_fees_queue.py --no-queue         # queue off, fees still on
"""

import argparse

from avellaneda_stoikov import AvellanedaStoikovMarketMaker
from market_maker import FixedSpreadMarketMaker
from market_realism import RealisticMaker
from run_realistic import GAMMA_REF, H_REF, TICKS_BACK, replay_depth
from signal_maker import SignalMarketMaker, replay_with_signal

QUOTE_SIZE = 0.01
MAX_INV = 0.1
TICKS_BACK_FIXED = 4
H = 0.005 + 0.01 * TICKS_BACK_FIXED
SIGNAL_WINDOW, SIGNAL_SKEW = 5, 1.0


def run(maker, ticks, fee_bps, model_queue):
    rm = RealisticMaker(maker, fee_bps=fee_bps, model_queue=model_queue)
    final_mid = None
    edge = 0.0
    inv_pnl = 0.0
    prev_mid = None
    buys = sells = 0

    for tick in ticks:
        mid = tick.book.mid_price()
        if mid is None:
            continue
        if prev_mid is not None:
            inv_pnl += maker.state.inventory * (mid - prev_mid)

        fill = rm.on_tick(tick.t, tick.book, tick.trade_price, tick.trade_side)
        if fill:
            if fill.side == "buy":
                edge += (mid - fill.price) * fill.size
                buys += 1
            else:
                edge += (fill.price - mid) * fill.size
                sells += 1

        prev_mid = mid
        final_mid = mid

    total = maker.state.mark_to_market(final_mid) if final_mid is not None else 0.0
    return {
        "total": total, "edge": edge, "inv_pnl": inv_pnl, "fees": rm.stats.total_fees,
        "residual": total - (edge + inv_pnl - rm.stats.total_fees),
        "buys": buys, "sells": sells,
        "blocked_by_queue": rm.stats.fills_blocked_by_queue,
        "no_queue_data": rm.stats.fills_with_no_queue_data,
        "final_inv": maker.state.inventory,
    }


def row(label, r):
    print(f"{label:<26} fills={r['buys'] + r['sells']:<5} P&L={r['total']:>+8.3f}  "
          f"edge={r['edge']:>+7.3f}  drift={r['inv_pnl']:>+8.3f}  fees={r['fees']:>6.3f}  "
          f"q-blocked={r['blocked_by_queue']:<5} no-q-data={r['no_queue_data']}")


def main(paths, fee_bps, model_queue):
    for path in paths:
        print("=" * 100)
        print(f"FILE: {path}   fee={fee_bps}bps   queue-modeled={model_queue}   "
              f"(quote distance {TICKS_BACK_FIXED} ticks back, h=${H:.3f})")
        print("=" * 100)

        fixed = FixedSpreadMarketMaker(half_spread=H, quote_size=QUOTE_SIZE, max_inventory=MAX_INV)
        row("Fixed-spread", run(fixed, replay_depth(path), fee_bps, model_queue))

        gamma = GAMMA_REF * (H / H_REF)
        as_maker = AvellanedaStoikovMarketMaker(gamma=gamma, k=1.0 / H, horizon_ticks=20,
                                                vol_window=50, quote_size=QUOTE_SIZE,
                                                max_inventory=MAX_INV)
        row("Avellaneda-Stoikov", run(as_maker, replay_depth(path), fee_bps, model_queue))

        sig = SignalMarketMaker(half_spread=H, quote_size=QUOTE_SIZE, max_inventory=MAX_INV,
                                max_skew_frac=SIGNAL_SKEW)
        r_sig = run(sig, replay_with_signal(path, SIGNAL_WINDOW), fee_bps, model_queue)
        row(f"Signal (w={SIGNAL_WINDOW}, skew={SIGNAL_SKEW})", r_sig)
        worst_residual = max(abs(r_sig["residual"]), 0.0)
        print(f"Check (total - edge - drift + fees), should be ~0: {worst_residual:.2e}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", nargs="+", default=["depth_1.jsonl", "depth_2.jsonl"])
    parser.add_argument("--fee-bps", type=float, default=10.0)
    parser.add_argument("--no-queue", action="store_true")
    args = parser.parse_args()
    main(args.files, args.fee_bps, model_queue=not args.no_queue)