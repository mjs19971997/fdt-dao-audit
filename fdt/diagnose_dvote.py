# -*- coding: utf-8 -*-
"""Diagnostic: is the manuscript's d_vote (eq. 2) actually measuring dispersion,
or is it dominated by the voter count n?

Equation (2) normalizes HHI as HHI* = (HHI - 1/n)/(1 - 1/n) and sets
d_vote = 1 - HHI*. HHI is a sum of SQUARED shares, so it is driven by whether any
single holder is large. That makes it blind to oligarchy: a cartel of k holders
splitting the same power between them drives every squared term down, and d_vote
rises toward 1, even though the power is held by a vanishing fraction of voters.

Three tests:
 (A1) Synthetic single whale: one holder owns 95%, n varies. HHI should catch this.
 (A2) Synthetic oligarchy: the top k holders split 95% evenly, n fixed, k varies.
      Concentration among voters stays extreme; only its shape changes.
 (B)  Empirical: correlate d_vote against log(n), Gini and top1% across the real
      per-proposal measurements we collected.
"""
import json
import numpy as np
from scipy_free_stats import spearman          # local, dependency-free
from metrics import dispersion, gini, hhi, top_share


def synth_whale(n, top_frac=0.95):
    """One whale holds `top_frac`; the remainder is split evenly over n-1 others."""
    if n < 2:
        return None
    rest = (1.0 - top_frac) / (n - 1)
    return np.array([top_frac] + [rest] * (n - 1))


def synth_oligarchy(n, k, top_frac=0.95):
    """Top `k` holders split `top_frac` evenly; the other n-k split the remainder."""
    if n <= k:
        return None
    top = [top_frac / k] * k
    rest = [(1.0 - top_frac) / (n - k)] * (n - k)
    return np.array(top + rest)


print("=" * 78)
print("(A1) SYNTHETIC single whale: one holder = 95%. n varies.")
print("=" * 78)
print(f"{'n':>8} {'HHI':>10} {'d_vote (eq.2)':>15} {'Gini':>8} {'top1%':>8}")
for n in (5, 10, 50, 100, 500, 1000, 5000, 20000, 100000):
    v = synth_whale(n)
    print(f"{n:>8} {hhi(v):>10.5f} {dispersion(v):>15.5f} {gini(v):>8.4f} "
          f"{top_share(v, 0.01):>8.4f}")
print()
print("    Reading: with a single dominant holder, d_vote stays ~0.10 at every n.")
print("    Equation (2) DOES detect this shape. It is not simply an n artefact.")

print()
print("=" * 78)
print("(A2) SYNTHETIC oligarchy: top k holders split the SAME 95%. n = 6000 fixed.")
print("     Voter-side concentration stays extreme; only the cartel size changes.")
print("=" * 78)
print(f"{'k':>8} {'HHI':>10} {'d_vote (eq.2)':>15} {'Gini':>8} {'top1%':>8} "
      f"{'flagged?':>10}")
for k in (1, 2, 5, 10, 30, 60, 120, 300):
    v = synth_oligarchy(6000, k)
    d, g = dispersion(v), gini(v)
    print(f"{k:>8} {hhi(v):>10.5f} {d:>15.5f} {g:>8.4f} "
          f"{top_share(v, 0.01):>8.4f} {'FAIL' if d < 0.40 else 'pass':>10}")
print()
print("    Reading: the same 95% of voting power, held by 1 vs 60 addresses out of")
print("    6000, moves d_vote from ~0.10 (flagged) to ~0.98 (passes) while Gini")
print("    stays ~0.95. Squaring the shares hides a cartel. This is the failure")
print("    mode that matters empirically: real DAOs look like (A2), not (A1).")

print()
print("=" * 78)
print("(B) EMPIRICAL: real per-proposal measurements from the collected sample")
print("=" * 78)
res = json.load(open("fdt/out/fdt_results.json", encoding="utf-8"))
rows = []
for r in res:
    for m in r.get("proposal_metrics") or []:
        if m["d_vote"] is not None and m["gini"] is not None and m["n_voters"] > 1:
            rows.append((m["n_voters"], m["d_vote"], m["gini"], m["top1_share"]))

n = np.array([r[0] for r in rows], float)
d = np.array([r[1] for r in rows], float)
g = np.array([r[2] for r in rows], float)
t1 = np.array([r[3] for r in rows], float)
print(f"  proposals with a computable d_vote: {len(rows):,}")
print()
print(f"  Spearman rho(d_vote, log n)  = {spearman(np.log(n), d):+.3f}   "
      f"<- should be ~0 if d_vote measures shape, not size")
print(f"  Spearman rho(d_vote, Gini)   = {spearman(g, d):+.3f}   "
      f"<- should be strongly negative if d_vote tracks concentration")
print(f"  Spearman rho(d_vote, top1%)  = {spearman(t1, d):+.3f}")
print(f"  Spearman rho(Gini,   log n)  = {spearman(np.log(n), g):+.3f}   "
      f"<- Gini's own size-dependence, for comparison")

print()
print("  d_vote by voter-count decile (median):")
qs = np.quantile(n, np.linspace(0, 1, 11))
for i in range(10):
    sel = (n >= qs[i]) & (n <= qs[i + 1])
    if sel.sum() == 0:
        continue
    print(f"    n in [{qs[i]:>8.0f},{qs[i+1]:>8.0f}]  "
          f"median d_vote={np.median(d[sel]):.3f}  median Gini={np.median(g[sel]):.3f}  "
          f"(k={sel.sum()})")

print()
print("=" * 78)
print("(C) How often does the manuscript's threshold d_vote < 0.40 actually fire?")
print("=" * 78)
fire = (d < 0.40).sum()
print(f"  proposals flagged by d_vote < 0.40 : {fire:,} / {len(d):,} "
      f"({100*fire/len(d):.1f}%)")
hi_conc = (g >= 0.90)
print(f"  proposals with Gini >= 0.90        : {hi_conc.sum():,} "
      f"({100*hi_conc.mean():.1f}%)")
both = ((d < 0.40) & hi_conc).sum()
print(f"  extreme concentration (Gini>=0.90) that d_vote ALSO flags: "
      f"{both:,} / {hi_conc.sum():,} ({100*both/max(hi_conc.sum(),1):.1f}%)")
print(f"  -> d_vote misses {hi_conc.sum()-both:,} of {hi_conc.sum():,} "
      f"extremely concentrated proposals "
      f"({100*(hi_conc.sum()-both)/max(hi_conc.sum(),1):.0f}%)")
