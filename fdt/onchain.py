# -*- coding: utf-8 -*-
"""Contract-level FDT dimensions, read directly from chain state.

D2 treasury control: for every treasury address a DAO declares in its own public
Snapshot space configuration, call the Gnosis Safe accessors

    getOwners()   0xa0e67e2b
    getThreshold() 0xe75235b8

and score D2 as failing when funds are movable by <= 3 signers (Table II).

D1 upgrade control: we probe the EIP-1967 implementation/admin slots on the
governance token and treasury contracts. This detects the standard proxy pattern
only; protocols with bespoke access control (Aave's ACL manager, for example)
return a zero admin slot and are reported as indeterminate rather than guessed.

Addresses are never invented here: they come from the DAO's own space config.
"""
import json
import time
import requests

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

SEL_GET_OWNERS = "0xa0e67e2b"
SEL_GET_THRESHOLD = "0xe75235b8"
SLOT_IMPL = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
SLOT_ADMIN = "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"

TAU_TREASURY_SIGNERS = 3      # Table II: fail when funds movable by <= 3 signers


def _rpc(net, method, params):
    url = RPCS.get(int(net))
    if not url:
        return {"__err": f"no rpc for network {net}"}
    for attempt in range(4):
        try:
            r = requests.post(url, json={"jsonrpc": "2.0", "id": 1,
                                         "method": method, "params": params},
                              timeout=30)
            if r.status_code != 200:
                time.sleep(1.5 * (attempt + 1))
                continue
            return r.json()
        except Exception as e:
            time.sleep(1.5 * (attempt + 1))
            last = str(e)[:80]
    return {"__err": "rpc failed"}


def call(net, to, data):
    j = _rpc(net, "eth_call", [{"to": to, "data": data}, "latest"])
    res = j.get("result")
    if not res or res == "0x":
        return None
    return res


def storage(net, to, slot):
    j = _rpc(net, "eth_getStorageAt", [to, slot, "latest"])
    return j.get("result")


def decode_address_array(hexstr):
    """ABI-decode `address[]` returned by getOwners()."""
    b = hexstr[2:]
    if len(b) < 128:
        return None
    n = int(b[64:128], 16)
    out = []
    for i in range(n):
        chunk = b[128 + i * 64: 192 + i * 64]
        if len(chunk) < 64:
            return None
        out.append("0x" + chunk[24:])
    return out


def slot_to_addr(res):
    if not res or int(res, 16) == 0:
        return None
    return "0x" + res[-40:]


def inspect_safe(net, addr):
    """Return owners/threshold if `addr` is a Gnosis Safe, else mark not-a-safe."""
    o = call(net, addr, SEL_GET_OWNERS)
    t = call(net, addr, SEL_GET_THRESHOLD)
    if o is None or t is None:
        return {"is_safe": False, "owners": None, "threshold": None}
    owners = decode_address_array(o)
    try:
        thr = int(t, 16)
    except Exception:
        thr = None
    if owners is None or thr is None:
        return {"is_safe": False, "owners": None, "threshold": None}
    return {"is_safe": True, "owners": owners, "n_owners": len(owners),
            "threshold": thr}


def inspect_proxy(net, addr):
    impl = slot_to_addr(storage(net, addr, SLOT_IMPL))
    admin = slot_to_addr(storage(net, addr, SLOT_ADMIN))
    return {"eip1967_proxy": impl is not None,
            "implementation": impl, "admin": admin}


def main():
    with open("fdt/data/spacemeta.json", encoding="utf-8") as f:
        metas = json.load(f)

    out = {}
    for space, m in sorted(metas.items()):
        treas = m.get("treasuries") or []
        if not treas:
            continue
        recs = []
        for t in treas:
            net = t.get("network") or 1
            addr = t.get("address")
            if not addr:
                continue
            safe = inspect_safe(net, addr)
            prox = inspect_proxy(net, addr)
            recs.append({"name": t.get("name"), "network": net, "address": addr,
                         **safe, **prox})
            time.sleep(0.2)

        safes = [r for r in recs if r["is_safe"]]
        # D2 scoring: the weakest declared treasury governs the dimension.
        min_thr = min([r["threshold"] for r in safes], default=None)
        d2_fail = None if min_thr is None else bool(min_thr <= TAU_TREASURY_SIGNERS)

        out[space] = {"treasuries": recs,
                      "n_declared": len(recs),
                      "n_safes": len(safes),
                      "min_threshold": min_thr,
                      "D2_treasury_fail": d2_fail}

        for r in recs:
            tag = (f"SAFE {r['threshold']}-of-{r['n_owners']}" if r["is_safe"]
                   else "not-a-safe")
            print(f"  {space:<24} {r['address'][:12]}.. net={str(r['network']):<6} "
                  f"{tag:<18} proxy={r['eip1967_proxy']}")

    # Also probe the governance token for the standard proxy pattern (D1 signal).
    print("\n-- D1 probe: EIP-1967 slots on governance tokens --")
    d1 = {}
    for space, m in sorted(metas.items()):
        tok = m.get("token")
        if not tok:
            continue
        p = inspect_proxy(tok.get("network") or 1, tok["address"])
        d1[space] = {"token": tok["address"], "network": tok.get("network"), **p}
        print(f"  {space:<24} proxy={str(p['eip1967_proxy']):<5} "
              f"admin={p['admin'] or '-'}")
        time.sleep(0.15)

    with open("fdt/out/onchain.json", "w", encoding="utf-8") as f:
        json.dump({"treasury": out, "token_proxy": d1}, f, indent=2)

    scored = [v for v in out.values() if v["D2_treasury_fail"] is not None]
    failed = [v for v in scored if v["D2_treasury_fail"]]
    print(f"\nD2 measurable for {len(scored)} spaces; failing (<= "
          f"{TAU_TREASURY_SIGNERS} signers): {len(failed)}")
    n_proxy = sum(1 for v in d1.values() if v["eip1967_proxy"])
    n_admin = sum(1 for v in d1.values() if v["admin"])
    print(f"D1 probe: {n_proxy}/{len(d1)} tokens are EIP-1967 proxies; "
          f"{n_admin} expose a non-zero admin slot")


if __name__ == "__main__":
    main()
