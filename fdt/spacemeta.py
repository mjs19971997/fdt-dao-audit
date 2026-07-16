# -*- coding: utf-8 -*-
"""Collect space-level metadata for the sample DAOs:
  - plugins            -> execution-autonomy proxy (oSnap / safeSnap => automated
                          on-chain execution; absent => passed proposals depend on
                          discretionary off-chain action by signers)
  - strategies         -> the governance token contract(s) and decimals
  - voting config      -> quorum, delay, period
  - treasuries         -> declared treasury addresses (sparse; used where present)
Then resolves each governance token's totalSupply on-chain, which is the
denominator for the participation-depth dimension.
"""
import json
import time
import requests

HUB = "https://hub.snapshot.org/graphql"
HDRS = {"Content-Type": "application/json", "User-Agent": "fdt-research/0.1"}
RPCS = {
    1: "https://ethereum-rpc.publicnode.com",
    10: "https://optimism-rpc.publicnode.com",
    56: "https://bsc-rpc.publicnode.com",
    100: "https://gnosis-rpc.publicnode.com",
    137: "https://polygon-bor-rpc.publicnode.com",
    250: "https://fantom-rpc.publicnode.com",
    8453: "https://base-rpc.publicnode.com",
    42161: "https://arbitrum-one-rpc.publicnode.com",
    43114: "https://avalanche-c-chain-rpc.publicnode.com",
}

# Execution plugins that actually push a passed proposal on-chain without a
# human deciding to act. Everything else is signalling-only.
EXEC_PLUGINS = {"oSnap", "safeSnap"}

SPACE_Q = """
query($ids: [String]) {
  spaces(first: 200, where: {id_in: $ids}) {
    id name network symbol followersCount proposalsCount votesCount
    plugins
    voting { type quorum delay period }
    treasuries { name address network }
    strategies { name network params }
  }
}
"""


def rpc_call(chain, to, data):
    url = RPCS.get(int(chain) if str(chain).isdigit() else 1)
    if not url:
        return None
    try:
        r = requests.post(url, json={"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                                     "params": [{"to": to, "data": data}, "latest"]},
                          timeout=30)
        j = r.json()
        res = j.get("result")
        if res and res != "0x":
            return int(res, 16)
    except Exception:
        return None
    return None


def token_from_strategies(strats):
    """Pull (address, decimals, network) for the first strategy that names a token
    contract. Snapshot nests delegation strategies, so we recurse into params."""
    def walk(params, net):
        if not isinstance(params, dict):
            return None
        addr = params.get("address")
        dec = params.get("decimals")
        if addr and isinstance(addr, str) and addr.startswith("0x") and len(addr) == 42:
            return {"address": addr, "decimals": dec if dec is not None else 18,
                    "network": net}
        for sub in (params.get("strategies") or []):
            got = walk(sub.get("params") or {}, sub.get("network") or net)
            if got:
                return got
        return None

    for s in strats or []:
        got = walk(s.get("params") or {}, s.get("network") or 1)
        if got:
            got["strategy"] = s.get("name")
            return got
    return None


def main():
    with open("fdt/data/sample_frame_probe.json", encoding="utf-8") as f:
        ids = json.load(f)["eligible"]

    r = requests.post(HUB, headers=HDRS,
                      json={"query": SPACE_Q, "variables": {"ids": ids}}, timeout=90)
    r.raise_for_status()
    j = r.json()
    if "errors" in j:
        print("GQL ERR:", json.dumps(j["errors"])[:300])
    spaces = (j.get("data") or {}).get("spaces") or []

    out = {}
    for s in spaces:
        plugins = list((s.get("plugins") or {}).keys()) if isinstance(s.get("plugins"), dict) \
            else list(s.get("plugins") or [])
        tok = token_from_strategies(s.get("strategies"))
        supply = None
        if tok:
            raw = rpc_call(tok["network"], tok["address"], "0x18160ddd")  # totalSupply()
            if raw is not None:
                supply = raw / (10 ** int(tok["decimals"] or 18))
            time.sleep(0.15)

        out[s["id"]] = {
            "name": s.get("name"),
            "network": s.get("network"),
            "symbol": s.get("symbol"),
            "followers": s.get("followersCount"),
            "proposals_all_time": s.get("proposalsCount"),
            "votes_all_time": s.get("votesCount"),
            "plugins": plugins,
            "has_exec_plugin": bool(set(plugins) & EXEC_PLUGINS),
            "exec_plugins": sorted(set(plugins) & EXEC_PLUGINS),
            "voting": s.get("voting"),
            "treasuries": s.get("treasuries") or [],
            "token": tok,
            "token_total_supply": supply,
            "supply_measured_at": "latest",   # no archive RPC available: see limitations
        }
        print(f"{s['id']:<28} exec={out[s['id']]['has_exec_plugin']!s:<5} "
              f"plugins={plugins} tok={(tok or {}).get('address','-')[:12]} "
              f"supply={supply if supply is None else f'{supply:,.0f}'}")

    with open("fdt/data/spacemeta.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    n_exec = sum(1 for v in out.values() if v["has_exec_plugin"])
    print(f"\nspaces={len(out)}  with automated execution={n_exec}  "
          f"signalling-only={len(out)-n_exec}")
    print("token supply resolved:",
          sum(1 for v in out.values() if v["token_total_supply"]), "/", len(out))


if __name__ == "__main__":
    main()
