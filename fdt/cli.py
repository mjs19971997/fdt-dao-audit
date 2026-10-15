# -*- coding: utf-8 -*-
"""fdt: command-line interface to the Functional Decentralization Test.

Subcommands
-----------
  selftest              run the analytic metric self-tests and exit non-zero on failure
  audit SPACE [...]     collect one Snapshot space over a trailing window, score it,
                        print a human-readable report, and write a JSON record
  score                 re-score every cached space in data/raw (offline)

The audit path reuses the exact collection and scoring code the paper's
ecosystem study ran (`collect.py`, `analyze.py`); this file adds argument
parsing, a single-space driver, and a report printer, nothing else. That is
deliberate: an auditor running `fdt audit somedao.eth` exercises the same code
path the published results came from.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import collect                                    # noqa: E402
import metrics as M                               # noqa: E402
from analyze import score_space                   # noqa: E402
from spacemeta import SPACE_Q, token_from_strategies, rpc_call, EXEC_PLUGINS  # noqa: E402

import requests                                   # noqa: E402

HUB = "https://hub.snapshot.org/graphql"
HDRS = {"Content-Type": "application/json", "User-Agent": "fdt-cli/0.1"}


def fetch_space_meta(space: str) -> dict | None:
    """Space-level metadata for one space: plugins, token, supply."""
    r = requests.post(HUB, headers=HDRS,
                      json={"query": SPACE_Q, "variables": {"ids": [space]}},
                      timeout=60)
    r.raise_for_status()
    rows = (r.json().get("data") or {}).get("spaces") or []
    if not rows:
        return None
    s = rows[0]
    plugins = list((s.get("plugins") or {}).keys()) if isinstance(s.get("plugins"), dict) \
        else list(s.get("plugins") or [])
    tok = token_from_strategies(s.get("strategies"))
    supply = None
    if tok:
        raw = rpc_call(tok.get("network") or 1, tok["address"], "0x18160ddd")
        if raw is not None:
            supply = raw / (10 ** int(tok.get("decimals") or 18))
    return {"name": s.get("name"), "network": s.get("network"),
            "symbol": s.get("symbol"), "followers": s.get("followersCount"),
            "proposals_all_time": s.get("proposalsCount"),
            "votes_all_time": s.get("votesCount"),
            "plugins": plugins,
            "has_exec_plugin": bool(set(plugins) & EXEC_PLUGINS),
            "exec_plugins": sorted(set(plugins) & EXEC_PLUGINS),
            "treasuries": s.get("treasuries") or [],
            "token": tok, "token_total_supply": supply,
            "supply_measured_at": "latest"}


def audit(space: str, months: int, out_dir: str, quiet: bool) -> int:
    t0 = time.time()
    window_start = int(time.time()) - months * 30 * 86400
    collect.WINDOW_START = window_start          # the driver owns the window

    say = (lambda *a: None) if quiet else print
    say(f"fdt audit {space}  (trailing {months} months)")
    say("  fetching space metadata ...")
    meta = fetch_space_meta(space)
    if meta is None:
        print(f"error: space {space!r} not found on the hub", file=sys.stderr)
        return 2

    say("  fetching proposals ...")
    props = collect.fetch_proposals(space)
    say(f"  {len(props)} closed proposals in window; fetching votes ...")
    rec = {"space": space, "window_start": window_start,
           "study_cutoff": int(time.time()), "proposals": []}
    nv = 0
    for p in props:
        votes = collect.fetch_votes(p["id"]) if (p["votes"] or 0) > 0 else []
        nv += len(votes)
        rec["proposals"].append({
            "id": p["id"], "created": p["created"], "start": p["start"],
            "end": p["end"], "title": p["title"], "type": p["type"],
            "quorum": p["quorum"], "snapshot": p["snapshot"],
            "author": p["author"], "choices": p["choices"],
            "scores": p["scores"], "scores_total": p["scores_total"],
            "votes_reported": p["votes"], "votes_collected": len(votes),
            "strategies": p["strategies"],
            "votes": [{"voter": v["voter"], "vp": v["vp"],
                       "created": v["created"], "choice": v["choice"]}
                      for v in votes]})
    say(f"  {nv:,} votes collected in {time.time()-t0:.0f}s; scoring ...")

    result = score_space(space, rec, meta)

    os.makedirs(out_dir, exist_ok=True)
    raw_path = os.path.join(out_dir, f"{space}.json")
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(rec, f)
    res_path = os.path.join(out_dir, f"{space}.fdt.json")
    slim = {k: v for k, v in result.items() if k != "proposal_metrics"}
    slim["n_proposal_metrics"] = len(result.get("proposal_metrics") or [])
    with open(res_path, "w", encoding="utf-8") as f:
        json.dump(slim, f, indent=2)

    _report(space, meta, result, nv, time.time() - t0, raw_path, res_path)
    return 0


def _fmt(v, p=3):
    return "unmeasured" if v is None else f"{v:.{p}f}"


def _report(space, meta, r, nv, secs, raw_path, res_path):
    W = 66
    print("=" * W)
    print(f"FDT audit report: {space}")
    print("=" * W)
    print(f"window                 : trailing, {r['n_proposals_window']} scoreable proposals")
    print(f"votes (positive power) : {r['n_votes_window']:,}  (collected {nv:,})")
    if r.get("dormant"):
        print("\nVERDICT: GOVERNANCE-DORMANT — no closed proposal in window.")
        print("A dormant electorate with live contracts is a finding, not a pass.")
    else:
        print("-" * W)
        print("D3 voting dispersion   (fail if Gini >= 0.90, N <= 4, or top-1% >= 50%)")
        print(f"    median Gini        : {_fmt(r['median_gini'])}")
        nk = r["median_nakamoto"]
        print(f"    median Nakamoto    : {'unmeasured' if nk is None else int(nk)}  (addresses deciding a majority of cast votes)")
        print(f"    median top-1% share: {_fmt(r['median_top1_share'])}")
        print(f"    -> {'FAIL' if r['D3_dispersion_fail'] else ('pass' if r['D3_dispersion_fail'] is not None else 'unmeasured')}")
        print("D4 participation depth (turnout unscored: no defensible denominator)")
        mv = r["median_n_voters"]
        print(f"    median unique voters per proposal: {'unmeasured' if mv is None else int(mv)}")
        print("D5 execution autonomy  (venue-level, unscored)")
        print(f"    execution module   : {', '.join(r.get('exec_basis','').split(';')[:1]) or 'unknown'}")
        print("D1 upgrade control / D2 treasury control: not automatable from public")
        print("    metadata; see the paper's Table 5 and onchain.py for declared Safes.")
        print("-" * W)
        print(f"measured failures      : {r['n_fails_measured']}  (of the dimensions measurable here)")
    print(f"wall-clock             : {secs:.0f}s")
    print(f"raw record             : {raw_path}")
    print(f"scored result          : {res_path}")
    print("=" * W)


def score_all(raw_dir: str) -> int:
    metas = {}
    sm = os.path.join(HERE, "data", "spacemeta.json")
    if os.path.exists(sm):
        metas = json.load(open(sm, encoding="utf-8"))
    ok = 0
    for fn in sorted(os.listdir(raw_dir)):
        if not fn.endswith(".json") or fn.endswith(".fdt.json"):
            continue
        space = fn[:-5]
        rec = json.load(open(os.path.join(raw_dir, fn), encoding="utf-8"))
        r = score_space(space, rec, metas.get(space))
        g = r.get("median_gini")
        print(f"{space:<30} props={r['n_proposals_window']:>4} "
              f"votes={r['n_votes_window']:>8,} gini={_fmt(g)} "
              f"fails={r.get('n_fails_measured', '-')}")
        ok += 1
    print(f"\nscored {ok} cached spaces")
    return 0


def selftest() -> int:
    """Run the analytic self-tests by executing the metrics module's checks."""
    import subprocess
    py = sys.executable
    r1 = subprocess.run([py, os.path.join(HERE, "metrics.py")],
                        capture_output=True, text=True)
    sys.stdout.write(r1.stdout)
    ok = "ALL METRIC SELF-TESTS PASSED" in r1.stdout
    r2 = subprocess.run([py, os.path.join(HERE, "scipy_free_stats.py")],
                        capture_output=True, text=True)
    sys.stdout.write(r2.stdout)
    ok &= "PASSED" in r2.stdout
    print("selftest:", "OK" if ok else "FAILED")
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="fdt",
                                 description="Functional Decentralization Test CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("audit", help="collect and score one Snapshot space")
    a.add_argument("space", nargs="+", help="space id(s), e.g. ens.eth")
    a.add_argument("--months", type=int, default=12,
                   help="trailing window in months (default 12)")
    a.add_argument("--out", default=os.path.join(HERE, "data", "audits"),
                   help="output directory for raw + scored JSON")
    a.add_argument("-q", "--quiet", action="store_true")

    s = sub.add_parser("score", help="re-score cached spaces offline")
    s.add_argument("--raw", default=os.path.join(HERE, "data", "raw"))

    sub.add_parser("selftest", help="run analytic metric self-tests")

    ns = ap.parse_args(argv)
    if ns.cmd == "selftest":
        return selftest()
    if ns.cmd == "score":
        return score_all(ns.raw)
    rc = 0
    for sp in ns.space:
        rc = max(rc, audit(sp, ns.months, ns.out, ns.quiet))
    return rc


if __name__ == "__main__":
    sys.exit(main())
