"""
ofi_signal_test.py

Tests whether order-flow features PREDICT the next short-term mid-price move,
before any of it is wired into a market maker.

Features (all computed from consecutive top-5 depth snapshots):
  ofi1  Order Flow Imbalance at the best bid/ask (Cont-Kukanov-Stoikov 2014)
  ofi5  the same quantity summed over the top 5 levels
  voi   Volume Order Imbalance at the best bid/ask
  imb1  static queue imbalance at the best level: (bid qty - ask qty) / total
  imb5  static depth imbalance over the top 5 levels

For each horizon H (in snapshots) the flow features are summed (imbalances are
averaged) over the last H snapshots, and compared with the mid-price change over
the NEXT H snapshots. Decision points are non-overlapping, so n is honest.

Columns:
  contemp r  correlation with the move over the SAME window (sanity check: OFI/VOI
             should be clearly positive here, otherwise a sign/logic bug)
  pred r     correlation with the FUTURE move (the number that matters)
  spearman   rank version of pred r (robust to outliers)
  t-stat     significance of pred r (rough: |t| < 2 is indistinguishable from noise)
  hit %      how often sign(feature) == sign(future move), ignoring zeros
  Q5-Q1 $    avg future move after the top 20% feature values minus after the bottom 20%

Usage:
    python ofi_signal_test.py --file depth_1.jsonl
    python ofi_signal_test.py --file depth_1.jsonl --holdout depth_2.jsonl
"""

import argparse
import json
import math
import statistics

LEVELS = 5
FEATURES = ["ofi1", "ofi5", "voi", "imb1", "imb5"]


def load_depth(path):
    snaps = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue  # partial last line after Ctrl+C
            if r.get("type") == "depth":
                snaps.append(r)
    return snaps


def level_ofi(pb, qb, pb0, qb0, pa, qa, pa0, qa0):
    """OFI contribution of one book level between two consecutive snapshots."""
    e = 0.0
    if pb > pb0:
        e += qb
    elif pb == pb0:
        e += qb - qb0
    else:
        e -= qb0
    if pa < pa0:
        e -= qa
    elif pa == pa0:
        e -= qa - qa0
    else:
        e += qa0
    return e


def compute_series(snaps):
    n_snaps = len(snaps)
    levels = min(LEVELS, len(snaps[0]["b"]))
    mid = [(s["b"][0][0] + s["a"][0][0]) / 2 for s in snaps]
    spread = [s["a"][0][0] - s["b"][0][0] for s in snaps]
    series = {k: [0.0] * n_snaps for k in FEATURES}

    for n in range(n_snaps):
        b, a = snaps[n]["b"], snaps[n]["a"]
        tb = b[0][1] + a[0][1]
        series["imb1"][n] = (b[0][1] - a[0][1]) / tb if tb > 0 else 0.0
        sb = sum(x[1] for x in b[:levels])
        sa = sum(x[1] for x in a[:levels])
        series["imb5"][n] = (sb - sa) / (sb + sa) if sb + sa > 0 else 0.0
        if n == 0:
            continue

        pb, pa = snaps[n - 1]["b"], snaps[n - 1]["a"]
        series["ofi1"][n] = level_ofi(b[0][0], b[0][1], pb[0][0], pb[0][1],
                                      a[0][0], a[0][1], pa[0][0], pa[0][1])
        series["ofi5"][n] = sum(
            level_ofi(b[i][0], b[i][1], pb[i][0], pb[i][1],
                      a[i][0], a[i][1], pa[i][0], pa[i][1])
            for i in range(levels))

        # VOI: bid side adds volume when price rises or holds, ask side when price falls or holds
        if b[0][0] > pb[0][0]:
            dvb = b[0][1]
        elif b[0][0] == pb[0][0]:
            dvb = b[0][1] - pb[0][1]
        else:
            dvb = 0.0
        if a[0][0] < pa[0][0]:
            dva = a[0][1]
        elif a[0][0] == pa[0][0]:
            dva = a[0][1] - pa[0][1]
        else:
            dva = 0.0
        series["voi"][n] = dvb - dva

    return series, mid, spread


def build_samples(series, mid, W, H):
    """Non-overlapping decision points: (features over last W, future move over next H, same-window move)."""
    rows = []
    n_snaps = len(mid)
    step = max(W, H)
    t = W
    while t + H < n_snaps:
        lo, hi = t - W + 1, t + 1
        feats = {
            "ofi1": sum(series["ofi1"][lo:hi]),
            "ofi5": sum(series["ofi5"][lo:hi]),
            "voi": sum(series["voi"][lo:hi]),
            "imb1": sum(series["imb1"][lo:hi]) / W,
            "imb5": sum(series["imb5"][lo:hi]) / W,
        }
        rows.append((feats, mid[t + H] - mid[t], mid[t] - mid[t - W]))
        t += step
    return rows


def pearson(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx == 0 or syy == 0:
        return 0.0
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / math.sqrt(sxx * syy)


def ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def spearman(x, y):
    return pearson(ranks(x), ranks(y))


def t_stat(r, n):
    if n < 3 or abs(r) >= 1:
        return 0.0
    return r * math.sqrt((n - 2) / (1 - r * r))


def hit_rate(x, y):
    pairs = [(a, b) for a, b in zip(x, y) if a != 0 and b != 0]
    if not pairs:
        return float("nan")
    return 100.0 * sum(1 for a, b in pairs if (a > 0) == (b > 0)) / len(pairs)


def quintile_spread(x, y):
    idx = sorted(range(len(x)), key=lambda i: x[i])
    k = max(1, len(x) // 5)
    bottom = [y[i] for i in idx[:k]]
    top = [y[i] for i in idx[-k:]]
    return statistics.mean(top) - statistics.mean(bottom)


def analyze(path, horizons):
    snaps = load_depth(path)
    print("=" * 74)
    if len(snaps) < 500:
        print(f"{path}: only {len(snaps)} depth snapshots -- record more (>= 5000 recommended).")
        return
    series, mid, spread = compute_series(snaps)
    dts = [snaps[i]["ts"] - snaps[i - 1]["ts"] for i in range(1, len(snaps))]
    med_dt = statistics.median(dts)
    span_min = (snaps[-1]["ts"] - snaps[0]["ts"]) / 60
    print(f"FILE: {path}")
    print(f"snapshots={len(snaps)}  span={span_min:.1f} min  median gap={med_dt * 1000:.0f} ms")
    print(f"median bid-ask spread=${statistics.median(spread):.3f}   "
          f"mid moved ${mid[0]:.2f} -> ${mid[-1]:.2f}")
    print("=" * 74)

    for H in horizons:
        rows = build_samples(series, mid, H, H)
        n = len(rows)
        if n < 30:
            print(f"\nHorizon {H}: only {n} samples -- skipped.")
            continue
        fwd = [r[1] for r in rows]
        contemp = [r[2] for r in rows]
        print(f"\nHorizon {H} snapshots (~{H * med_dt:.1f}s), n={n} samples, "
              f"avg |future move| = ${statistics.mean(abs(v) for v in fwd):.3f}")
        print(f"{'feature':<8}{'contemp r':>10}{'pred r':>9}{'spearman':>10}"
              f"{'t-stat':>8}{'hit %':>8}{'Q5-Q1 $':>10}")
        for name in FEATURES:
            x = [r[0][name] for r in rows]
            r_pred = pearson(x, fwd)
            print(f"{name:<8}{pearson(x, contemp):>10.3f}{r_pred:>9.3f}"
                  f"{spearman(x, fwd):>10.3f}{t_stat(r_pred, n):>8.2f}"
                  f"{hit_rate(x, fwd):>8.1f}{quintile_spread(x, fwd):>+10.3f}")


def main(path, holdout, horizons):
    analyze(path, horizons)
    if holdout:
        analyze(holdout, horizons)
    print("\n" + "-" * 74)
    print("How to read this: 5 features x several horizons = many tests, so a few will")
    print("look 'significant' (|t| > 2) by chance. Only trust a feature whose pred r has")
    print("the SAME sign and similar size on the holdout file. Sanity: 'contemp r' for")
    print("ofi1/ofi5/voi should be clearly positive; if not, something is wrong.")
    print("-" * 74)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--holdout", default=None)
    parser.add_argument("--horizons", default="5,20,50",
                        help="comma-separated horizons in snapshots (~100 ms each)")
    args = parser.parse_args()
    main(args.file, args.holdout, [int(h) for h in args.horizons.split(",")])