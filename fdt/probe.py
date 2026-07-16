# -*- coding: utf-8 -*-
"""Probe the Snapshot GraphQL API to establish exactly which fields are really
available before we design the measurement pipeline. Prints raw shapes."""
import json
import requests

HUB = "https://hub.snapshot.org/graphql"
HDRS = {"Content-Type": "application/json", "User-Agent": "fdt-research/0.1"}


def q(query, variables=None):
    r = requests.post(HUB, headers=HDRS,
                      json={"query": query, "variables": variables or {}},
                      timeout=60)
    r.raise_for_status()
    j = r.json()
    if "errors" in j:
        print("GQL ERRORS:", json.dumps(j["errors"])[:600])
    return j.get("data")


print("=" * 70)
print("1) Top spaces by activity")
print("=" * 70)
d = q("""
{
  spaces(first: 25, orderBy: "proposalsCount", orderDirection: desc,
         where: {verified: true}) {
    id name followersCount proposalsCount votesCount
    symbol network strategies { name }
  }
}
""")
for s in (d or {}).get("spaces", []) or []:
    strat = ",".join(x["name"] for x in s.get("strategies") or [])
    print(f"  {s['id']:<28} props={s['proposalsCount']:<6} votes={s['votesCount']:<8} "
          f"followers={s['followersCount']:<8} strat={strat[:40]}")

print()
print("=" * 70)
print("2) Proposal shape (uniswap)")
print("=" * 70)
d = q("""
{
  proposals(first: 3, where: {space: "uniswapgovernance.eth", state: "closed"},
            orderBy: "created", orderDirection: desc) {
    id title state created start end
    choices scores scores_total scores_state votes
    quorum type snapshot
  }
}
""")
for p in (d or {}).get("proposals", []) or []:
    print(json.dumps({k: v for k, v in p.items() if k != "title"}, indent=2)[:700])
    print("  title:", p["title"][:70])
    print("  ---")

print()
print("=" * 70)
print("3) Vote shape -- does `vp` exist? (post-delegation voting power)")
print("=" * 70)
d = q("""
{
  votes(first: 5, where: {space: "uniswapgovernance.eth"},
        orderBy: "vp", orderDirection: desc) {
    id voter created choice vp vp_by_strategy vp_state
    proposal { id }
  }
}
""")
for v in (d or {}).get("votes", []) or []:
    print(f"  voter={v['voter'][:12]}... vp={v['vp']} vp_state={v['vp_state']} "
          f"by_strategy={v['vp_by_strategy']} prop={v['proposal']['id'][:14]}")

print()
print("=" * 70)
print("4) Pagination limit check -- how many votes can we pull per query?")
print("=" * 70)
for n in (1000, 1001):
    try:
        d = q("""
        query($n: Int!) {
          votes(first: $n, where: {space: "uniswapgovernance.eth"}) { id }
        }
        """, {"n": n})
        got = len((d or {}).get("votes") or [])
        print(f"  first={n} -> returned {got}")
    except Exception as e:
        print(f"  first={n} -> ERROR {e}")
