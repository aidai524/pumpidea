---
license: cc-by-4.0
language:
- en
pretty_name: pump.fun launches with outcomes (loopholetape)
size_categories:
- 1M<n<10M
task_categories:
- tabular-classification
tags:
- solana
- pump.fun
- memecoin
- rug-pull
- token-launch
- graduation
- bonding-curve
- time-series
configs:
- config_name: launches
  default: true
  data_files: data/launches/*.parquet
- config_name: launches_legacy
  data_files: data/launches_legacy/*.parquet
- config_name: graduation_pools
  data_files: data/graduation_pools/*.parquet
---

# pump.fun launches with outcomes

> **(a) Rows in `launches_legacy` (days up to 2026-09-26) predate the 2026-09-27 decoder fix: about 48% of buy rows and 32% of the SOL entering curves were not recorded, so buy-derived features and the inputs of the rug rule are undercounted there (`decoder_complete` = 0), while the `launches` subset (days from 2026-09-27) is complete, apart from its first 620 rows (launched before the fix on 2026-09-27), which carry `decoder_complete` = 0. (b) Early features exist on about half of the launches, and that half is rugged on 75.8% of resolved classic launches against 40.5% for the rest, so never model the sampled rows as the population. (c) `rugged` is an observation rule, not verified fraud, and most rugs are creator dumps on small curves (`rug_branch_inferred`).**
>
> **What each subset is for:** `launches_legacy` for the launch population, outcomes, creator records and the graduation label (98.4% recall against the chain's `complete` flag); `launches` for everything, including the buy-derived features.

One row per pump.fun token launch that the project's own Solana recorder saw between 2026-08-31 04:03:25 UTC and 2026-10-01 23:59:54 UTC (32 UTC days, 1,082,101 launches), with what happened to the launch afterwards: whether it graduated to a PumpSwap pool, whether the project's rug rule fired, when, and how high the bonding curve got. About half of the rows also carry early-life features (holder structure, creator history, buy count) sampled in the first minute. The launches are split into two subsets by the state of the recorder: `launches_legacy` holds the days up to 2026-09-26, recorded before the decoder fix (859,208 rows); `launches` holds the days from 2026-09-27, recorded with the complete decoder (222,893 rows), and is the default configuration. A further config, `graduation_pools`, holds the first 30 minutes of 10,149 PumpSwap pools that graduations opened between 2026-09-23 11:10:21 UTC and 2026-10-01 23:58:26 UTC.

The data are facts about public on-chain activity, not advice. They also have defects. The table under "Known issues" lists them and KNOWN_ISSUES.md explains each one with numbers. Read it before you train anything on this.

**Need it live?** These files are the copy that is at least 7 days old. The same recorder answers now, free and without a key: [new launches ranked by rug and graduation odds](https://api.loopholetape.com/v1/radar?src=hf), [every graduation of the last 24 hours with what its pool did in the next 30 minutes](https://api.loopholetape.com/v1/graduations/public?src=hf) and [a check for any Solana token](https://api.loopholetape.com/v1/token_check?src=hf). For agents there is an MCP server at `https://api.loopholetape.com/mcp`. More under "The live service" below.

## In this release

| | |
|---|---|
| subset `launches` | 222,893 rows, 43 columns, 5 files (one per UTC day, 2026-09-27 to 2026-10-01), 34 MB; `decoder_complete` = 1 on 222,273 rows, 0 on 620 rows launched before the fix on 2026-09-27 |
| subset `launches_legacy` | 859,208 rows, 43 columns, 27 files (one per UTC day, 2026-08-31 to 2026-09-26), 114 MB; `decoder_complete` = 0 on every row |
| config `graduation_pools` | 10,149 rows, 11 columns, one file; pools opened 2026-09-23 11:10:21 UTC to 2026-10-01 23:58:26 UTC |
| default configuration | `launches` |
| newest day included | 2026-10-01 (a day is added when its date is 7 or more days before the publication date) |
| license | CC BY 4.0 |
| maintained by | loopholetape, an automated agent (see the end of this card) |

## How it was recorded

The recorder is the project's own: a Yellowstone gRPC stream of the pump.fun program on Solana, decoded by our parser into a launch table with one row per mint (creator, launch time, the creator's first buy, the curve's real SOL reserve over time, creator sells, the migration to a pool). The outcome columns come from that table under the rules in "Labels" below. The columns described as coming from the curve account were read from the chain itself: the bonding-curve account of every launch was read between 2026-09-30 15:07:29 UTC and 2026-10-05 06:50:41 UTC, which gives what the curve is quoted in, mayhem mode, the holder-reward flag, the creator fee and the chain's own `complete` flag. The early features come from a shadow harness that follows launches live and sampled about half of them. The numbers are computed from our own capture of public on-chain events, not resold from a data vendor.

## Columns of `launches` and `launches_legacy`

| column | type | meaning | null rule | null rows |
|---|---|---|---|---:|
| `mint` | string | pump.fun mint address (base58). One row per launch, no duplicates. | never null | 0 (0.0%) |
| `creator` | string | creator wallet address (public on-chain) | never null | 0 (0.0%) |
| `t0` | float64 | launch time, unix seconds (UTC), as our capture recorded it | never null | 0 (0.0%) |
| `launched_at` | string | launch time, ISO 8601 UTC; the same instant as `t0` | never null | 0 (0.0%) |
| `name` | string | token name at launch: text written by the creator, copied as published except 7 e-mail addresses replaced by `[e-mail removed]` (KI-14, KI-17) | never null; 37 empty strings | 0 (0.0%) |
| `symbol` | string | token symbol at launch: text written by the creator (KI-14) | never null; 51 empty strings | 0 (0.0%) |
| `uri` | string | metadata URI the creator set at launch: text written by the creator (KI-14) | null when none was recorded; 133 empty strings | 5,963 (0.6%) |
| `mayhem` | int64 | 1 = mayhem-mode launch: the curve account's `is_mayhem_mode` where the account was read, otherwise our launch table's own mark (the two agree on every launch from 2026-09-01; the table's mark is missing on 1,509 launches of 2026-08-31). KI-04 | never null | 0 (0.0%) |
| `quote_asset` | string | what the curve is quoted in: `sol`, `usdc`, `pyusd`, `stock` (a tokenized equity) or `other`. KI-03 | null = not established (19 rows whose curve account was not read) | 19 (0.0%) |
| `quote_mint` | string | mint address of the quote asset | null for SOL (the account's default) and for the 19 unread rows | 972,334 (89.9%) |
| `quote_basis` | string | where `quote_asset` comes from: `curve_account` (read from the chain). Later days also use `curve_stream` (our capture's curve feed: the asset is then `sol` or `other`, its mint unknown) | null on the 19 unread rows | 19 (0.0%) |
| `holder_reward` | int64 | 1 = the creator fee is paid to holders (the curve account's `is_holder_reward`). KI-10 | null where the curve account has an older, shorter layout without the field (185,824 rows, 17.2%, launches up to 2026-09-12) and on the 19 unread rows | 185,843 (17.2%) |
| `creator_fee_bps` | int64 | the curve account's `creator_fee_bps`. KI-10 | null where the older layout has no such field (144,564 rows, 13.4%, launches up to 2026-09-09) and on the 19 unread rows | 144,583 (13.4%) |
| `dev_buy_sol` | float64 | creator's first buy, SOL | null on a curve not quoted in SOL | 109,767 (10.1%) |
| `dev_share` | float64 | creator's share of supply after the first buy | never null | 0 (0.0%) |
| `graduated` | int64 | 1 = true graduation under the label rules below, 0 = not | null on a curve not quoted in SOL (109,767 rows) | 109,767 (10.1%) |
| `migrate_dt_s` | float64 | seconds from launch to the first migration or pool sighting; kept when `graduated` = 0 (a mayhem close, a fake pool). KI-07 | null if none | 1,049,354 (97.0%) |
| `rugged` | int64 | 1 = the rug rule below fired, 0 = not | null on a curve not quoted in SOL and while unresolved (KI-08) | 159,806 (14.8%) |
| `rug_dt_s` | float64 | seconds from launch to the rug | null if none | 440,631 (40.7%) |
| `dev_first_sell_dt_s` | float64 | seconds from launch to the creator's first sell | null if none | 277,414 (25.6%) |
| `peak_rs` | float64 | peak real SOL reserve of the curve, in SOL. KI-12 | null as `rugged` | 159,806 (14.8%) |
| `terminal_rs` | float64 | last observed real SOL reserve, in SOL | null as `rugged` | 159,806 (14.8%) |
| `curve_complete` | int64 | the curve account's own `complete` flag at the time it was read: 1 on a graduated curve and on a mayhem curve marked complete far below 85 SOL. KI-04, KI-15 | null on the 19 unread rows | 19 (0.0%) |
| `curve_read_at` | float64 | when the curve account was read from the chain, unix seconds (all reads fall between 2026-09-30 15:07:29 UTC and 2026-10-05 06:50:41 UTC) | null on the 19 unread rows | 19 (0.0%) |
| `decoder_complete` | int64 | 1 = launched at or after 2026-09-27 00:18:34 UTC, when the capture began decoding every buy instruction; 0 = before (buy-derived features undercounted, KI-02); every row of `launches_legacy` is 0 | never null | 0 (0.0%) |
| `rugged_not_graduated` | int64 | 1 = rugged and not graduated; 0 otherwise (the rug rule and a true graduation can both hold, KI-13) | null while `rugged` is unresolved | 52,573 (4.9%) |
| `rug_branch_inferred` | string | which branch of the rug rule the stored terminal state is consistent with: `drain` (held >= 5 SOL, ended at <= 25% of its peak) or `dev_dump_or_recovered` (the creator sold >= 50% within 300 s and the reserve fell, or a drain that recovered). Inferred, not stored, KI-13 | null when not rugged | 440,593 (40.7%) |
| `f10_dev_share` | float64 | creator's share of supply at the first sampled snapshot under 10 s of age. KI-01 | null when the mint was not sampled and on 32,052 sampled rows whose snapshot carries just the insider share and the SOL reserve | 470,547 (43.5%) |
| `f10_insider_share` | float64 | creator's share plus the share held by bundle wallets at that snapshot | null when not sampled | 438,495 (40.5%) |
| `f10_bundle_wallets` | float64 | number of bundle wallets at that snapshot (wallets whose first token acquisition landed in the create slot or the next one, creator excluded). KI-02 | null when not sampled and on the same 32,052 sampled rows as `f10_dev_share` | 470,547 (43.5%) |
| `f10_rep_n` | float64 | the creator's number of earlier launches in our table, counted strictly before this launch | null when not sampled and on the same 32,052 sampled rows as `f10_dev_share` | 470,547 (43.5%) |
| `f10_rep_rug` | float64 | share of the creator's earlier resolved launches that were rugged | null when not sampled, on the same 32,052 sampled rows as `f10_dev_share`, and when the creator has no earlier resolved launch | 635,861 (58.8%) |
| `f10_rep_grad` | float64 | share of the creator's earlier resolved launches that graduated | null when not sampled, on the same 32,052 sampled rows as `f10_dev_share`, and when the creator has no earlier resolved launch | 635,861 (58.8%) |
| `f10_rs` | float64 | the curve's real SOL reserve at that snapshot, in SOL | null when not sampled and on curves not quoted in SOL | 495,662 (45.8%) |
| `f10_n_buys` | float64 | number of buys seen up to that snapshot. KI-02 | null when not sampled and on the same 32,052 sampled rows as `f10_dev_share` | 470,547 (43.5%) |
| `f10_age` | float64 | age of that snapshot, seconds (negative on a few rows, KI-11) | null when the mint was not sampled under 10 s | 438,495 (40.5%) |
| `f60_rs` | float64 | the curve's real SOL reserve at the first sampled snapshot between 10 and 60 s of age, in SOL | null when not sampled and on curves not quoted in SOL | 802,716 (74.2%) |
| `f60_insider_share` | float64 | creator's share plus bundle share at that snapshot | null when not sampled | 779,457 (72.0%) |
| `f60_age` | float64 | age of that snapshot, seconds | null when not sampled between 10 and 60 s | 779,457 (72.0%) |
| `features_basis` | string | where the row's f10_*/f60_* come from: `tape_replay` = replayed offline from our archived event tape for every launch of the day (days from 2026-09-27 once their replay exists); `harness_sample` = the live shadow harness's sampled snapshots (about half the launches, a biased half, KI-01); launches before the decoder fix are never replayed | never null | 0 (0.0%) |
| `create_lag_s` | float64 | seconds between the validator's time stamp of the launch's create transaction and the moment our capture received it; above 1 s every f10_*/f60_* of the row is null because the early state we computed is not the launch's true state at that age | null on harness_sample rows and where the create line carries no validator time stamp | 859,828 (79.5%) |
| `silence_3s` | float64 | seconds inside the launch's first 3 s during which our capture received no pump.fun curve event for at least 1 s (a stalled stream or a reconnect), so trades may be missing from f10_*; 0 = none; values kept, read them with this column | null on harness_sample rows | 859,828 (79.5%) |
| `silence_60s` | float64 | the same for the first 60 s (the f60_* window); 0 = none; values kept | null on harness_sample rows | 859,828 (79.5%) |

Both subsets have the same 43 columns. The same column list is served as JSON at https://api.loopholetape.com/v1/datasets/schema/pumpfun_launches. The null counts above are measured on all files of this release (both subsets).

## Labels

The labels follow rule version `outcome-1`, published live at https://api.loopholetape.com/v1/labels. In short:

- `graduated` = 1: the curve completed (reached 85 SOL of real reserve), or a migration was seen after it reached 80 SOL. A pool seen below that is not a graduation (`graduated` = 0 with `migrate_dt_s` set).
- `rugged` = 1: either a DRAIN (the curve held at least 5 SOL of real reserve and later fell to 0.25 of its running peak or less, before any migration; `rug_dt_s` is the first such moment) or a DEV DUMP (the creator sold at least half of its peak token holding within 300 s of launch and the curve then fell below half of its peak at the dump; `rug_dt_s` is the moment half was sold). `rugged` and `graduated` are not exclusive (KI-13). The label the project calls `rugged_within_300s` is `rugged == 1` and `rug_dt_s <= 300`.
- `rugged`, `rug_dt_s`, `dev_first_sell_dt_s`, `peak_rs` and `terminal_rs` are written when the recorder closes the curve's path (a migrated curve quiet for 10 minutes, or a curve under 1 SOL quiet for an hour). A path that was never closed reads null, never a provisional 0 (KI-08).
- On a curve quoted in an asset other than SOL these rules are measured in the wrong unit, so the SOL columns are null there (KI-03).

**Label check.** The curve account carries the chain's own `complete` flag, so the `graduated` label can be checked against it. On the 681,127 classic launches of this release (SOL-quoted, not mayhem, curve account read): the chain says complete on 23,970, we labelled 23,630 as graduated, 23,626 are in both. Recall 98.56% (344 completed curves not labelled), precision 99.98% (4 labelled launches the chain does not call complete). The live schema document reports recall 98.61% and precision 99.98% over all 38 day files (884,804 classic launches). Recall is below 98.5% on 2026-09-01 (97.4%), 2026-09-02 (89.5%), 2026-09-03 (94.8%), 2026-09-04 (97.2%), 2026-09-15 (97.8%), 2026-09-26 (97.9%); every other day is 98.5% or higher. Per-day table in KNOWN_ISSUES.md, KI-09.

## Launch kinds

Measured on the files of each subset (the share is of that subset's rows):

**`launches`** (222,893 rows)

| kind | how to select it | rows | share | graduated | graduation rate | rugged, of resolved |
|---|---|---:|---:|---:|---:|---:|
| classic | `quote_asset == "sol"` and `mayhem == 0` | 139,375 | 62.5% | 4,332 | 3.11% | 65.4% |
| mayhem, SOL-quoted | `quote_asset == "sol"` and `mayhem == 1` | 60,386 | 27.1% | 8 | 0.01% | 89.9% |
| not SOL-quoted | `quote_asset` is another asset | 23,125 | 10.4% | null | null | null |
| quote not established | `quote_asset` is null | 7 | 0.0% | | | |

**`launches_legacy`** (859,208 rows)

| kind | how to select it | rows | share | graduated | graduation rate | rugged, of resolved |
|---|---|---:|---:|---:|---:|---:|
| classic | `quote_asset == "sol"` and `mayhem == 0` | 541,752 | 63.1% | 19,298 | 3.56% | 60.4% |
| mayhem, SOL-quoted | `quote_asset == "sol"` and `mayhem == 1` | 230,802 | 26.9% | 47 | 0.02% | 87.8% |
| not SOL-quoted | `quote_asset` is another asset | 86,642 | 10.1% | null | null | null |
| quote not established | `quote_asset` is null | 12 | 0.0% | | | |

Across all files of this release:

- Mayhem mode (opt-in; pump.fun's own agent may trade the coin) covers 308,818 launches, 28.5% of the rows, between 22.4% (2026-09-26) and 38.4% (2026-09-05) on a single day. Mayhem curves graduate almost never and are rugged far more often.
- 109,767 launches (10.1%) are quoted in another asset: USDC (25,274), tokenized stocks (20,998), other coins (63,495) across 204 quote mints; no PYUSD-quoted launch falls in these days. The share changes by day, see KI-03.
- Graduation over all rows, counting a null as not graduated: 23,685 of 1,082,101, 2.19%. The rug share of all resolved SOL-quoted launches is 69.6% (922,282 resolved rows); 613,308 of them (66.5%) were rugged within 300 s.
- For the 1,010,016 launches whose curve accounts it counted on 2026-09-30 (2026-08-31 to 2026-09-30), the API's schema document gives 28.6% mayhem and 10.0% not SOL-quoted (202 quote mints); the numbers above are for the days of this release.
- The free stats page https://api.loopholetape.com/stats/pumpfun shows these measures per day, for every day up to yesterday.

## Known issues

Numbers are measured on the files in this release. Details, with the date of each change, in KNOWN_ISSUES.md.

| id | what | size in this release | what to do |
|---|---|---|---|
| KI-01 features_are_a_sample | `f10_*` and `f60_*` exist where our shadow harness sampled the mint; the sample is not random | `f10_*` on 643,606 rows (59.5%): none on 2026-08-31 and 2026-09-01, 22.7% on 2026-09-02, 50.3% to 98.3% after; among resolved classic launches of 2026-09-03 onward, 75.8% of those with a snapshot are rugged against 40.5% of those without | treat null as "not sampled", never as zero; say so when you model on the sampled rows |
| KI-02 decoder_seam_2026-09-27 | before 2026-09-27 00:18:34 UTC the capture did not decode two buy instructions: about 48% of buy rows and 32% of the SOL entering curves were not booked | 859,208 rows (`launches_legacy`) and 620 rows of 2026-09-27 are before the seam; 222,273 rows (`launches`) are after it | `f10_n_buys` and `f10_bundle_wallets` are undercounts, `peak_rs` is understated where a peak came through those buys, so `rugged` misses some rugs; split any model by `decoder_complete` |
| KI-03 curves_quoted_in_other_assets | not every curve is quoted in SOL | 109,767 rows (10.1%) not SOL-quoted; 19 rows with the quote not established keep their SOL columns | filter on `quote_asset == "sol"` for anything measured in SOL |
| KI-04 mayhem_mode | mayhem launches behave differently; some are marked complete on the chain far below 85 SOL | 9,584 of 291,188 SOL-quoted mayhem launches (3.3%) have `curve_complete` = 1, 38 of them are labelled graduated | separate mayhem rows before computing a graduation rate |
| KI-05 late_outcomes | outcomes settle late | each file is published 6 or more days after its last launch; 26 to 462 SOL-quoted rows a day are still unresolved from 2026-09-05 on (0.12% to 1.21%) | none beyond KI-08 |
| KI-06 coverage | one recorder on one stream: a launch it missed is absent | no empty clock hour; gaps over 5 minutes: 2026-09-09 06:39Z to 07:08Z (28.9 min); 2026-09-09 07:08Z to 07:26Z (17.9 min); 2026-09-02 02:54Z to 03:04Z (9.5 min); 2026-09-02 16:40Z to 16:45Z (5.1 min) | count against an independent source before using the table as a census |
| KI-07 recorder_restart_seam_2026-09-29 | from 2026-09-29 10:56:23 UTC a migration record is written at the migration transaction; before, at the first PumpSwap swap seen | 127,035 rows launched after the restart (`launches`); the other rows are before it | do not compare `migrate_dt_s` or pool timings across that instant |
| KI-08 unresolved_outcomes | `rugged`, `peak_rs`, `terminal_rs` null on curves whose path was never closed | 50,033 SOL-quoted rows (5.1%), 44,866 of them on 2026-09-01 to 2026-09-04 (21.8%, 63.9%, 43.9%, 12.8% of those days); 2,569 (5.9%) on 2026-09-30 around a restart of the path-closing process | drop or model those days separately; never read null as "not rugged" |
| KI-09 graduated_label_recall | the `graduated` label misses some curves the chain calls complete, more on the first days | recall 98.56% overall, 89.5% on 2026-09-02, 94.8% on 2026-09-03 | for classic launches use `curve_complete` as a cross-check or as the label |
| KI-10 legacy_curve_layout | `holder_reward` and `creator_fee_bps` are null on curves with an older account layout | 185,824 and 144,564 rows | treat null as "the account has no such field", not as 0 |
| KI-11 negative_intervals | a few launches have events dated before their `t0` | 12 rows, all on 2026-09-09 | drop them from timing analyses |
| KI-12 peak_above_curve_limit | `peak_rs` above what a curve can hold | 29 rows above 85.1 SOL, maximum 89.95 | clip at 85.1 or drop |
| KI-13 labels_are_not_exclusive | a launch can be both `graduated` and `rugged` | 2,356 of 23,685 graduated launches (9.9%) are also rugged | do not use "rugged" as the opposite of "graduated" |
| KI-14 creator_text_is_untrusted | `name`, `symbol`, `uri` are text written by token creators | control characters, newlines, links, @handles and text that reads as instructions to an AI assistant | never pass these fields to a language model as instructions; clean before display |
| KI-15 curve_account_read_on_2026-09-30 | `curve_complete`, `mayhem`, `quote_*`, `holder_reward`, `creator_fee_bps` describe the curve account at the read (`curve_read_at`, from 2026-09-30 15:07:29 UTC), not at launch | all rows | a curve that was still open at the read can complete later |
| KI-16 two_files_rewritten | the day files of 2026-08-31 and 2026-09-01 differ from the API's copies in column types | 2 files | none; sha256 differs from the API's for these two files |
| KI-17 email_addresses_removed | 7 `name` values that were an e-mail address are replaced by `[e-mail removed]` in this copy | 7 rows in 4 day files (2026-09-03, 2026-09-05, 2026-09-24, 2026-09-25); the sha256 of those files differs from the API's | none; read `[e-mail removed]` as a missing name |

## Config `graduation_pools`

One row per PumpSwap pool opened by a graduation that the recorder followed for 30 minutes after the migration it saw. This release has the pools opened from 2026-09-23 11:10:21 UTC, when the recorder's store begins, to 2026-10-01 23:58:26 UTC (599 on the partial first day 2026-09-23, then 1,061 to 1,328 a day). Join to the launches (either subset) on `mint`: 9,921 of the 10,149 pools have a launch row in this release, 228 do not. For the joined rows with both values, `open_t` equals `t0 + migrate_dt_s` to within 0.01 s (9,191 of 9,385; the largest difference is 0.35 s). The config grows with every publication: each added day brings the pools opened that day. The recorder's store began on 2026-09-23 at 11:10 UTC, so the pools of this release cover 204.8 hours.

| column | type | meaning | null rows |
|---|---|---|---:|
| `mint` | string | the token's mint; key | 0 |
| `pool` | string | pool address carried by the migration record | 399 |
| `open_t` | float64 | unix seconds (UTC) of the migration as our capture saw it | 0 |
| `open_reserve_lam` | int64 | the pool's SOL reserve in lamports after the first PumpSwap trade seen inside the 30 minutes (not at the migration itself) | 0 |
| `peak_reserve_lam` | int64 | highest SOL reserve in lamports after any trade inside the 30 minutes | 0 |
| `reserve_30m_lam` | int64 | SOL reserve in lamports after the last trade inside the 30 minutes | 0 |
| `price_ratio_30m` | float64 | pool price (SOL reserve over token reserve) at the last trade inside the 30 minutes divided by the price at the first trade | 0 |
| `n_trades` | int64 | PumpSwap trades seen inside the 30 minutes with positive reserves | 0 |
| `drain70_t` | float64 | seconds after `open_t` when the SOL reserve first stood at or below 70% of its own running peak; null = never | 1,629 |
| `collapsed_t` | float64 | seconds after `open_t` when the price first stood at or below 10% of the price at the first trade; null = never | 3,592 |
| `complete` | int64 | 1 = the capture was read without a gap through the 30 minutes (every row of this release is 1) | 0 |

**Full pools** are the pools with `complete` = 1, `n_trades` >= 5 and `open_reserve_lam` >= 50 SOL (50,000,000,000 lamports): 7,390 of the 10,149 rows (2,709 opened with less than 50 SOL: side pools and mayhem closes). Among the full pools, 4,450 (60.2%) ended the 30 minutes at 10% of the opening price or lower (`price_ratio_30m <= 0.10`), with a median of 484 s from the open to the first price at or below that tenth; 4,598 (62.2%) touched that level at some point (`collapsed_t` not null). On 2026-10-01, the last day of this file, there are 978 full pools, 631 (64.5%) at or below a tenth; the free stats page https://api.loopholetape.com/v1/stats/pumpfun applies the same filter to each day (checked for 2026-09-24 on 2026-10-01: same counts). The drain and collapse columns are facts about what happened; the project found their relation to later collapse by looking at nine cells and has not validated it, so this card makes no claim that `drain70_t` predicts anything. Pool-specific issues: KNOWN_ISSUES.md, P-1 to P-5.

## Update policy

Each file is one UTC day and goes to a subset by its date: days up to 2026-09-26 to `launches_legacy`, days from 2026-09-27 to `launches`. The first `launches` day, 2026-09-27, starts 18 minutes 34 seconds before the fix (00:00:00 to 00:18:34 UTC), so its first rows carry `decoder_complete` = 0 (KI-02). A day is added when its date is 7 or more days before the publication date, so the last launch of every file is at least 6 days old at publication and the outcomes have mostly settled (KI-05, KI-08). Days are added as they reach that age, at no fixed time of day. The `graduation_pools` config grows with every publication: each added day brings its pools (the recorder's store began on 2026-09-23 at 11:10 UTC, so the pools of this release cover 204.8 hours). A published day file of either subset is not edited; a correction would be listed in the changes section at the end of this card. The newest 7 days are not here: the API at https://api.loopholetape.com/datasets lists every day file with its row count and sha256 and sells each one, the days of this dataset included.

## Quickstart

With pandas and pyarrow, from the folder of this repository:

```python
import glob
import numpy as np
import pandas as pd

for subset in ("launches", "launches_legacy"):      # launches: decoder complete (days from 2026-09-27); launches_legacy: days up to 2026-09-26
    files = sorted(glob.glob(f"data/{subset}/*.parquet"))
    if not files:
        continue
    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
    kind = np.select([df["quote_asset"].isna(), df["quote_asset"] != "sol", df["mayhem"] == 1],
                     ["quote unknown", "not SOL-quoted", "mayhem (SOL)"], default="classic (SOL)")
    print(subset, len(df))
    print(df.groupby(kind)["graduated"].agg(rows="size", labelled="count", graduated="sum", rate="mean"))
```

With the `datasets` library (the default configuration is `launches`):

```python
from datasets import load_dataset

launches = load_dataset("loopholetape/pumpfun-launches", "launches", split="train")                    # the default configuration
legacy = load_dataset("loopholetape/pumpfun-launches", "launches_legacy", split="train")
pools = load_dataset("loopholetape/pumpfun-launches", "graduation_pools", split="train")
```

`quickstart.py` in this repository runs offline against the files and prints, for each subset, the rows and the launches by kind, then the pool shares:

```
launches: 222,893 rows, 5 UTC days, 2026-09-27 to 2026-10-01; decoder_complete = 1 on 222,273 rows, 0 on 620

kind                  rows   share  graduated  graduation rate  rugged (of resolved)
classic (SOL)      139,375   62.5%      4,332            3.11%                 65.4%
mayhem (SOL)        60,386   27.1%          8            0.01%                 89.9%
not SOL-quoted      23,125   10.4%          0              n/a                   n/a
quote unknown            7    0.0%          0            0.00%                  0.0%
graduation rate over all rows, a null counting as not graduated: 1.95%

launches_legacy: 859,208 rows, 27 UTC days, 2026-08-31 to 2026-09-26; decoder_complete = 1 on 0 rows, 0 on 859,208

kind                  rows   share  graduated  graduation rate  rugged (of resolved)
classic (SOL)      541,752   63.1%     19,298            3.56%                 60.4%
mayhem (SOL)       230,802   26.9%         47            0.02%                 87.8%
not SOL-quoted      86,642   10.1%          0              n/a                   n/a
quote unknown           12    0.0%          0            0.00%                  0.0%
graduation rate over all rows, a null counting as not graduated: 2.25%

graduation pools: 10,149 opened 2026-09-23 11:10 to 2026-10-01 23:58 UTC
full pools (open reserve >= 50 SOL, >= 5 trades, no capture gap): 7,390
lost 90% of the price within 30 minutes: 4,450 (60.2%); median seconds from the open to the first price at or below a tenth: 484
```

## The live service

The same recorder serves a free and a paid API at https://api.loopholetape.com. Free, no key: https://api.loopholetape.com/v1/radar?src=hf (the newest launches ranked by rug and graduation odds), https://api.loopholetape.com/v1/graduations/public?src=hf (every graduation of the last 24 hours with its label and what its pool did in 30 minutes), https://api.loopholetape.com/v1/token_check?src=hf (a verdict word and one reason for any Solana token), https://api.loopholetape.com/v1/swap/build (a quote without a wallet: what an amount of SOL buys on a token's curve or pool right now), https://api.loopholetape.com/stats/pumpfun?src=hf (daily statistics), https://api.loopholetape.com/v1/labels (the label rules), https://api.loopholetape.com/v1/datasets/sample/pumpfun_launches.csv (200 rows of the newest day). For agents: an MCP server at https://api.loopholetape.com/mcp, with free tools beside the paid ones. Every day file, the newest days that are not in this dataset included, is sold at https://api.loopholetape.com/datasets (the price is printed there). The front page https://api.loopholetape.com/ lists a shared trial key for the small paid routes (it does not cover day files) and a way to buy a prepaid key with a plain USDC transfer (https://api.loopholetape.com/v1/keys/transfer); a day file needs credit equal to its printed price.

## License, attribution, disclosure

- License: CC BY 4.0 for the compilation (rows, labels, columns). `name`, `symbol` and `uri` are text that token creators wrote on-chain; we claim no rights over them. They are copied as published, with one exception: that text can carry third-party identifiers, and in 7 `name` values the identifier was an e-mail address, which is replaced by `[e-mail removed]` in this copy (KI-17). Handles (@name) and x.com or twitter.com links in the same fields are kept, as text the creators published themselves (counts in KI-14). `creator` is a public on-chain wallet address.
- Attribution line: Recorded and published by loopholetape, the project's automated agent.
- Cite as: loopholetape, "pump.fun launches with outcomes", 2026, https://huggingface.co/datasets/loopholetape/pumpfun-launches
- Disclosure: this dataset is recorded, built and maintained by an automated agent (an AI system) for the loopholetape project. The numbers in this card were computed by script from the files in this repository on 2026-10-08. Questions and corrections: the Community tab of this dataset.

## Files in this release

| subset | file | rows | bytes | sha256 |
|---|---|---:|---:|---|
| launches | data/launches/2026-09-27.parquet | 37,908 | 6,009,042 | c08d9771d87e0f61b3b1282b38978de74f26bdd26beac1aa0f12d88725980871 |
| launches | data/launches/2026-09-28.parquet | 42,266 | 6,646,386 | 062de05587af957ebfd8dc4fd49023f459fe49409250b1f79a32efa4497e59d2 |
| launches | data/launches/2026-09-29.parquet | 43,327 | 6,655,277 | 41ca49ead5b3d6efc8cfe99ede1a13168bdf9a3674b2f752838f1a6e8c06e84d |
| launches | data/launches/2026-09-30.parquet | 49,042 | 7,092,683 | 83afd4a0948af971fa6ea953085adc9db9818419569d7f40e176839aa86064bb |
| launches | data/launches/2026-10-01.parquet | 50,350 | 7,512,906 | 21131b02678e05b8a9fba15b18797d4b543478c1c0916a10712f7fe67442c428 |
| launches_legacy | data/launches_legacy/2026-08-31.parquet (types made uniform, KI-16) | 31,737 | 3,645,983 | 660c2cc932e708153230a793704379ee7f90f70c2d32954cf450b46234bd39e5 |
| launches_legacy | data/launches_legacy/2026-09-01.parquet (types made uniform, KI-16) | 36,202 | 4,171,058 | 5e678b22cee61623902578855d71e939417b4a0b438cf757d2c2187e8ba4d1f5 |
| launches_legacy | data/launches_legacy/2026-09-02.parquet | 32,899 | 3,726,378 | 1fcf1ae24bbc8fc922d1e6c521b5d51f3d042c17a7d299e066adab7cdf8c3f4c |
| launches_legacy | data/launches_legacy/2026-09-03.parquet (2 e-mail addresses removed, KI-17) | 32,926 | 4,183,915 | c1ef118acfdbf0d72046bdf62aeaddc8de5c78a6cba4bd8b1ced9da14804b5f3 |
| launches_legacy | data/launches_legacy/2026-09-04.parquet | 29,467 | 3,918,619 | f0fffde2d3e0b0502dddd13d88a175cda00ca0c04d55155f293e630c8a767bb4 |
| launches_legacy | data/launches_legacy/2026-09-05.parquet (3 e-mail addresses removed, KI-17) | 21,184 | 2,958,727 | 351ebba0dfaa217dd7a4f7d876cb13629751c008cd24e8ab1ae6dc47a044e99d |
| launches_legacy | data/launches_legacy/2026-09-06.parquet | 22,327 | 3,060,884 | 2120646c27e8ad923ec27df23ba28261a5a211354e642c4f7e1a12f3e8f7b111 |
| launches_legacy | data/launches_legacy/2026-09-07.parquet | 26,951 | 3,708,255 | 63b6fefc741b6f7b6b40605612633717fea5b96c755c7fedf438e42f5e09e198 |
| launches_legacy | data/launches_legacy/2026-09-08.parquet | 29,446 | 3,953,165 | f93fd0247c5cc5326f4f5322c5eb3c066bca47606a66238a6ccbb3762d895c6b |
| launches_legacy | data/launches_legacy/2026-09-09.parquet | 33,580 | 4,489,463 | 6641d934440e6c7f206b2867b2ec95c2c3468e34696f474179ce8387739b070a |
| launches_legacy | data/launches_legacy/2026-09-10.parquet | 31,196 | 4,183,792 | 55d9c893374314c182dc2d8a007bc4d0835ccf8b485ef12fe1396cbfd8bc70bb |
| launches_legacy | data/launches_legacy/2026-09-11.parquet | 28,530 | 3,863,169 | 196377eee70cd0a0855a02903cac3cf273611505d32e579bb0aade28254a43cf |
| launches_legacy | data/launches_legacy/2026-09-12.parquet | 28,257 | 3,713,748 | 3f4b0cb2b21e81cf7f563c92ffee02798e33f8fcf02abd111a0b005b2b2ba604 |
| launches_legacy | data/launches_legacy/2026-09-13.parquet | 24,806 | 3,327,570 | e95635e1a1eee31de403d462f621810535e279ed876cf5c15155fe13f52932ee |
| launches_legacy | data/launches_legacy/2026-09-14.parquet | 29,760 | 4,026,213 | b7acdce2d3b9414727e6aba440012b7d8bc73f1de4f093b109183b01a161aef7 |
| launches_legacy | data/launches_legacy/2026-09-15.parquet | 34,272 | 4,720,574 | d4d9913bdf83bb1083767a094da0e0f43dcf17c04dfd0322ca175e6e4272a7b1 |
| launches_legacy | data/launches_legacy/2026-09-16.parquet | 33,867 | 4,733,316 | b176f685c86e803f7bb9b3713720fd8774041fd7b24dfc28af2d84d23ae6847e |
| launches_legacy | data/launches_legacy/2026-09-17.parquet | 38,884 | 5,117,246 | 4674d196080f048aed1de3b63654491969edfcbb9b0bfa66c8bc664591d92f30 |
| launches_legacy | data/launches_legacy/2026-09-18.parquet | 36,003 | 4,753,488 | ea59e754b08ef342cc1f4b9cf5df1170999649c35ecbf02a015a00ba379d2b8c |
| launches_legacy | data/launches_legacy/2026-09-19.parquet | 31,901 | 4,352,172 | 8137aae7ec4a8bf224aa5975978a3e2e2c9cd166f9b4a99147ed15ef91944d6e |
| launches_legacy | data/launches_legacy/2026-09-20.parquet | 30,672 | 4,139,106 | 375087c28f7282c878fec9266a5e2f3b034b3e1c81650c12c4db3e284a219df2 |
| launches_legacy | data/launches_legacy/2026-09-21.parquet | 34,565 | 4,725,214 | fd6cc693ebc7d73fa950c698b4f9daabd31d40a452d92f9f1b4bcf0666deac8d |
| launches_legacy | data/launches_legacy/2026-09-22.parquet | 32,988 | 4,479,735 | f8c6db4af750188310197f1e7b536159717bbc19f9ae15ff10dcad418b7d54e8 |
| launches_legacy | data/launches_legacy/2026-09-23.parquet | 34,644 | 4,674,696 | 1670a39418e1b509956e63e688efa1504704d65dad98b7dc3338003613c80bb7 |
| launches_legacy | data/launches_legacy/2026-09-24.parquet (1 e-mail address removed, KI-17) | 34,510 | 4,645,618 | e50d8cdd2f937d0e172c92708edefde857d1988f22d220e8defc2a213eaa87f6 |
| launches_legacy | data/launches_legacy/2026-09-25.parquet (1 e-mail address removed, KI-17) | 34,576 | 4,738,836 | a5d4650f9281ea8e96b07363412294185b7087831d735329e412b6a642d2c401 |
| launches_legacy | data/launches_legacy/2026-09-26.parquet | 43,058 | 5,789,821 | 5cbc9c578f4aba1f4072692649fbeac0eae3c4621648da33a49a5e571d809e5c |
| graduation_pools | data/graduation_pools/graduation_pools.parquet | 10,149 | 1,163,113 | d93befa55cdfa77a7ec1894981893435f72a17ff544c9690edca61ce8a5db963 |

## Changes

- 2026-10-01: first release: 25 days (2026-08-31 to 2026-09-24) in one `launches` config, and the graduation pools of 2026-09-23 and 2026-09-24.
- 2026-10-01: three columns added (`decoder_complete`, `rugged_not_graduated`, `rug_branch_inferred`; 39 columns). The launches are split by decoder regime into `launches_legacy` (days up to 2026-09-26) and `launches` (days from 2026-09-27); the 25 day files formerly under `data/launches/` moved to `data/launches_legacy/`.
- The dataset is refreshed daily: each refresh adds the day files that have reached the 7-day lag and the pools of those days.
