# -*- coding: utf-8 -*-
"""FDT data collection: pull every closed proposal and every individual vote
(with post-delegation voting power `vp`) for the sample DAOs over the trailing
12-month window, straight from the Snapshot hub. Checkpoints to disk so the run
resumes.

No estimated or synthetic values are produced anywhere in this file: every row
written is a record returned by the public API.
"""
import json
import os
import time
import requests

HUB = "https://hub.snapshot.org/graphql"
HDRS = {"Content-Type": "application/json", "User-Agent": "fdt-research/0.1"}

STUDY_CUTOFF = 1752451200      # 2025-07-14
# The manuscript specifies a trailing-12-month window for the dispersion and
# participation dimensions, so that is what we collect. A 24-month pull was
# attempted first but is infeasible for the highest-volume spaces under the
# hub's 100-req/60s limit (stgdao alone carries ~18M lifetime votes).
WINDOW_START = 1752451200      # 2025-07-14 -> trailing 12 months
OUT_DIR = "fdt/data/raw"
os.makedirs(OUT_DIR, exist_ok=True)

_last_call = [0.0]
MIN_INTERVAL = 0.62            # ~96 req/min, under the 100/60s hub limit


def q(query, variables, tries=7):
    """Rate-limited, retrying GraphQL call."""
    for attempt in range(tries):
        gap = time.time() - _last_call[0]
        if gap < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - gap)
        _last_call[0] = time.time()
        try:
            r = requests.post(HUB, headers=HDRS,
                              json={"query": query, "variables": variables},
                              timeout=90)
        except requests.RequestException as e:
            print(f"      net error {e}; retry")
            time.sleep(3 * (attempt + 1))
            continue
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 15))
            print(f"      429 -> sleep {wait}s")
            time.sleep(wait + 1)
            continue
        if r.status_code >= 500:
            time.sleep(3 * (attempt + 1))
            continue
        r.raise_for_status()
        j = r.json()
        if "errors" in j:
            print("      GQL ERR:", json.dumps(j["errors"])[:200])
            return None
        return j.get("data")
    return None


PROPS_Q = """
query($space: String!, $lt: Int!) {
  proposals(first: 1000, where: {space: $space, state: "closed", created_lt: $lt},
            orderBy: "created", orderDirection: desc) {
    id created start end title votes scores scores_total quorum type choices
    snapshot author
    strategies { name params }
  }
}
"""

VOTES_Q = """
query($pid: String!, $lt: Int!) {
  votes(first: 1000, where: {proposal: $pid, created_lt: $lt},
        orderBy: "created", orderDirection: desc) {
    voter created vp choice
  }
}
"""


def fetch_proposals(space):
    out, cursor = [], 2147483647
    while True:
        d = q(PROPS_Q, {"space": space, "lt": cursor})
        if not d:
            break
        rows = d["proposals"]
        if not rows:
            break
        out.extend(p for p in rows if p["created"] >= WINDOW_START)
        if rows[-1]["created"] < WINDOW_START or len(rows) < 1000:
            break
        cursor = rows[-1]["created"]
    return out


def fetch_votes(pid):
    """All votes for one proposal, paged by created_lt (skip ceiling is 5000)."""
    out, cursor, seen = [], 2147483647, set()
    while True:
        d = q(VOTES_Q, {"pid": pid, "lt": cursor})
        if not d:
            break
        rows = d["votes"]
        if not rows:
            break
        fresh = [v for v in rows if (v["voter"], v["created"]) not in seen]
        for v in fresh:
            seen.add((v["voter"], v["created"]))
        out.extend(fresh)
        if len(rows) < 1000:
            break
        nc = rows[-1]["created"]
        if nc == cursor:           # all rows share a timestamp; cursor stuck
            print(f"      cursor stuck at {nc}; {len(out)} rows collected")
            break
        cursor = nc
    return out


def main():
    with open("fdt/data/sample_frame_probe.json", encoding="utf-8") as f:
        spaces = json.load(f)["eligible"]

    for i, sp in enumerate(spaces, 1):
        path = os.path.join(OUT_DIR, f"{sp}.json")
        if os.path.exists(path):
            print(f"[{i:>2}/{len(spaces)}] {sp:<28} cached")
            continue

        t0 = time.time()
        props = fetch_proposals(sp)
        rec = {"space": sp, "window_start": WINDOW_START,
               "study_cutoff": STUDY_CUTOFF, "proposals": []}

        for p in props:
            votes = fetch_votes(p["id"]) if (p["votes"] or 0) > 0 else []
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
                          for v in votes],
            })

        nv = sum(len(x["votes"]) for x in rec["proposals"])
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rec, f)
        print(f"[{i:>2}/{len(spaces)}] {sp:<28} props={len(props):>4} "
              f"votes={nv:>8,}  {time.time()-t0:>6.1f}s")

    print("\nCOLLECTION COMPLETE ->", OUT_DIR)


if __name__ == "__main__":
    main()
