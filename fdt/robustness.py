# -*- coding: utf-8 -*-
"""The two robustness checks the manuscript promises, actually executed.

(R1) Whale masking: re-estimate concentration after removing the ten largest
     wallets from each proposal. The manuscript asserts "concentration falls
     under masking but remains well above public-equity benchmarks." We test it.

(R2) Leave-one-DAO-out: recompute the ecosystem-level medians 30 times, each time
     dropping one DAO, to confirm no single protocol drives the result.

Both operate only on collected data; nothing is imputed.
"""
import json
import numpy as np
import statistics as st

from metrics import gini, hhi, dispersion, top_share

RES = "fdt/out/fdt_results.json"


def load_props():
    res = json.load(open(RES, encoding="utf-8"))
    return [r for r in res if r.get("scored")]


def raw_vps():
    """Reload raw vp vectors (the results file keeps only summaries)."""
    import os
    out = {}
    for fn in sorted(os.listdir("fdt/data/raw")):
        rec = json.load(open(f"fdt/data/raw/{fn}", encoding="utf-8"))
        vs = []
        for p in rec["proposals"]:
            v = [x["vp"] for x in p.get("votes") or []
                 if isinstance(x["vp"], (int, float)) and x["vp"] > 0]
            if len(v) > 11:          # need >10 to mask 10 and still measure
                vs.append(v)
        if vs:
            out[fn[:-5]] = vs
    return out


print("=" * 78)
print("(R1) WHALE MASKING: drop the 10 largest wallets per proposal")
print("=" * 78)
data = raw_vps()
rows = []
for space, props in sorted(data.items()):
    g_full, g_mask, n_ok = [], [], 0
    for v in props:
        a = sorted(v, reverse=True)
        if len(a) <= 11:
            continue
        gf, gm = gini(a), gini(a[10:])
        if gf is None or gm is None:
            continue
        g_full.append(gf); g_mask.append(gm); n_ok += 1
    if n_ok == 0:
        continue
    rows.append((space, n_ok, st.median(g_full), st.median(g_mask)))

print(f"{'space':<24} {'props':>6} {'Gini full':>10} {'Gini masked':>12} {'drop':>8}")
print("-" * 66)
for sp, k, gf, gm in sorted(rows, key=lambda r: -r[2]):
    print(f"{sp:<24} {k:>6} {gf:>10.4f} {gm:>12.4f} {gf-gm:>+8.4f}")

gf_all = [r[2] for r in rows]
gm_all = [r[3] for r in rows]
print()
print(f"  DAOs with >10 voters on >=1 proposal : {len(rows)}")
print(f"  median Gini, full                    : {st.median(gf_all):.4f}")
print(f"  median Gini, top-10 masked           : {st.median(gm_all):.4f}")
print(f"  median drop                          : {st.median(gf_all)-st.median(gm_all):+.4f}")
still_high = sum(1 for g in gm_all if g >= 0.60)
print(f"  DAOs still at Gini >= 0.60 after masking: {still_high}/{len(rows)}")
print()
print("  Benchmark note: listed-equity ownership Gini is typically ~0.6-0.8, so")
print("  'well above public-equity benchmarks' is NOT supported for every DAO;")
print("  the honest statement is the per-DAO distribution printed above.")

print()
print("=" * 78)
print("(R2) LEAVE-ONE-DAO-OUT on the ecosystem medians")
print("=" * 78)
scored = load_props()
def eco(sel):
    g = [r["median_gini"] for r in sel if r["median_gini"] is not None]
    d = [r["median_d_vote"] for r in sel if r["median_d_vote"] is not None]
    return st.median(g), st.median(d)

base_g, base_d = eco(scored)
print(f"  full sample (k={len(scored)}): median Gini={base_g:.4f}  median d_vote={base_d:.4f}")
swings_g, swings_d = [], []
for i, r in enumerate(scored):
    sel = scored[:i] + scored[i + 1:]
    g, d = eco(sel)
    swings_g.append(abs(g - base_g)); swings_d.append(abs(d - base_d))
worst = max(range(len(scored)), key=lambda i: swings_g[i])
print(f"  max |delta median Gini| when dropping any single DAO : "
      f"{max(swings_g):.4f}  (worst: {scored[worst]['space']})")
print(f"  max |delta median d_vote| when dropping any single DAO: {max(swings_d):.4f}")
print()
print("  -> the ecosystem-level result is not an artefact of any one protocol"
      if max(swings_g) < 0.05 else
      "  -> WARNING: a single DAO materially moves the ecosystem median")

json.dump({"masking": [{"space": s, "n_props": k, "gini_full": gf,
                        "gini_masked": gm} for s, k, gf, gm in rows],
           "loo": {"base_gini": base_g, "base_d_vote": base_d,
                   "max_delta_gini": max(swings_g),
                   "max_delta_d_vote": max(swings_d)}},
          open("fdt/out/robustness.json", "w", encoding="utf-8"), indent=2)
print("\nwrote fdt/out/robustness.json")
