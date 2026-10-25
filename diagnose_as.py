import argparse
import math
import statistics

from avellaneda_stoikov import AvellanedaStoikovMarketMaker
from replay_feed import replay


def main(path: str):
    gamma, k = 0.01, 1.5
    maker = AvellanedaStoikovMarketMaker(
        gamma=gamma, k=k, horizon_ticks=20, vol_window=50,
        quote_size=0.01, max_inventory=0.1,
    )
    skews, half_spreads, sigmas = [], [], []

    for tick in replay(path):
        if tick.book.mid_price() is None:
            continue
        maker.on_tick(tick.t, tick.book, tick.trade_price, tick.trade_side)

        q = maker.state.inventory
        sigma = maker.vol.sigma()
        tau = maker._time_remaining()
        skews.append(abs(q * gamma * sigma ** 2 * tau))
        half_spreads.append((gamma * sigma ** 2 * tau + (2 / gamma) * math.log(1 + gamma / k)) / 2)
        sigmas.append(sigma)

    print("=" * 60)
    print(f"A-S DIAGNOSTIC on {path}  ({len(skews)} ticks)")
    print("=" * 60)
    print(f"Avg sigma (per-tick mid move, $):   {statistics.mean(sigmas):.4f}")
    print(f"Avg A-S half-spread ($):            {statistics.mean(half_spreads):.4f}")
    print(f"Avg inventory skew |shift| ($):     {statistics.mean(skews):.5f}")
    print(f"Max inventory skew |shift| ($):     {max(skews):.5f}")
    ratio = statistics.mean(skews) / statistics.mean(half_spreads)
    print(f"Skew as % of half-spread (avg):     {ratio * 100:.2f}%")
    print("(Fixed-spread maker half-spread for reference: 0.50)")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="recorded_ticks.json")
    args = parser.parse_args()
    main(args.file)

    