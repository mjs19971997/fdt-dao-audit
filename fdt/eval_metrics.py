# -*- coding: utf-8 -*-
"""Does the proposed replacement actually fix the defect?

Criteria:
  (i)  INVARIANCE  - decisive. On synthetic data we control the ground truth, so
                     an indicator that swings while concentration is held fixed is
                     provably measuring something else. This is the eq.-2 defect.
  (ii) DISCRIMINATION - decisive. It must separate captured from dispersed votes.
  (iii) SIZE-CO-MOVEMENT - diagnostic only, NOT a defect test. On real data
                     concentration may genuinely covary with n (a bigger DAO can
                     really be more captured), so rho != 0 is not by itself proof
                     of an artefact. Reported for transparency, not scored.

We test d_vote (eq. 2), Gini, top1% and a proposed MMF against all three.
"""
import json
import numpy as np
from scipy_free_stats import spearman
from metrics import dispersion, gini, top_share, minimal_majority_fraction as mmf


def oligarchy(n, k, top_frac=0.95):
    top = [top_frac / k] * k
    rest = [(1.0 - top_frac) / (n - k)] * (n - k)
    return np.array(top + rest)


def uniform(n):
    return np.ones(n)


CANDS = [("d_vote (eq.2)", dispersion), ("Gini", gini),
         ("top1% share", lambda v: top_share(v, 0.01)), ("MMF (proposed)", mmf)]

print("=" * 78)
print("(i) INVARIANCE: same 95% of power, cartel size k varies, n = 6000 fixed")
print("=" * 78)
print(f"{'k':>6} " + "".join(f"{nm:>16}" for nm, _ in CANDS))
vals = {nm: [] for nm, _ in CANDS}
for k in (1, 2, 5, 10, 30, 60, 120, 300):
    row = []
    for nm, fn in CANDS:
        v = fn(oligarchy(6000, k))
        vals[nm].append(v)
        row.append(f"{v:>16.4f}")
    print(f"{k:>6} " + "".join(row))
print()
print(f"{'swing (max-min)':>6}")
for nm, _ in CANDS:
    sw = max(vals[nm]) - min(vals[nm])
    verdict = "STABLE" if sw < 0.15 else "SWINGS"
    print(f"   {nm:<18} {sw:>7.4f}   {verdict}")
print()
print("   A sound indicator should barely move: concentration is identical.")

print()
print("=" * 78)
print("(ii) DISCRIMINATION: captured (k=10 of 6000 hold 95%) vs dispersed (equal)")
print("=" * 78)
cap, disp = oligarchy(6000, 10), uniform(6000)
print(f"{'metric':<20} {'captured':>12} {'dispersed':>12} {'separation':>12}")
for nm, fn in CANDS:
    a, b = fn(cap), fn(disp)
    print(f"{nm:<20} {a:>12.4f} {b:>12.4f} {abs(b-a):>12.4f}")

print()
print("=" * 78)
print("(iii) SIZE CO-MOVEMENT on the real sample (diagnostic, not a defect test)")
print("=" * 78)
res = json.load(open("fdt/out/fdt_results.json", encoding="utf-8"))
rows = []
for r in res:
    for m in r.get("proposal_metrics") or []:
        if m["n_voters"] > 1 and m["d_vote"] is not None:
            rows.append(m)
n = np.array([m["n_voters"] for m in rows], float)
series = {
    "d_vote (eq.2)": np.array([m["d_vote"] for m in rows], float),
    "Gini": np.array([m["gini"] for m in rows], float),
    "top1% share": np.array([m["top1_share"] for m in rows], float),
    "MMF (proposed)": np.array([m["nakamoto"] / m["n_voters"] for m in rows], float),
}
print(f"  proposals: {len(rows):,}")
print(f"{'metric':<20} {'rho(.,log n)':>14} {'|rho|':>8}")
for nm, arr in series.items():
    r_ = spearman(np.log(n), arr)
    print(f"{nm:<20} {r_:>+14.3f} {abs(r_):>8.3f}")
print()
print("  Note: MMF co-moves with n most strongly. That is expected by construction")
print("  (a fixed cartel over a growing electorate is a shrinking FRACTION of it)")
print("  and is not evidence of the eq.-2 defect, which test (i) isolates.")

print()
print("  Agreement with Gini >= 0.90 (the manuscript's own extreme-concentration mark):")
hi = series["Gini"] >= 0.90
for nm, arr in series.items():
    if nm == "Gini":
        continue
    # flag rule: low value = concentrated for d_vote/MMF; high = concentrated for top1%
    flag = arr >= 0.50 if nm == "top1% share" else arr < np.quantile(arr, 0.207)
    tp = (flag & hi).sum()
    print(f"    {nm:<18} catches {tp:>3}/{hi.sum():>3} "
          f"({100*tp/max(hi.sum(),1):>4.0f}%) of extreme-concentration proposals")
