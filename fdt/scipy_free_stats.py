# -*- coding: utf-8 -*-
"""Spearman rank correlation without a SciPy dependency (average ranks for ties)."""
import numpy as np


def _rankdata(a):
    a = np.asarray(a, float)
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), float)
    sa = a[order]
    i = 0
    while i < len(a):
        j = i
        while j + 1 < len(a) and sa[j + 1] == sa[i]:
            j += 1
        avg = (i + j) / 2.0 + 1.0          # 1-based average rank over the tie block
        ranks[order[i:j + 1]] = avg
        i = j + 1
    return ranks


def spearman(x, y):
    rx, ry = _rankdata(x), _rankdata(y)
    rx = rx - rx.mean()
    ry = ry - ry.mean()
    denom = np.sqrt((rx ** 2).sum() * (ry ** 2).sum())
    return float((rx * ry).sum() / denom) if denom > 0 else float("nan")


if __name__ == "__main__":
    # sanity: perfect monotone relationships and a known tie case
    x = np.array([1, 2, 3, 4, 5], float)
    assert abs(spearman(x, x) - 1.0) < 1e-12
    assert abs(spearman(x, -x) + 1.0) < 1e-12
    assert abs(spearman(np.array([1, 2, 3.]), np.array([1, 1, 2.])) - 0.866) < 0.01
    print("spearman self-tests PASSED")
