# -*- coding: utf-8 -*-
"""Probe 4: pagination depth + throughput, and the turnout-denominator question."""
import time
import json
import requests

HUB = "https://hub.snapshot.org/graphql"
HDRS = {"Content-Type": "application/json", "User-Agent": "fdt-research/0.1"}


def q(query, variables=None):
    r = requests.post(HUB, headers=HDRS,
                      json={"query": query, "variables": variables or {}}, timeout=90)
    r.raise_for_status()
    j = r.json()
    if "errors" in j:
        return {"__errors": j["errors"]}
    return j.get("data")


print("=" * 78)
print("1) Does `skip` have a ceiling? (affects how we page big proposals)")
print("=" * 78)
for sk in (0, 4000, 5000, 6000):
    d = q("""
    query($sk: Int!) {
      votes(first: 100, skip: $sk, where: {space: "uniswapgovernance.eth"}) { id }
    }
    """, {"sk": sk})
    if "__errors" in d:
        print(f"  skip={sk:<6} -> ERROR: {json.dumps(d['__errors'])[:150]}")
    else:
        print(f"  skip={sk:<6} -> {len(d['votes'])} rows")

print()
print("=" * 78)
print("2) Cursor pagination via created_lt (skip-limit-free) + throughput")
print("=" * 78)
Q = """
query($space: String!, $lt: Int!) {
  votes(first: 1000, where: {space: $space, created_lt: $lt},
        orderBy: "created", orderDirection: desc) {
    voter created vp
  }
}
"""
cursor = 2147483647
total = 0
t0 = time.time()
for page in range(5):
    d = q(Q, {"space": "uniswapgovernance.eth", "lt": cursor})
    if "__errors" in d:
        print("  ERR", json.dumps(d["__errors"])[:200]); break
    rows = d["votes"]
    if not rows:
        break
    total += len(rows)
    cursor = rows[-1]["created"]
    print(f"  page {page}: {len(rows):>5} rows, cursor -> {cursor}, "
          f"cum={total}, {time.time()-t0:.1f}s")
print(f"  throughput ~= {total/(time.time()-t0):.0f} votes/sec")

print()
print("=" * 78)
print("3) Turnout denominator: what does a proposal expose?")
print("=" * 78)
d = q("""
{
  proposals(first: 2, where: {space: "ens.eth", state: "closed"},
            orderBy: "created", orderDirection: desc) {
    id votes scores_total quorum snapshot
    strategies { name params }
  }
}
""")
print(json.dumps(d, indent=2)[:1200])
