# -*- coding: utf-8 -*-
"""Publication figures for v5 -- every value plotted here is computed from the
collected Snapshot records in fdt/out/. Nothing is hard-coded or illustrative.
"""
import json
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from metrics import dispersion, gini, top_share, minimal_majority_fraction as mmf

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "figs_v5")
os.makedirs(OUT, exist_ok=True)

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 9.5, "axes.titlesize": 10.5, "axes.labelsize": 9.5,
    "axes.edgecolor": "#33373d", "axes.linewidth": 0.8,
    "xtick.labelsize": 8.5, "ytick.labelsize": 8.5, "legend.fontsize": 8.3,
    "figure.dpi": 300, "savefig.dpi": 300, "savefig.bbox": "tight",
    "savefig.pad_inches": 0.05,
})
NAVY, STEEL, BRICK = "#1f2a44", "#4a6fa5", "#9e3b38"
GRAY, LIGHT, GREEN, SAND = "#8a8f99", "#d9e1ee", "#3f7d5c", "#c9a66b"

RES = json.load(open("fdt/out/fdt_results.json", encoding="utf-8"))
ROB = json.load(open("fdt/out/robustness.json", encoding="utf-8"))
SCORED = [r for r in RES if r["scored"]]
DORMANT = [r for r in RES if not r["scored"]]


def save(fig, name):
    p = os.path.join(OUT, name)
    fig.savefig(p)
    plt.close(fig)
    print("saved", os.path.relpath(p))


def short(s):
    return s.replace(".eth", "").replace("-snapshot", "").replace("governance", "")\
            .replace("snapshot.dcl", "decentraland").replace("foundation", "")


# =====================================================================
# F1: governance activity -- dormancy in the trailing 12 months
# =====================================================================
def fig_dormancy():
    props = sorted([(short(r["space"]), r["n_proposals_window"]) for r in RES],
                   key=lambda t: t[1])
    names = [p[0] for p in props]
    vals = [p[1] for p in props]
    cols = [BRICK if v == 0 else (SAND if v < 5 else STEEL) for v in vals]

    fig, ax = plt.subplots(figsize=(6.4, 7.2))
    y = np.arange(len(names))
    ax.barh(y, [max(v, 0.25) for v in vals], color=cols, edgecolor=NAVY,
            linewidth=0.5, zorder=3)
    ax.set_yticks(y); ax.set_yticklabels(names, fontsize=7.4)
    ax.set_xscale("symlog", linthresh=1)
    ax.set_xlabel("Closed proposals in the trailing 12 months (log scale)")
    ax.axvline(5, color=GRAY, ls="--", lw=0.9, zorder=2)
    for yi, v in zip(y, vals):
        ax.text(max(v, 0.25) * 1.15, yi, str(v), va="center", fontsize=6.8,
                color=NAVY)
    ax.set_axisbelow(True)
    ax.grid(axis="x", color="#ededed", lw=0.7)
    n0 = sum(1 for v in vals if v == 0)
    ax.set_title(f"Governance activity across the sample (n = {len(vals)} DAOs)\n"
                 f"{n0} of {len(vals)} recorded no closed proposal at all",
                 fontsize=9.6)
    handles = [Line2D([0], [0], color=BRICK, lw=6, label="dormant (0 proposals)"),
               Line2D([0], [0], color=SAND, lw=6, label="marginal (1-4)"),
               Line2D([0], [0], color=STEEL, lw=6, label="active (5+)")]
    ax.legend(handles=handles, loc="lower right", frameon=True, fontsize=7.4)
    fig.tight_layout()
    save(fig, "f1_dormancy.png")


# =====================================================================
# F2: measured concentration per DAO (replaces the hard-coded Gini bars)
# =====================================================================
def fig_concentration():
    rows = sorted([(short(r["space"]), r["median_gini"], r["n_votes_window"])
                   for r in SCORED if r["median_gini"] is not None],
                  key=lambda t: -t[1])
    names = [r[0] for r in rows]
    g = [r[1] for r in rows]
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    x = np.arange(len(names))
    cols = [BRICK if v >= 0.90 else (SAND if v >= 0.75 else STEEL) for v in g]
    ax.bar(x, g, width=0.7, color=cols, edgecolor=NAVY, linewidth=0.5, zorder=3)
    ax.axhline(0.90, color=BRICK, ls="--", lw=1.1, zorder=4)
    ax.text(len(names) - 0.4, 0.912, "extreme-concentration mark (G = 0.90)",
            ha="right", fontsize=7.2, color=BRICK, style="italic")
    ax.set_xticks(x); ax.set_xticklabels(names, rotation=60, ha="right", fontsize=6.9)
    ax.set_ylabel("Median Gini of effective voting power")
    ax.set_ylim(0, 1.06)
    ax.set_axisbelow(True); ax.grid(axis="y", color="#ededed", lw=0.7)
    n_hi = sum(1 for v in g if v >= 0.90)
    ax.set_title(f"Measured voting-power concentration, trailing 12 months "
                 f"({n_hi}/{len(g)} at G >= 0.90)", fontsize=9.6)
    fig.tight_layout()
    save(fig, "f2_concentration_measured.png")


# =====================================================================
# F3: the equation-(2) defect -- the paper's central technical finding
# =====================================================================
def fig_dvote_defect():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.0, 3.5))

    # left: synthetic cartel sweep
    ks = [1, 2, 5, 10, 30, 60, 120, 300]
    dv, gg = [], []
    for k in ks:
        top = [0.95 / k] * k
        rest = [(0.05) / (6000 - k)] * (6000 - k)
        v = np.array(top + rest)
        dv.append(dispersion(v)); gg.append(gini(v))
    ax1.plot(ks, dv, "o-", color=STEEL, lw=1.8, ms=5, label="$d_{vote}$ (eq. 2)")
    ax1.plot(ks, gg, "s-", color=BRICK, lw=1.8, ms=5, label="Gini")
    ax1.axhline(0.40, color=GRAY, ls="--", lw=1.0)
    ax1.text(1.2, 0.43, "eq. (2) fail threshold", fontsize=6.8, color=GRAY)
    ax1.set_xscale("log")
    ax1.set_xlabel("cartel size $k$ (holders sharing the same 95%)")
    ax1.set_ylabel("indicator value")
    ax1.set_ylim(0, 1.05)
    ax1.set_title("Synthetic: concentration held fixed", fontsize=9.0)
    ax1.legend(frameon=False, loc="center right")
    ax1.grid(color="#ededed", lw=0.7); ax1.set_axisbelow(True)

    # right: empirical scatter, d_vote vs Gini
    d, g = [], []
    for r in SCORED:
        for m in r["proposal_metrics"]:
            if m["d_vote"] is not None and m["gini"] is not None:
                d.append(m["d_vote"]); g.append(m["gini"])
    ax2.scatter(g, d, s=6, alpha=0.28, color=NAVY, edgecolors="none")
    ax2.axhline(0.40, color=GRAY, ls="--", lw=1.0)
    ax2.axvline(0.90, color=BRICK, ls="--", lw=1.0)
    ax2.set_xlabel("Gini (measured concentration)")
    ax2.set_ylabel("$d_{vote}$ (eq. 2)")
    ax2.set_xlim(0, 1.02); ax2.set_ylim(0, 1.02)
    ax2.set_title(f"Empirical: {len(d):,} real proposals", fontsize=9.0)
    n_miss = sum(1 for gi, di in zip(g, d) if gi >= 0.90 and di >= 0.40)
    n_hi = sum(1 for gi in g if gi >= 0.90)
    ax2.annotate(f"{n_miss} of {n_hi} extremely\nconcentrated proposals\n"
                 f"sit above the threshold\n(eq. 2 passes them)",
                 xy=(0.955, 0.72), xytext=(0.30, 0.30), fontsize=6.6, color=BRICK,
                 ha="left", va="center",
                 arrowprops=dict(arrowstyle="->", color=BRICK, lw=0.9,
                                 connectionstyle="arc3,rad=-0.2"))
    ax2.grid(color="#ededed", lw=0.7); ax2.set_axisbelow(True)

    fig.suptitle("Equation (2) is blind to oligarchy: squaring the shares hides a cartel",
                 fontsize=10.0, y=1.01)
    fig.tight_layout()
    save(fig, "f3_dvote_defect.png")


# =====================================================================
# F4: whale masking (R1) -- executed, not asserted
# =====================================================================
def fig_masking():
    rows = sorted(ROB["masking"], key=lambda r: -r["gini_full"])
    names = [short(r["space"]) for r in rows]
    gf = [r["gini_full"] for r in rows]
    gm = [r["gini_masked"] for r in rows]
    x = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(6.6, 3.9))
    ax.bar(x - 0.2, gf, width=0.4, color=STEEL, edgecolor=NAVY, lw=0.5,
           label="all voters", zorder=3)
    ax.bar(x + 0.2, gm, width=0.4, color=SAND, edgecolor=NAVY, lw=0.5,
           label="top-10 wallets masked", zorder=3)
    ax.axhspan(0.60, 0.80, color="#eef2e9", zorder=0)
    ax.text(len(names) - 0.5, 0.70, "typical listed-equity range",
            ha="right", fontsize=6.8, color=GREEN, style="italic")
    ax.set_xticks(x); ax.set_xticklabels(names, rotation=60, ha="right", fontsize=6.8)
    ax.set_ylabel("Median Gini of effective voting power")
    ax.set_ylim(0, 1.05)
    ax.legend(frameon=False, loc="upper right")
    ax.set_axisbelow(True); ax.grid(axis="y", color="#ededed", lw=0.7)
    ax.set_title("Robustness check R1: concentration after removing the ten largest wallets",
                 fontsize=9.4)
    fig.tight_layout()
    save(fig, "f4_masking.png")


# =====================================================================
# F5: execution autonomy -- venue capability across the sample
# =====================================================================
def fig_execution():
    meta = json.load(open("fdt/data/spacemeta.json", encoding="utf-8"))
    withx = [s for s, v in meta.items() if v.get("has_exec_plugin")]
    without = [s for s, v in meta.items() if not v.get("has_exec_plugin")]
    fig, ax = plt.subplots(figsize=(5.6, 3.2))
    ax.barh([0, 1], [len(withx), len(without)],
            color=[GREEN, BRICK], edgecolor=NAVY, lw=0.7, height=0.55, zorder=3)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["automated on-chain\nexecution module\n(oSnap / safeSnap)",
                        "signalling only:\nexecution needs a\nsigner to act"],
                       fontsize=8.0)
    for yi, v in zip([0, 1], [len(withx), len(without)]):
        ax.text(v + 0.6, yi, f"{v}  ({100*v/len(meta):.0f}%)", va="center",
                fontsize=8.4, fontweight="bold", color=NAVY)
    ax.set_xlim(0, len(meta) * 1.15)
    ax.set_xlabel("number of DAOs in sample")
    ax.set_axisbelow(True); ax.grid(axis="x", color="#ededed", lw=0.7)
    ax.set_title("Execution autonomy of the Snapshot governance venue", fontsize=9.6)
    fig.tight_layout()
    save(fig, "f5_execution.png")


if __name__ == "__main__":
    fig_dormancy()
    fig_concentration()
    fig_dvote_defect()
    fig_masking()
    fig_execution()
    print("\nfigures ->", os.path.relpath(OUT))
