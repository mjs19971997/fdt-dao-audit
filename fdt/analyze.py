# -*- coding: utf-8 -*-
"""Run the Functional Decentralization Test over the collected Snapshot data.

Scoring follows Table II of the manuscript exactly:

  D3 voting dispersion  fail if d_vote < 0.40 OR G >= 0.90 OR N <= 4 OR top1% >= 0.50
  D4 participation      fail if median turnout T < 10% of eligible voting power
                        OR turnout is not persistent across a 3-proposal window
  D5 execution autonomy fail if E < 0.90

  D1 upgrade control    NOT SCORED HERE -- requires protocol-specific contract
  D2 treasury control   inspection; see onchain.py for the curated subset.

Every value written by this module is computed from collected API records. Where
a quantity cannot be measured it is emitted as None and excluded, never imputed.
"""
from __future__ import annotations
import json
import os
import statistics as st

import numpy as np

from metrics import (hhi, hhi_normalized, dispersion, gini, nakamoto,
                     top_share, hhi_masked)

RAW = "fdt/data/raw"
STUDY_CUTOFF = 1752451200

# ---- Table II thresholds --------------------------------------------------
TAU_DISPERSION = 0.40
TAU_GINI = 0.90
TAU_NAKAMOTO = 4
TAU_TOP1 = 0.50
TAU_TURNOUT = 0.10
TAU_EXEC = 0.90
MIN_PROPOSALS = 3          # need a 3-proposal window to judge persistence


def proposal_metrics(p):
    """Concentration metrics for one proposal, over effective post-delegation vp."""
    vps = [v["vp"] for v in p.get("votes") or []]
    vps = [x for x in vps if isinstance(x, (int, float)) and x > 0]
    n = len(vps)
    if n == 0:
        return None
    return {
        "proposal": p["id"],
        "created": p["created"],
        "n_voters": n,
        "votes_reported": p.get("votes_reported"),
        "vp_total": float(sum(vps)),
        "hhi": hhi(vps),
        "hhi_star": hhi_normalized(vps),
        "d_vote": dispersion(vps),
        "gini": gini(vps),
        "nakamoto": nakamoto(vps, 0.5),
        "top1_share": top_share(vps, 0.01),
        "top10_share": top_share(vps, 0.10),
        "hhi_masked10": hhi_masked(vps, 10),
        "scores_total": p.get("scores_total"),
    }


def turnout_series(pms, total_supply):
    """Turnout per proposal = effective voting power cast / total token supply.

    Total supply is an upper bound on eligible voting power, so this is a
    conservative (lower-bound) turnout. Returns None when supply is unknown."""
    if not total_supply or total_supply <= 0:
        return None
    return [min(1.0, m["vp_total"] / total_supply) for m in pms]


def persistent(turnouts, tau=TAU_TURNOUT, window=3):
    """Turnout is 'persistent' if every proposal in the most recent `window`
    clears the threshold. Fewer than `window` proposals -> cannot judge."""
    if turnouts is None or len(turnouts) < window:
        return None
    return all(t >= tau for t in turnouts[-window:])


def score_space(space, rec, meta):
    pms = [m for m in (proposal_metrics(p) for p in rec["proposals"]) if m]
    pms.sort(key=lambda m: m["created"])
    n_props = len(pms)

    out = {
        "space": space,
        "name": (meta or {}).get("name"),
        "n_proposals_window": n_props,
        "n_votes_window": int(sum(m["n_voters"] for m in pms)),
        "dormant": n_props == 0,
        "proposal_metrics": pms,
    }
    if n_props == 0:
        out["scored"] = False
        out["reason"] = "no closed proposals in trailing 12 months"
        return out

    # ---- D3 voting dispersion (median across proposals) -------------------
    med = lambda k: st.median([m[k] for m in pms if m[k] is not None]) \
        if any(m[k] is not None for m in pms) else None
    d_vote = med("d_vote")
    g = med("gini")
    nak = med("nakamoto")
    t1 = med("top1_share")

    d3_fail = None
    if all(v is not None for v in (d_vote, g, nak, t1)):
        d3_fail = bool(d_vote < TAU_DISPERSION or g >= TAU_GINI
                       or nak <= TAU_NAKAMOTO or t1 >= TAU_TOP1)

    # ---- D4 participation depth -------------------------------------------
    supply = (meta or {}).get("token_total_supply")
    tos = turnout_series(pms, supply)
    med_turnout = st.median(tos) if tos else None
    pers = persistent(tos)
    d4_fail = None
    if med_turnout is not None:
        d4_fail = bool(med_turnout < TAU_TURNOUT or pers is False)

    # ---- D5 execution autonomy (venue-level; NOT scored as a pass/fail) ----
    # Absence of an execution module means THIS venue cannot push a passed
    # proposal on-chain without a signer choosing to act. It does NOT establish
    # E = 0 for the DAO: several protocols (Uniswap, Compound, ENS) run a binding
    # on-chain Governor and use Snapshot only for advisory temperature checks.
    # Distinguishing advisory from binding venues needs per-protocol Governor
    # addresses, which are not derivable from public space metadata, so we record
    # the venue property and leave the dimension unscored rather than guess.
    has_exec = (meta or {}).get("has_exec_plugin")
    d5_fail = None
    if has_exec is True:
        e_val, e_basis = None, (
            f"execution module present ({','.join((meta or {}).get('exec_plugins') or [])}); "
            "per-proposal execution rate not measured")
    elif has_exec is False:
        e_val, e_basis = None, (
            "no execution module: this venue is signalling-only. Binding execution "
            "may occur via a separate on-chain governor (not observable here)")
    else:
        e_val, e_basis = None, "unknown"

    fails = [f for f in (d3_fail, d4_fail, d5_fail) if f is True]
    unknown = [f for f in (d3_fail, d4_fail, d5_fail) if f is None]

    out.update({
        "scored": True,
        "median_d_vote": d_vote, "median_gini": g,
        "median_nakamoto": nak, "median_top1_share": t1,
        "median_hhi": med("hhi"), "median_hhi_masked10": med("hhi_masked10"),
        "median_n_voters": med("n_voters"),
        "token_total_supply": supply,
        "median_turnout": med_turnout,
        "turnout_persistent": pers,
        "has_exec_plugin": has_exec,
        "exec_value": e_val, "exec_basis": e_basis,
        "D3_dispersion_fail": d3_fail,
        "D4_participation_fail": d4_fail,
        "D5_execution_fail": d5_fail,
        "n_fails_measured": len(fails),
        "n_unknown": len(unknown),
    })
    return out


def main():
    with open("fdt/data/spacemeta.json", encoding="utf-8") as f:
        metas = json.load(f)

    results = []
    for fn in sorted(os.listdir(RAW)):
        if not fn.endswith(".json"):
            continue
        space = fn[:-5]
        with open(os.path.join(RAW, fn), encoding="utf-8") as f:
            rec = json.load(f)
        results.append(score_space(space, rec, metas.get(space)))

    scored = [r for r in results if r["scored"]]
    dormant = [r for r in results if not r["scored"]]

    print(f"{'space':<26} {'props':>5} {'voters':>7} {'d_vote':>7} {'gini':>6} "
          f"{'nak':>4} {'top1%':>6} {'turnout':>8} {'exec':>5} {'fails':>6}")
    print("-" * 96)
    for r in sorted(scored, key=lambda x: -(x["n_votes_window"] or 0)):
        f = lambda v, p=2: "-" if v is None else f"{v:.{p}f}"
        print(f"{r['space']:<26} {r['n_proposals_window']:>5} "
              f"{r['n_votes_window']:>7,} {f(r['median_d_vote'],3):>7} "
              f"{f(r['median_gini'],3):>6} "
              f"{'-' if r['median_nakamoto'] is None else int(r['median_nakamoto']):>4} "
              f"{f(r['median_top1_share'],3):>6} "
              f"{'-' if r['median_turnout'] is None else format(r['median_turnout'],'.4f'):>8} "
              f"{str(r['has_exec_plugin']):>5} {r['n_fails_measured']:>6}")

    print()
    print(f"scored spaces        : {len(scored)}")
    print(f"dormant (0 proposals): {len(dormant)}  {[d['space'] for d in dormant]}")

    with open("fdt/out/fdt_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("\nwrote fdt/out/fdt_results.json")


if __name__ == "__main__":
    os.makedirs("fdt/out", exist_ok=True)
    main()
