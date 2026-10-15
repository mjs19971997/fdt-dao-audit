# FDT — Functional Decentralization Test

Open, reproducible implementation of the **Functional Decentralization Test**: a
five-dimension audit of how decentralized a DAO's governance actually is, run
end-to-end against public data for 42 economically significant DAOs
(983 closed proposals, 226,156 individual votes with post-delegation voting power).

Companion code and data for the paper:

> *Auditing Decentralization Claims at Scale: An Open Implementation of the
> Functional Decentralization Test, Evidence from 42 DAOs, and a Correction to
> Its Dispersion Metric.* Jalili Sanjarani M., Elmi Sola Y., Hasanpour H.,
> Neghabi A.A. (under review, 2026)

**No API key, no paid subscription, no privileged access.** Only public endpoints:

| Source | Used for |
|---|---|
| `hub.snapshot.org/graphql` | proposals, votes, effective post-delegation voting power (`vp`), space plugins, declared treasuries |
| public JSON-RPC (publicnode / drpc / 1rpc) | `totalSupply`, Safe `getOwners` / `getThreshold`, EIP-1967 storage slots |

## Study window

Trailing 12 months ending **2026-07-14** (`WINDOW_START = 1752451200`), fixed as a
constant in `fdt/collect.py`. Results drift as the window advances; keep the
constant pinned to reproduce the published figures. The raw records collected for
the paper are included under `fdt/data/raw/` (one JSON per DAO), so every derived
number can be recomputed **without** re-crawling.

## Setup

```bash
python -m venv venv
# Linux/macOS:            source venv/bin/activate
# Windows (Git Bash):     source venv/Scripts/activate
pip install -r requirements.txt
```

## Reproduce the paper's numbers (no network needed)

The collected records are shipped in `fdt/data/raw/`, so the analysis chain runs
offline. From the **repository root**:

```bash
PYTHONPATH=fdt python fdt/metrics.py           # analytic self-tests (must all PASS)
python fdt/scipy_free_stats.py                 # Spearman self-tests
PYTHONPATH=fdt python fdt/analyze.py           # FDT scoring  -> fdt/out/fdt_results.json
PYTHONPATH=fdt python fdt/robustness.py        # R1 masking, R2 leave-one-out
PYTHONPATH=fdt python fdt/diagnose_dvote.py    # the eq.(2) defect, synthetic + empirical
PYTHONPATH=fdt python fdt/eval_metrics.py      # candidate replacement metrics
python fdt/make_figs_v5.py                     # all figures -> figs_v5/
```

## Re-collect from scratch (network)

```bash
python fdt/probe3.py       # resolve the sample frame against the Snapshot hub
python fdt/spacemeta.py    # plugins, governance tokens, totalSupply
python -u fdt/collect.py   # proposals + every vote (~25 min under the rate limit)
PYTHONPATH=fdt python fdt/onchain.py   # treasury Safes + EIP-1967 probes
```

`collect.py` checkpoints per space into `fdt/data/raw/`; an interrupted run
resumes without refetching. Delete a space's JSON to force a refresh.

## One-command audit (CLI)

```bash
PYTHONPATH=fdt python fdt/cli.py audit ens.eth          # collect + score + report
PYTHONPATH=fdt python fdt/cli.py audit somedao.eth --months 6
PYTHONPATH=fdt python fdt/cli.py score                  # re-score all cached spaces, offline
PYTHONPATH=fdt python fdt/cli.py selftest               # analytic metric checks (CI gate)
```

`audit` fetches a space's metadata, proposals, and every vote over a trailing
window, scores all measurable dimensions with the same code path the paper's
ecosystem study ran, prints a report, and writes the raw record plus the scored
result under `fdt/data/audits/`. Measured live: a full audit of `ens.eth`
(14 proposals, 1,195 votes) completes in **26 seconds**. The report never
conflates unmeasurable with passing: a dimension without a defensible
denominator is printed as *unscored*.

## Tutorial: audit a DAO outside the sample

Suppose you want to audit `somedao.eth`, a Snapshot space not in our frame.

1. **Add it to the frame.** Open `fdt/data/sample_frame_probe.json` and append
   `"somedao.eth"` to the `eligible` list (or edit `CANDIDATES` in
   `fdt/probe3.py` and re-run it to apply the activity criteria).
2. **Fetch its metadata and votes:**
   ```bash
   python fdt/spacemeta.py        # refreshes plugins/token/supply for all frame spaces
   python -u fdt/collect.py       # fetches only the new space (others are cached)
   ```
3. **Re-score and re-check:**
   ```bash
   PYTHONPATH=fdt python fdt/analyze.py
   PYTHONPATH=fdt python fdt/robustness.py
   ```
   Your DAO now appears in `fdt/out/fdt_results.json` with its per-proposal
   metrics, medians, and pass/fail bits.
4. **What it costs.** Collection is bounded by the hub's rate limit, not CPU.
   Requests ≈ (number of proposals) + (votes ÷ 1000), at ~0.62 s per request:
   a median-sized DAO in our sample (~20 proposals, ~1,000 votes) collects in
   ~20 s; our heaviest space by votes (104,664) took 236 s; a space with 412
   small proposals took 671 s.
5. **If it declares treasuries** in its Snapshot config, `onchain.py` will pick
   them up and read the Safe owners/threshold directly from chain state.

## Measured performance

All figures measured on an 8-core Xeon E5-4650 v2, Windows Server 2022.

| Stage | Wall-clock | Peak RSS | Bound by |
|---|---|---|---|
| Collection, all 42 DAOs (network) | 33.8 min | — | hub rate limit (100 req/60 s) |
| FDT scoring over 226,156 votes | 6.4 s | 89 MB | CPU |
| Robustness checks | 4.5 s | 90 MB | CPU |
| Defect diagnostics + metric evaluation | 3.8 s | 34 MB | CPU |
| Figure generation | 22.7 s | 145 MB | CPU |
| **Full offline analysis chain** | **37.4 s** | **≤ 145 MB** | CPU |

Once the 29.3 MB of raw records exists, everything downstream reruns offline in
under 40 seconds — the marginal cost of re-analysis is effectively zero.

## Extending to other voting venues

Collection and analysis meet at a narrow interface. Everything downstream of
collection consumes, per proposal, a list of vote records:

```json
{"voter": "0x…", "vp": 12345.6, "created": 1752451200, "choice": 1}
```

plus per-space metadata (`fdt/data/spacemeta.json`). To support another venue —
Tally's API over Governor-family contracts, or direct event-log extraction —
write one collector that emits this shape into `fdt/data/raw/<space>.json`
(see any shipped file for the envelope); metrics, scoring, robustness, and
figures apply unchanged. The open design question (not plumbing) is the
effective-vote semantics for Governor venues: cast votes vs delegated
checkpoints. See paper §8.

## Validate before you trust

`fdt/metrics.py` is checked against distributions with known closed-form values
(HHI = 1 for a single holder, 1/n for n equal holders; Gini = 0 under equality).
This suite caught a real boundary bug during development: the first Nakamoto
implementation returned 2 for four equal holders, because a cumulative share
landing *exactly* on 50% was treated as exceeding it. Correct answer: 3.

## Layout

```
fdt/collect.py           proposals + every vote; created_lt cursor paging; rate-limited
fdt/spacemeta.py         plugins (execution modules), governance token, totalSupply
fdt/metrics.py           eq. (1)-(3), Gini, Nakamoto, top-k, MMF  + self-tests
fdt/analyze.py           per-proposal -> per-DAO FDT scoring
fdt/onchain.py           Safe getOwners/getThreshold; EIP-1967 slot probe
fdt/robustness.py        R1 whale masking, R2 leave-one-DAO-out
fdt/diagnose_dvote.py    synthetic cartel sweep + empirical correlations
fdt/eval_metrics.py      invariance / discrimination / size co-movement of candidates
fdt/make_figs_v5.py      all figures, computed from fdt/out/*.json
fdt/probe*.py            the API reconnaissance the design rests on (kept for audit)
fdt/data/raw/*.json      collected records, one file per DAO (42 files)
fdt/out/*.json           derived results
figs_v5/*.png            paper figures
```

## Known limits (paper §11)

- **No archive RPC** on free endpoints → historical `totalSupply` at each
  proposal's snapshot block is unreadable, so **turnout is not scored**: the only
  available denominator (total supply) overstates the eligible base in a
  delegation system and would bias the result toward the paper's own thesis.
- **Upgrade control is unmeasured.** Only 3/37 governance tokens are EIP-1967
  proxies; upgrade authority lives in core contracts no public metadata
  enumerates, and bespoke access control (e.g. Aave's ACL manager) returns a
  zero admin slot.
- **Treasury control covers 8/42 DAOs** — only those declaring a treasury
  address that resolves as a Gnosis Safe.
- **Single venue.** Snapshot only. Protocols with a binding on-chain Governor
  (Uniswap, Compound, ENS) use Snapshot advisorily; the execution-autonomy
  figures characterize the sampled venue, not those governors.
- **No entity clustering.** One actor voting from many wallets counts as many
  voters, biasing every dispersion measure toward *dispersed*. Concentration
  findings are conservative.

## Headline results

| | |
|---|---|
| DAOs / proposals / votes | 42 / 983 / 226,156 |
| Governance-dormant (0 closed proposals in 12 mo) | 12 / 42 (28.6%) |
| Median Gini of effective voting power | 0.855 (range 0.656–0.995) |
| DAOs at Gini ≥ 0.90 | 9 / 30 active |
| Median Nakamoto over votes cast | 2 |
| Venues with no automated execution module | 36 / 42 |
| Measurable treasuries moving on ≤ 3 signatures | 4 / 8 |
| R1 masking: median Gini full → top-10 masked | 0.855 → 0.670 |
| R2 leave-one-out: max Δ median Gini | 0.0008 |
| eq. (2) `d_vote` vs Gini (Spearman) | +0.04 |
| eq. (2) misses of Gini ≥ 0.90 proposals | 183 / 201 (91%) |

## Citing

If you use this code or dataset, please cite the paper above and this repository:

```bibtex
@misc{fdt2026,
  author = {Jalili Sanjarani, Mostafa and Elmi Sola, Yasser and
            Hasanpour, Hesam and Neghabi, Ali Akbar},
  title  = {FDT: an open implementation of the Functional Decentralization Test},
  year   = {2026},
  url    = {https://github.com/mjs19971997/fdt-dao-audit}
}
```

## Tests

The metric layer ships with analytic self-tests (`fdt/metrics.py`,
`fdt/scipy_free_stats.py`) — run them first; they must all PASS before any
result is trusted. They are executed automatically at the top of the
reproduce sequence above.

## Archival

A DOI-stamped snapshot of this repository (code + dataset) will be deposited
on Zenodo upon paper acceptance, so results remain citable independent of
GitHub availability.

## License

MIT — see [LICENSE](LICENSE). The collected governance records are public
on-chain/API data and carry no additional restrictions.
