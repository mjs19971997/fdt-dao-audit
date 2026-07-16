# -*- coding: utf-8 -*-
"""Probe on-chain access for the two contract-level FDT dimensions:
   - upgrade control  -> EIP-1967 admin/implementation storage slots
   - treasury control -> Gnosis Safe owners + threshold
Also tests whether any public RPC serves archive reads (needed for a turnout
denominator measured at the proposal's snapshot block rather than today).
"""
import json
import requests

RPCS = [
    "https://eth.llamarpc.com",
    "https://cloudflare-eth.com",
    "https://rpc.ankr.com/eth",
    "https://ethereum-rpc.publicnode.com",
    "https://eth.drpc.org",
    "https://1rpc.io/eth",
]

# EIP-1967 slots
SLOT_IMPL = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
SLOT_ADMIN = "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"

UNI_TOKEN = "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984"   # UNI
ENS_TOKEN = "0xC18360217D8F7Ab5e7c516566761Ea12Ce7F9D72"   # ENS


def rpc(url, method, params, timeout=25):
    try:
        r = requests.post(url, json={"jsonrpc": "2.0", "id": 1,
                                     "method": method, "params": params},
                          timeout=timeout)
        if r.status_code != 200:
            return {"__err": f"HTTP {r.status_code}"}
        return r.json()
    except Exception as e:
        return {"__err": str(e)[:80]}


print("=" * 78)
print("1) Which RPCs answer at all? (eth_blockNumber)")
print("=" * 78)
live = []
for u in RPCS:
    j = rpc(u, "eth_blockNumber", [])
    if "result" in j:
        print(f"  OK    {u:<38} block={int(j['result'],16):,}")
        live.append(u)
    else:
        print(f"  DEAD  {u:<38} {j.get('__err') or j.get('error')}")

print()
print("=" * 78)
print("2) ARCHIVE test: totalSupply() of UNI at an old block (~2 yrs ago)")
print("=" * 78)
# totalSupply() selector 0x18160ddd
OLD_BLOCK = hex(20_000_000)   # ~June 2024
for u in live:
    j = rpc(u, "eth_call", [{"to": UNI_TOKEN, "data": "0x18160ddd"}, OLD_BLOCK])
    if "result" in j and j["result"] not in ("0x", None):
        print(f"  ARCHIVE-OK  {u:<36} supply={int(j['result'],16)/1e18:,.0f}")
    else:
        err = j.get("error", {})
        msg = err.get("message") if isinstance(err, dict) else err
        print(f"  no-archive  {u:<36} {str(msg or j.get('__err'))[:60]}")

print()
print("=" * 78)
print("3) LATEST totalSupply (fallback denominator)")
print("=" * 78)
for u in live[:2]:
    for name, tok in (("UNI", UNI_TOKEN), ("ENS", ENS_TOKEN)):
        j = rpc(u, "eth_call", [{"to": tok, "data": "0x18160ddd"}, "latest"])
        if "result" in j:
            print(f"  {u:<34} {name} supply={int(j['result'],16)/1e18:,.0f}")

print()
print("=" * 78)
print("4) EIP-1967 proxy slots readable? (Aave v3 Pool proxy)")
print("=" * 78)
AAVE_POOL = "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2"
for u in live[:2]:
    for label, slot in (("impl", SLOT_IMPL), ("admin", SLOT_ADMIN)):
        j = rpc(u, "eth_getStorageAt", [AAVE_POOL, slot, "latest"])
        print(f"  {u:<34} {label:<6} {j.get('result') or j.get('error')}")

print()
print("=" * 78)
print("5) Gnosis Safe transaction service: owners + threshold")
print("=" * 78)
SAFES = {
    "ENS DAO wallet": "0xFe89cc7aBB2C4183683ab71653C4cdc9B02D44b7",
    "Uniswap treasury (timelock)": "0x1a9C8182C09F50C8318d769245beA52c32BE35BC",
}
for name, addr in SAFES.items():
    url = f"https://safe-transaction-mainnet.safe.global/api/v1/safes/{addr}/"
    try:
        r = requests.get(url, timeout=25)
        if r.status_code == 200:
            d = r.json()
            print(f"  {name}: threshold={d.get('threshold')} "
                  f"owners={len(d.get('owners') or [])}")
        else:
            print(f"  {name}: HTTP {r.status_code} (not a Safe / not indexed)")
    except Exception as e:
        print(f"  {name}: ERR {str(e)[:60]}")
