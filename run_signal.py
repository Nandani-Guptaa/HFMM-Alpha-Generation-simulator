# """
# run_signal.py

# Phase 3 test: does skewing quotes with the imb1 order-imbalance signal beat
# the fixed-spread baseline and the (properly calibrated) Avellaneda-Stoikov
# trader, on the same real recordings and the same one-fill-per-snapshot rule
# used in run_realistic.py?

# Quote distance is held FIXED (at a realistic 4-ticks-back) so the only thing
# varying is the signal itself: how far back the rolling imb1 average looks
# (window, in ~100ms snapshots) and how strongly it is allowed to skew the
# quote (max_skew_frac, as a fraction of the half-spread -- never a separate
# dollar scale, to avoid the calibration mistake found in Avellaneda-Stoikov).

# Usage:
#     python run_signal.py
#     python run_signal.py --files depth_1.jsonl depth_2.jsonl
# """

# import argparse

# from avellaneda_stoikov import AvellanedaStoikovMarketMaker
# from market_maker import FixedSpreadMarketMaker
# from run_attribution import run_with_attribution
# from run_realistic import GAMMA_REF, H_REF, OneFillPerSidePerSnapshot
# from signal_maker import SignalMarketMaker, replay_with_signal

# QUOTE_SIZE = 0.01
# MAX_INV = 0.1
# TICKS_BACK = 4                       # fixed, realistic distance (see run_realistic.py)
# H = 0.005 + 0.01 * TICKS_BACK
# WINDOWS = [5, 10, 20]                 # ~0.5s, ~1s, ~2s of snapshot history
# SKEW_FRACS = [0.2, 0.5, 1.0]


# def run(maker, path, window=None):
#     ticks = replay_with_signal(path, window) if window else None
#     if ticks is None:
#         from run_realistic import replay_depth
#         ticks = replay_depth(path)
#     wrapped = OneFillPerSidePerSnapshot(maker)
#     return run_with_attribution(wrapped, ticks, MAX_INV)


# def row(label, r):
#     print(f"{label:<28} fills={r['buys'] + r['sells']:<6} P&L={r['total']:>+8.3f}  "
#           f"edge={r['edge']:>+7.3f}  drift={r['inv_pnl']:>+8.3f}  cap%={r['pct_at_cap']:>5.1f}")


# def main(paths):
#     for path in paths:
#         print("=" * 78)
#         print(f"FILE: {path}   (quote distance fixed at {TICKS_BACK} ticks back, h=${H:.3f})")
#         print("=" * 78)

#         fixed = FixedSpreadMarketMaker(half_spread=H, quote_size=QUOTE_SIZE, max_inventory=MAX_INV)
#         row("Fixed-spread (baseline)", run(fixed, path))

#         gamma = GAMMA_REF * (H / H_REF)
#         as_maker = AvellanedaStoikovMarketMaker(gamma=gamma, k=1.0 / H, horizon_ticks=20,
#                                                 vol_window=50, quote_size=QUOTE_SIZE,
#                                                 max_inventory=MAX_INV)
#         row("Avellaneda-Stoikov", run(as_maker, path))

#         print("-" * 78)
#         best = None
#         for w in WINDOWS:
#             for sf in SKEW_FRACS:
#                 sig = SignalMarketMaker(half_spread=H, quote_size=QUOTE_SIZE,
#                                         max_inventory=MAX_INV, max_skew_frac=sf)
#                 r = run(sig, path, window=w)
#                 row(f"Signal (window={w:>2}, skew={sf})", r)
#                 if best is None or r["total"] > best[1]["total"]:
#                     best = (f"window={w}, skew={sf}", r)
#         print("-" * 78)
#         print(f"Best signal setting on this file: {best[0]}  ->  P&L {best[1]['total']:+.3f}")
#         print("=" * 78 + "\n")


# if __name__ == "__main__":
#     parser = argparse.ArgumentParser()
#     parser.add_argument("--files", nargs="+", default=["depth_1.jsonl", "depth_2.jsonl"])
#     args = parser.parse_args()
#     main(args.files)


"""
run_signal.py

Phase 3 test: does skewing quotes with the imb1 order-imbalance signal beat
the fixed-spread baseline and the (properly calibrated) Avellaneda-Stoikov
trader, on the same real recordings and the same one-fill-per-snapshot rule
used in run_realistic.py?

Quote distance is held FIXED (at a realistic 4-ticks-back) so the only thing
varying is the signal itself: how far back the rolling imb1 average looks
(window, in ~100ms snapshots) and how strongly it is allowed to skew the
quote (max_skew_frac, as a fraction of the half-spread -- never a separate
dollar scale, to avoid the calibration mistake found in Avellaneda-Stoikov).

Usage:
    python run_signal.py
    python run_signal.py --files depth_1.jsonl depth_2.jsonl
"""

import argparse

from avellaneda_stoikov import AvellanedaStoikovMarketMaker
from market_maker import FixedSpreadMarketMaker
from run_attribution import run_with_attribution
from run_realistic import GAMMA_REF, H_REF, OneFillPerSidePerSnapshot
from signal_maker import SignalMarketMaker, replay_with_signal

QUOTE_SIZE = 0.01
MAX_INV = 0.1
TICKS_BACK = 4                       # fixed, realistic distance (see run_realistic.py)
H = 0.005 + 0.01 * TICKS_BACK
WINDOWS = [3, 5, 10]                  # ~0.3s, ~0.5s, ~1s of snapshot history
SKEW_FRACS = [1.0, 1.5, 2.0, 3.0, 5.0]  # extended past 1.0 -- the earlier best sat at this edge


def run(maker, path, window=None):
    ticks = replay_with_signal(path, window) if window else None
    if ticks is None:
        from run_realistic import replay_depth
        ticks = replay_depth(path)
    wrapped = OneFillPerSidePerSnapshot(maker)
    return run_with_attribution(wrapped, ticks, MAX_INV)


def row(label, r):
    print(f"{label:<28} fills={r['buys'] + r['sells']:<6} P&L={r['total']:>+8.3f}  "
          f"edge={r['edge']:>+7.3f}  drift={r['inv_pnl']:>+8.3f}  cap%={r['pct_at_cap']:>5.1f}")


def main(paths):
    for path in paths:
        print("=" * 78)
        print(f"FILE: {path}   (quote distance fixed at {TICKS_BACK} ticks back, h=${H:.3f})")
        print("=" * 78)

        fixed = FixedSpreadMarketMaker(half_spread=H, quote_size=QUOTE_SIZE, max_inventory=MAX_INV)
        row("Fixed-spread (baseline)", run(fixed, path))

        gamma = GAMMA_REF * (H / H_REF)
        as_maker = AvellanedaStoikovMarketMaker(gamma=gamma, k=1.0 / H, horizon_ticks=20,
                                                vol_window=50, quote_size=QUOTE_SIZE,
                                                max_inventory=MAX_INV)
        row("Avellaneda-Stoikov", run(as_maker, path))

        print("-" * 78)
        best = None
        for w in WINDOWS:
            for sf in SKEW_FRACS:
                sig = SignalMarketMaker(half_spread=H, quote_size=QUOTE_SIZE,
                                        max_inventory=MAX_INV, max_skew_frac=sf)
                r = run(sig, path, window=w)
                row(f"Signal (window={w:>2}, skew={sf})", r)
                if best is None or r["total"] > best[1]["total"]:
                    best = (f"window={w}, skew={sf}", r)
        print("-" * 78)
        print(f"Best signal setting on this file: {best[0]}  ->  P&L {best[1]['total']:+.3f}")
        print("=" * 78 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", nargs="+", default=["depth_1.jsonl", "depth_2.jsonl"])
    args = parser.parse_args()
    main(args.files)