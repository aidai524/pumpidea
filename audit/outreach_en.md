# Pump.fun — an independent, on-chain reconciliation of protocol revenue

**To:** Pump.fun data / finance / protocol team
**From:** [our team]
**Date:** 2026-10-13
**Scope:** public on-chain data only; no internal access used

---

## Why we are writing

Your fees dashboard states that since the introduction of custom pairs it "does not
correctly reflect the revenue and buyback amount". We rebuilt the protocol's fee
plumbing from public data to see whether the gap can be measured independently.
It can — and two of the findings may be useful to your team.

## What we found (public data only)

**1. Revenue is collected in quote assets across an enormous number of token accounts.**
Per trade, one of the eight published normal fee recipients receives the protocol fee
and one of the eight buyback recipients receives the buyback slice, paid in the pool's
**quote asset** (WSOL for SOL pairs; USDC / custom-pair tokens otherwise). We measured
**257k–571k SPL token accounts** on individual recipient addresses. Reconciling revenue
therefore requires aggregating and pricing tens of thousands of distinct quote assets —
a structural reason the dashboard is hard to keep correct after custom pairs.

**2. The published fee-program ABI does not match the deployed program.**
The fee-program instruction actually invoked inside trades carries discriminator
`297ebd54ab49eeee`, which is absent from
`pump-fun/pump-public-docs/idl/pump_fees.json` and from every published npm SDK build
we checked (pump-sdk 1.37.0 → 4.0.0; all 30–31 published discriminators follow
`sha256("global:" + name)[:8]`, none match). Is the deployed build ahead of the
published IDL, or is this an internal instruction? Either way, external reconciliation
needs the matching ABI.

**3. Method check (no contradiction found).** A bottom-up net-inflow floor built from
mint-level data equals ~16% of DefiLlama's curve-fee figure over the same 34 days —
consistent with how often funds turn over on the curve, and useful as an independent
sanity check rather than a contradiction.

## What we propose

A short paid diagnostic (2–3 weeks):

- reconstruct daily **protocol / buyback / creator** revenue directly from chain data
  (published fee recipients + PDAs + the matching ABI), **including custom pairs**,
  with an explicit and documented valuation policy for quote assets;
- reconcile it against your dashboard and third-party aggregators, and attribute every
  difference (timing, scope, or valuation);
- leave you with a reproducible pipeline (raw data → labels → metrics) that your team
  can rerun daily, and a monitoring script that flags divergence.

We are not asking to replace your data team. The point of an external reconciliation is
independence: a second method that does not reuse your own accounting.

## Proposed first step

A 30-minute call with whoever owns the fees dashboard, plus a single day of data
(a CSV or sandbox export) to validate our chain reconstruction against your ledger.

## Questions we would like to close first

1. Which fee-program build is deployed, and can we receive the matching IDL?
2. What is the dashboard's revenue definition (window, gross/net, custom pairs,
   quote-asset handling)?
3. How is the 50% buyback calculated, and from which revenue figure?
4. What valuation policy is used for custom-pair quote assets?
5. How are creator fees and the Mayhem insurance fund treated in revenue?
6. Is PumpSwap's 0.05% protocol share included in the buyback pool?
7. Can we validate against a single-day export from your ledger?

---

*Prepared from pump.fun's public documentation (`pump-public-docs`), public RPC reads of
the published fee-recipient addresses, DefiLlama, and the loopholetape public capture.
All numbers reproducible on request.*
