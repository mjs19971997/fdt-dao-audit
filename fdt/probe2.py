# -*- coding: utf-8 -*-
"""Probe 2: establish a defensible DAO sample frame + check turnout denominators."""
import json
import requests

HUB = "https://hub.snapshot.org/graphql"
HDRS = {"Content-Type": "application/json", "User-Agent": "fdt-research/0.1"}


def q(query, variables=None):
    r = requests.post(HUB, headers=HDRS,
                      json={"query": query, "variables": variables or {}}, timeout=60)
    r.raise_for_status()
    j = r.json()
    if "errors" in j:
        print("GQL ERRORS:", json.dumps(j["errors"])[:400])
    return j.get("data")


print("=" * 78)
print("1) Spaces ranked by followersCount (candidate sample frame)")
print("=" * 78)
d = q("""
{
  spaces(first: 60, orderBy: "followersCount", orderDirection: desc) {
    id name followersCount proposalsCount votesCount network symbol
    strategies { name }
  }
}
""")
rows = (d or {}).get("spaces", []) or []
print(f"  returned {len(rows)}")
for s in rows:
    strat = ",".join(x["name"] for x in s.get("strategies") or [])
    print(f"  {s['id']:<32} foll={s['followersCount']:<9} props={s['proposalsCount']:<6} "
          f"votes={s['votesCount']:<9} net={s['network']:<6} {strat[:34]}")
