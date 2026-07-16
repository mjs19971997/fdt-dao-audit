# -*- coding: utf-8 -*-
"""Scope the collection job: pull proposal metadata (cheap) for every eligible
space over the paper's trailing-12-month window and total the vote counts, so we
can size the real vote pull against the 100-req/60s hub rate limit."""
import json
import time
import requests

HUB = "https://hub.snapshot.org/graphql"
HDRS = {"Content-Type": "application/json", "User-Agent": "fdt-research/0.1"}

# Trailing 12 months from the study cut-off (2026-07-14).
WINDOW_START = 1752451200   # 2025-07-14 00:00:00 UTC

with open("fdt/data/sample_frame_probe.json", encoding="utf-8") as f:
    ELIGIBLE = json.load(f)["eligible"]

PROPS_Q = """
query($space: String!, $lt: Int!) {
  proposals(first: 1000, where: {space: $space, state: "closed", created_lt: $lt},
            orderBy: "created", orderDirection: desc) {
    id created votes scores_total quorum type
  }
}
"""


def q(query, variables):
    for attempt in range(6):
        r = requests.post(HUB, headers=HDRS,
                          json={"query": query, "variables": variables}, timeout=90)
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 20))
            print(f"    429 -> sleeping {wait}s")
            time.sleep(wait + 1)
            continue
        r.raise_for_status()
        j = r.json()
        if "errors" in j:
            print("    GQL ERR:", json.dumps(j["errors"])[:200])
            return None
        return j.get("data")
    return None


def proposals_in_window(space):
    """All closed proposals created within the trailing-12-month window."""
    out, cursor = [], 2147483647
    while True:
        d = q(PROPS_Q, {"space": space, "lt": cursor})
        if not d:
            break
        rows = d["proposals"]
        if not rows:
            break
        for p in rows:
            if p["created"] >= WINDOW_START:
                out.append(p)
        cursor = rows[-1]["created"]
        if rows[-1]["created"] < WINDOW_START:
            break          # paged past the window; stop
        if len(rows) < 1000:
            break
        time.sleep(0.65)   # stay under 100 req/60s
    return out


def main():
    summary, grand = [], 0
    for i, sp in enumerate(ELIGIBLE, 1):
        props = proposals_in_window(sp)
        nv = sum(p["votes"] or 0 for p in props)
        grand += nv
        summary.append({"space": sp, "n_proposals": len(props), "n_votes": nv,
                        "max_votes_in_one": max([p["votes"] or 0 for p in props],
                                                default=0)})
        print(f"[{i:>2}/{len(ELIGIBLE)}] {sp:<28} props={len(props):>4} "
              f"votes={nv:>9,}  (cum {grand:,})")
        time.sleep(0.65)

    summary.sort(key=lambda r: -r["n_votes"])
    req_est = sum((r["n_votes"] + 999) // 1000 for r in summary)
    print()
    print(f"TOTAL votes in 12-mo window : {grand:,}")
    print(f"Est. vote requests (1k/req) : {req_est:,}")
    print(f"Est. wall-clock @100req/60s : {req_est / 100 * 60 / 60:.1f} min")

    with open("fdt/data/scope.json", "w", encoding="utf-8") as f:
        json.dump({"window_start": WINDOW_START, "summary": summary,
                   "total_votes": grand, "est_requests": req_est}, f, indent=2)


if __name__ == "__main__":
    main()
