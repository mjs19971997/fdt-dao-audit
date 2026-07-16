# -*- coding: utf-8 -*-
"""Probe 3: validate a candidate sample frame of economically significant DAOs.

Snapshot's `orderBy` is ignored by the hub API, so a ranked pull is impossible.
We instead test an explicit candidate list of well-known governance spaces and
report which ones actually exist and meet activity criteria. The surviving set
becomes the paper's purposive sample, with inclusion criteria stated up front.
"""
import json
import requests

HUB = "https://hub.snapshot.org/graphql"
HDRS = {"Content-Type": "application/json", "User-Agent": "fdt-research/0.1"}

CANDIDATES = [
    "uniswapgovernance.eth", "aave.eth", "ens.eth", "gitcoindao.eth",
    "opcollective.eth", "arbitrumfoundation.eth", "lido-snapshot.eth",
    "balancer.eth", "sushigov.eth", "badgerdao.eth", "gnosis.eth",
    "1inch.eth", "apecoin.eth", "safe.eth", "stgdao.eth", "cvx.eth",
    "olympusdao.eth", "starknet.eth", "dydxgov.eth", "radiantcapital.eth",
    "snapshot.dcl.eth", "aavegotchi.eth", "indexcoop.eth", "hop.eth",
    "rocketpool-dao.eth", "pooltogether.eth", "gearbox.eth", "lyra.eth",
    "frax.eth", "yam.eth", "shellprotocol.eth", "mantle.eth", "bitdao.eth",
    "comp-vote.eth", "moonwell.eth", "beets.eth", "spookyswap.eth",
    "banklessvault.eth", "developerdao.eth", "fwb.eth", "nounsdao.eth",
    "krausehouse.eth", "friendsofpooltogether.eth", "mstablegovernance.eth",
    "instadapp-gov.eth", "alchemixstakers.eth", "tribe.eth", "idlefinance.eth",
    "euler.eth", "angle.eth", "qidao.eth", "beanstalkfarms.eth",
    "stakedao.eth", "gmx.eth", "vesta-finance.eth", "connext.eth",
    "across.eth", "silofinance.eth", "morpho.eth", "spectradao.eth",
]

QUERY = """
query($ids: [String]) {
  spaces(first: 200, where: {id_in: $ids}) {
    id name followersCount proposalsCount votesCount network symbol
    strategies { name }
  }
}
"""


def main():
    r = requests.post(HUB, headers=HDRS,
                      json={"query": QUERY, "variables": {"ids": CANDIDATES}},
                      timeout=90)
    r.raise_for_status()
    j = r.json()
    if "errors" in j:
        print("GQL ERRORS:", json.dumps(j["errors"])[:500])
    spaces = (j.get("data") or {}).get("spaces") or []

    found = {s["id"] for s in spaces}
    missing = [c for c in CANDIDATES if c not in found]

    spaces.sort(key=lambda s: -(s.get("votesCount") or 0))
    print(f"{'space':<30} {'props':>6} {'votes':>9} {'followers':>10}  strategies")
    print("-" * 100)
    for s in spaces:
        strat = ",".join(x["name"] for x in s.get("strategies") or [])
        print(f"{s['id']:<30} {s['proposalsCount']:>6} {s['votesCount']:>9} "
              f"{s['followersCount']:>10}  {strat[:38]}")

    print()
    print(f"FOUND   : {len(spaces)} / {len(CANDIDATES)}")
    print(f"MISSING : {missing}")

    # Activity criteria for inclusion in the study
    eligible = [s for s in spaces
                if (s.get("proposalsCount") or 0) >= 25
                and (s.get("votesCount") or 0) >= 2000]
    print()
    print(f"ELIGIBLE (>=25 proposals AND >=2000 votes): {len(eligible)}")
    for s in eligible:
        print(f"   {s['id']}")

    with open("fdt/data/sample_frame_probe.json", "w", encoding="utf-8") as f:
        json.dump({"spaces": spaces, "missing": missing,
                   "eligible": [s["id"] for s in eligible]}, f, indent=2)


if __name__ == "__main__":
    main()
