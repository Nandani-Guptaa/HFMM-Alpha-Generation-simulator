# """
# diagnose_as_realistic.py

# Checks whether A-S's inventory skew is too large relative to its own spread
# when run at realistic (tick-scale) quote distances -- the suspected reason it
# underperformed the fixed-spread trader in run_realistic.py.

# For each tested distance it reports, averaged over the whole replay:
#   half-spread    A-S's own quoted half-spread at that moment
#   |skew|         how far the inventory term shifts the quote off mid
#   skew % of half-spread   the ratio: if this is large (e.g. >50%), the skew is
#                           dominating the quote, which can push it to a worse
#                           price than a plain fixed-spread quote would be at.

# Usage:
#     python diagnose_as_realistic.py --file depth_1.jsonl
# """

# import argparse
# import math
# import statistics

# from avellaneda_stoikov import AvellanedaStoikovMarketMaker
# from run_realistic import TICKS_BACK, replay_depth


# def analyze(path, ticks_back):
#     h = 0.005 + 0.01 * ticks_back
#     maker = AvellanedaStoikovMarketMaker(gamma=0.01, k=1.0 / h, horizon_ticks=20,
#                                          vol_window=50, quote_size=0.01, max_inventory=0.1)
#     skews, half_spreads = [], []
#     for tick in replay_depth(path):
#         maker.on_tick(tick.t, tick.book, tick.trade_price, tick.trade_side)
#         q = maker.state.inventory / maker.max_inventory * 5.0
#         sigma = maker.vol.sigma()
#         tau = maker._time_remaining()
#         skews.append(abs(q * maker.gamma * sigma ** 2 * tau))
#         half_spreads.append((maker.gamma * sigma ** 2 * tau
#                              + (2 / maker.gamma) * math.log(1 + maker.gamma / maker.k)) / 2)
#     avg_skew = statistics.mean(skews)
#     avg_hs = statistics.mean(half_spreads)
#     return h, avg_hs, avg_skew, (avg_skew / avg_hs * 100 if avg_hs else float("nan"))


# def main(path):
#     print("=" * 70)
#     print(f"A-S SKEW vs SPREAD -- {path}")
#     print("=" * 70)
#     print(f"{'ticks back':>10}{'target h':>12}{'half-spread':>14}{'avg |skew|':>14}{'skew % of hs':>14}")
#     for tb in TICKS_BACK:
#         h, hs, sk, pct = analyze(path, tb)
#         print(f"{tb:>10}{h:>12.3f}{hs:>14.3f}{sk:>14.4f}{pct:>13.1f}%")
#     print("-" * 70)
#     print("If skew % is large (roughly >50%), the inventory term is dominating the quote --")
#     print("gamma is miscalibrated for this scale and needs to shrink as h shrinks.")


# if __name__ == "__main__":
#     parser = argparse.ArgumentParser()
#     parser.add_argument("--file", default="depth_1.jsonl")
#     args = parser.parse_args()
#     main(args.file)


# """
# diagnose_as_realistic.py

# Checks whether A-S's inventory skew is too large relative to its own spread
# when run at realistic (tick-scale) quote distances -- the suspected reason it
# underperformed the fixed-spread trader in run_realistic.py.

# For each tested distance it reports, averaged over the whole replay:
#   half-spread    A-S's own quoted half-spread at that moment
#   |skew|         how far the inventory term shifts the quote off mid
#   skew % of half-spread   the ratio: if this is large (e.g. >50%), the skew is
#                           dominating the quote, which can push it to a worse
#                           price than a plain fixed-spread quote would be at.

# Usage:
#     python diagnose_as_realistic.py --file depth_1.jsonl
# """

# import argparse
# import math
# import statistics

# from avellaneda_stoikov import AvellanedaStoikovMarketMaker
# from run_realistic import TICKS_BACK, replay_depth


# def analyze(path, ticks_back):
#     from run_realistic import GAMMA_REF, H_REF
#     h = 0.005 + 0.01 * ticks_back
#     gamma = GAMMA_REF * (h / H_REF)
#     maker = AvellanedaStoikovMarketMaker(gamma=gamma, k=1.0 / h, horizon_ticks=20,
#                                          vol_window=50, quote_size=0.01, max_inventory=0.1)
#     skews, half_spreads = [], []
#     for tick in replay_depth(path):
#         maker.on_tick(tick.t, tick.book, tick.trade_price, tick.trade_side)
#         q = maker.state.inventory / maker.max_inventory * 5.0
#         sigma = maker.vol.sigma()
#         tau = maker._time_remaining()
#         skews.append(abs(q * maker.gamma * sigma ** 2 * tau))
#         half_spreads.append((maker.gamma * sigma ** 2 * tau
#                              + (2 / maker.gamma) * math.log(1 + maker.gamma / maker.k)) / 2)
#     avg_skew = statistics.mean(skews)
#     avg_hs = statistics.mean(half_spreads)
#     return h, avg_hs, avg_skew, (avg_skew / avg_hs * 100 if avg_hs else float("nan"))


# def main(path):
#     print("=" * 70)
#     print(f"A-S SKEW vs SPREAD -- {path}")
#     print("=" * 70)
#     print(f"{'ticks back':>10}{'target h':>12}{'half-spread':>14}{'avg |skew|':>14}{'skew % of hs':>14}")
#     for tb in TICKS_BACK:
#         h, hs, sk, pct = analyze(path, tb)
#         print(f"{tb:>10}{h:>12.3f}{hs:>14.3f}{sk:>14.4f}{pct:>13.1f}%")
#     print("-" * 70)
#     print("If skew % is large (roughly >50%), the inventory term is dominating the quote --")
#     print("gamma is miscalibrated for this scale and needs to shrink as h shrinks.")


# if __name__ == "__main__":
#     parser = argparse.ArgumentParser()
#     parser.add_argument("--file", default="depth_1.jsonl")
#     args = parser.parse_args()
#     main(args.file)



"""
diagnose_as_realistic.py

Checks whether A-S's inventory skew is too large relative to its own spread
when run at realistic (tick-scale) quote distances -- the suspected reason it
underperformed the fixed-spread trader in run_realistic.py.

For each tested distance it reports, averaged over the whole replay:
  half-spread    A-S's own quoted half-spread at that moment
  |skew|         how far the inventory term shifts the quote off mid
  skew % of half-spread   the ratio: if this is large (e.g. >50%), the skew is
                          dominating the quote, which can push it to a worse
                          price than a plain fixed-spread quote would be at.

Usage:
    python diagnose_as_realistic.py --file depth_1.jsonl
"""

import argparse
import math
import statistics

from avellaneda_stoikov import AvellanedaStoikovMarketMaker
from run_realistic import TICKS_BACK, replay_depth


def analyze(path, ticks_back):
    from run_realistic import GAMMA_REF, H_REF
    h = 0.005 + 0.01 * ticks_back
    gamma = GAMMA_REF * (h / H_REF)
    maker = AvellanedaStoikovMarketMaker(gamma=gamma, k=1.0 / h, horizon_ticks=20,
                                         vol_window=50, quote_size=0.01, max_inventory=0.1)
    skews, half_spreads = [], []
    for tick in replay_depth(path):
        maker.on_tick(tick.t, tick.book, tick.trade_price, tick.trade_side)
        q = maker.state.inventory / maker.max_inventory * 5.0
        sigma = maker.vol.sigma()
        tau = maker._time_remaining()
        skews.append(abs(q * maker.gamma * sigma ** 2 * tau))
        half_spreads.append((maker.gamma * sigma ** 2 * tau
                             + (2 / maker.gamma) * math.log(1 + maker.gamma / maker.k)) / 2)
    avg_skew = statistics.mean(skews)
    avg_hs = statistics.mean(half_spreads)
    return h, avg_hs, avg_skew, (avg_skew / avg_hs * 100 if avg_hs else float("nan"))


def main(path):
    print("=" * 70)
    print(f"A-S SKEW vs SPREAD -- {path}")
    print("=" * 70)
    print(f"{'ticks back':>10}{'target h':>12}{'half-spread':>14}{'avg |skew|':>14}{'skew % of hs':>14}")
    for tb in TICKS_BACK:
        h, hs, sk, pct = analyze(path, tb)
        print(f"{tb:>10}{h:>12.3f}{hs:>14.3f}{sk:>14.4f}{pct:>13.1f}%")
    print("-" * 70)
    print("If skew % is large (roughly >50%), the inventory term is dominating the quote --")
    print("gamma is miscalibrated for this scale and needs to shrink as h shrinks.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="depth_1.jsonl")
    args = parser.parse_args()
    main(args.file)