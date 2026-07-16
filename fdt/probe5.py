# -*- coding: utf-8 -*-
"""Probe 5: is the created_lt cursor correct? Ties on `created` would be silently
dropped by a strict-less-than cursor, and could stall paging entirely."""
import time
import requests
from collections import Counter

HUB = "https://hub.snapshot.org/graphql"
HDRS = {"Content-Type": "application/json", "User-Agent": "fdt-research/0.1"}


def q(query, variables):
    r = requests.post(HUB, headers=HDRS,
                      json={"query": query, "variables": variables}, timeout=90)
    r.raise_for_status()
    return r.json().get("data")


# a large stgdao proposal
d = q("""
{
  proposals(first: 5, where: {space: "stgdao.eth", state: "closed"},
            orderBy: "created", orderDirection: desc) {
    id votes created
  }
}
""", {})
props = d["proposals"]
for p in props:
    print(f"  {p['id'][:20]}  reported_votes={p['votes']:>7,}  created={p['created']}")

pid = max(props, key=lambda p: p["votes"] or 0)
print(f"\nTesting biggest: {pid['id']}  reported={pid['votes']:,}")

# How clustered are `created` timestamps? (ties break a strict-lt cursor)
d = q("""
query($pid: String!) {
  votes(first: 1000, where: {proposal: $pid}, orderBy: "created", orderDirection: desc) {
    created
  }
}
""", {"pid": pid["id"]})
ts = [v["created"] for v in d["votes"]]
c = Counter(ts)
print(f"  first page: {len(ts)} rows, {len(c)} distinct timestamps")
print(f"  max votes sharing one timestamp: {max(c.values())}")
print(f"  boundary timestamp {ts[-1]} appears {c[ts[-1]]}x on this page")

print("\n-- paging with created_lt, measuring loss vs reported --")
cursor, total, pages = 2147483647, 0, 0
t0 = time.time()
while pages < 40:
    d = q("""
    query($pid: String!, $lt: Int!) {
      votes(first: 1000, where: {proposal: $pid, created_lt: $lt},
            orderBy: "created", orderDirection: desc) { created }
    }
    """, {"pid": pid["id"], "lt": cursor})
    rows = d["votes"]
    pages += 1
    if not rows:
        break
    total += len(rows)
    nc = rows[-1]["created"]
    if nc == cursor:
        print("  CURSOR STUCK")
        break
    cursor = nc
    if len(rows) < 1000:
        break
    time.sleep(0.62)
print(f"  collected={total:,} reported={pid['votes']:,} "
      f"loss={pid['votes']-total:,} pages={pages} time={time.time()-t0:.1f}s")
