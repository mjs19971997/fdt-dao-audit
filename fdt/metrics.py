# -*- coding: utf-8 -*-
"""Concentration and participation metrics for the Functional Decentralization
Test, implemented exactly as specified in the manuscript.

    (1)  HHI    = sum_i s_i^2                      over effective (post-delegation) shares
    (2)  HHI*   = (HHI - 1/n) / (1 - 1/n)          normalized to [0, 1]
         d_vote = 1 - HHI*                         dispersion score (high = dispersed)
    (3)  FDT    = sum_k 1[x_k < tau_k]             flag functionally centralized if FDT >= 3

Also provides the Gini coefficient and the Nakamoto coefficient so results are
directly comparable with the published measurement literature.
"""
from __future__ import annotations
import numpy as np


def _clean(vp) -> np.ndarray:
    """Strictly positive voting powers, descending. Zero-vp votes carry no power
    and would distort n in the HHI normalization, so they are dropped."""
    a = np.asarray([float(x) for x in vp], dtype=float)
    a = a[np.isfinite(a) & (a > 0)]
    return np.sort(a)[::-1]


def shares(vp) -> np.ndarray:
    a = _clean(vp)
    tot = a.sum()
    return a / tot if tot > 0 else a


def hhi(vp) -> float | None:
    """Equation (1). Ranges 1/n (uniform) .. 1 (single holder)."""
    s = shares(vp)
    if s.size == 0:
        return None
    return float(np.sum(s ** 2))


def hhi_normalized(vp) -> float | None:
    """Equation (2), first part. Undefined for n = 1 (no dispersion to measure)."""
    s = shares(vp)
    n = s.size
    if n <= 1:
        return None
    h = float(np.sum(s ** 2))
    return float((h - 1.0 / n) / (1.0 - 1.0 / n))


def dispersion(vp) -> float | None:
    """Equation (2), second part: d_vote = 1 - HHI*."""
    hn = hhi_normalized(vp)
    return None if hn is None else float(1.0 - hn)


def gini(vp) -> float | None:
    """Gini coefficient of effective voting power (0 = equal, ->1 = concentrated).

    Uses the standard covariance/rank form on the ascending-sorted vector."""
    a = np.sort(_clean(vp))
    n = a.size
    if n == 0:
        return None
    if n == 1:
        return 0.0
    tot = a.sum()
    if tot <= 0:
        return None
    idx = np.arange(1, n + 1)
    return float((2.0 * np.sum(idx * a)) / (n * tot) - (n + 1.0) / n)


def nakamoto(vp, threshold: float = 0.5) -> int | None:
    """Smallest number of addresses whose combined effective voting power exceeds
    `threshold` of the total. Default 0.5, matching the delegated-voting-power
    convention used in the literature we benchmark against."""
    s = shares(vp)
    if s.size == 0:
        return None
    c = np.cumsum(s)
    # side="right" so that a cumulative share landing exactly on the threshold
    # does not count as exceeding it (4 equal holders => 3, not 2).
    return int(np.searchsorted(c, threshold, side="right") + 1)


def top_share(vp, frac: float = 0.01) -> float | None:
    """Share of total effective voting power held by the top `frac` of addresses
    (at least one address)."""
    s = shares(vp)
    n = s.size
    if n == 0:
        return None
    k = max(1, int(np.ceil(n * frac)))
    return float(np.sum(s[:k]))


def minimal_majority_fraction(vp, threshold: float = 0.5) -> float | None:
    """MMF: the fraction of participating addresses needed to control `threshold`
    of effective voting power, i.e. Nakamoto / n.

    Proposed replacement for d_vote (eq. 2). Unlike HHI it does not square the
    shares, so it is not blinded by a cartel: moving the same power from 1 holder
    to k holders leaves MMF ~ k/2n, still tiny. Ranges from ~0 (captured) to 0.5
    (every voter equal). Higher = more dispersed, matching eq. (3)'s orientation."""
    s = shares(vp)
    n = s.size
    if n <= 1:
        return None
    nak = nakamoto(vp, threshold)
    return None if nak is None else float(nak / n)


def hhi_masked(vp, mask_top: int = 10) -> float | None:
    """Manuscript robustness check: re-estimate HHI after removing the largest
    `mask_top` wallets, to test how much concentration rides on a few whales."""
    a = _clean(vp)
    if a.size <= mask_top + 1:
        return None
    return hhi(a[mask_top:])


# ---------------------------------------------------------------------------
# self-tests: distributions whose values are known analytically
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    ok = True

    def check(label, got, want, tol=1e-9):
        global ok
        good = got is not None and abs(got - want) < tol
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  {label:<44} got={got!r} want={want}")

    print("HHI (1)")
    check("single holder -> 1.0", hhi([100.0]), 1.0)
    check("4 equal holders -> 1/4", hhi([1, 1, 1, 1]), 0.25)
    check("10 equal holders -> 1/10", hhi([1] * 10), 0.10)
    check("[3,1] -> 0.5^2+... = 0.625", hhi([3, 1]), 0.625)

    print("normalized HHI + dispersion (2)")
    check("uniform n=4 -> HHI*=0", hhi_normalized([1, 1, 1, 1]), 0.0)
    check("uniform n=4 -> d_vote=1", dispersion([1, 1, 1, 1]), 1.0)
    check("near-monopoly -> HHI*~1", hhi_normalized([1e9, 1e-6, 1e-6]), 1.0, tol=1e-5)
    check("n=1 -> undefined", 1.0 if hhi_normalized([5]) is None else 0.0, 1.0)

    print("Gini")
    check("perfect equality -> 0", gini([1, 1, 1, 1]), 0.0)
    check("two holders [0,1] -> 0.5", gini([0.0001, 1]), 0.5, tol=1e-3)
    check("n=1 -> 0", gini([7]), 0.0)

    print("Nakamoto")
    check("4 equal, 50% -> 3", nakamoto([1, 1, 1, 1]), 3)
    check("one holder 60% -> 1", nakamoto([60, 10, 10, 10, 10]), 1)
    check("two holders 30+30 -> 2", nakamoto([30, 30, 20, 20]), 2)

    print("top_share / masking")
    check("top1% of 100 equal -> 0.01", top_share([1] * 100, 0.01), 0.01)
    check("mask top10 of 11 equal -> None-guard", 1.0 if hhi_masked([1] * 11) is None else 0.0, 1.0)
    check("mask top10 of 20 equal -> 0.1", hhi_masked([1] * 20), 0.1)

    print()
    print("ALL METRIC SELF-TESTS PASSED" if ok else "SOME TESTS FAILED")
