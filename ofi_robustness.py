"""
ofi_robustness.py

Tries to BREAK the OFI/VOI result before we believe it. Run after ofi_signal_test.py
(it reuses that file's feature code, so keep both in the same folder).

For each horizon H it reports, per feature:
  pred r        correlation with the future move (same number as ofi_signal_test.py)
  partial r     the same after removing the linear effect of the PAST move
                (does the feature know anything beyond "price has been going up"?)
  t (partial)   significance of partial r; |t| < 2 is indistinguishable from noise
  next-win r    correlation with the move one window LATER (a gap of H is skipped).
                A real short-lived effect should fade here.
  null 95%      size of |r| you get by chance: the feature is circularly shifted
                against the moves 200 times, which keeps autocorrelation but breaks
                any real link. Observed |pred r| should sit well above this.
It also prints how well the past move ALONE predicts the future move.

Usage:
    python ofi_robustness.py --file depth_1.jsonl
    python ofi_robustness.py --file depth_1.jsonl --holdout depth_2.jsonl
"""

import argparse
import math
import random
import statistics

from ofi_signal_test import FEATURES, build_samples, compute_series, load_depth, pearson


def residual(y, x):
    """y with the linear effect of x removed."""
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    beta = sum((a - mx) * (b - my) for a, b in zip(x, y)) / sxx if sxx else 0.0
    return [b - my - beta * (a - mx) for a, b in zip(x, y)]


def partial_r(x, y, z):
    return pearson(residual(x, z), residual(y, z))


def null_threshold(x, y, trials=200, seed=0):
    """95th percentile of |r| when x is circularly shifted against y."""
    rng = random.Random(seed)
    n = len(x)
    lo = max(1, n // 10)
    vals = []
    for _ in range(trials):
        k = rng.randint(lo, n - lo)
        vals.append(abs(pearson(x[k:] + x[:k], y)))
    vals.sort()
    return vals[int(0.95 * len(vals)) - 1]


def analyze(path, horizons):
    snaps = load_depth(path)
    print("=" * 78)
    if len(snaps) < 500:
        print(f"{path}: only {len(snaps)} depth snapshots -- record more.")
        return
    series, mid, _ = compute_series(snaps)
    dts = [snaps[i]["ts"] - snaps[i - 1]["ts"] for i in range(1, len(snaps))]
    med_dt = statistics.median(dts)
    print(f"FILE: {path}   snapshots={len(snaps)}")
    print("=" * 78)

    for H in horizons:
        rows = build_samples(series, mid, H, H)
        n = len(rows)
        if n < 60:
            print(f"\nHorizon {H}: only {n} samples -- skipped.")
            continue
        fwd = [r[1] for r in rows]
        past = [r[2] for r in rows]
        print(f"\nHorizon {H} snapshots (~{H * med_dt:.1f}s), n={n}")
        print(f"Past move ALONE -> future move: r = {pearson(past, fwd):+.3f}")
        print(f"{'feature':<8}{'pred r':>8}{'partial r':>11}{'t (part.)':>10}"
              f"{'next-win r':>12}{'null 95%':>10}")
        for name in FEATURES:
            x = [r[0][name] for r in rows]
            pr = partial_r(x, fwd, past)
            t_part = pr * math.sqrt((n - 3) / (1 - pr * pr)) if abs(pr) < 1 else 0.0
            print(f"{name:<8}{pearson(x, fwd):>8.3f}{pr:>11.3f}{t_part:>10.2f}"
                  f"{pearson(x[:-1], fwd[1:]):>12.3f}{null_threshold(x, fwd):>10.3f}")


def main(path, holdout, horizons):
    analyze(path, horizons)
    if holdout:
        analyze(holdout, horizons)
    print("\n" + "-" * 78)
    print("Reading guide: if partial r collapses toward 0, the feature was mostly a proxy")
    print("for momentum. If it stays clearly above 'null 95%' (and |t| > 2) it carries")
    print("information beyond the last move. next-win r should be much smaller than pred r.")
    print("-" * 78)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--holdout", default=None)
    parser.add_argument("--horizons", default="5,20,50")
    args = parser.parse_args()
    main(args.file, args.holdout, [int(h) for h in args.horizons.split(",")])