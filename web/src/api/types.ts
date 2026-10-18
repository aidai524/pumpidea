/** 与 `/api/v1` 契约一一对应的类型。
 *
 * 这些类型是**前端对后端的唯一认知** —— 它们只反映 `api/app/normalize.py`
 * 定义的形状，不反映任何上游 JSON 的内部结构。
 *
 * 两条约定（后端用测试锁住了，见 api/tests/test_api.py）：
 *   1. 比率一律 0~1，字段名 `*_rate` / `*_share`
 *   2. 金额一律绝对 USD，字段名 `*_usd`
 * 所以这里没有 `*_pct`，也不需要在前端做 /100 或 *1e6。
 */

export type SourceStatus = {
  source: "analysis" | "audit" | "pulse" | "risk";
  ok: boolean;
  path?: string;
  url?: string;
  status_code?: number;
  generated_at?: string | null;
  file_mtime?: string | null;
  /** 数据多久以前生成的（秒）。**必须展示出来** —— 三条线频率差几个数量级。 */
  age_seconds?: number | null;
  error?: { code: string; message: string };
};

export type Health = {
  contract_version: string;
  checked_at: number;
  ok: boolean;
  sources: SourceStatus[];
};

export type Caveat = { key: string; title: string; detail: string };

export type Kpis = {
  launches: number | null;
  graduated: number | null;
  graduation_rate: number | null;
  organic_graduations: number | null;
  organic_graduation_rate: number | null;
  instant_graduations: number | null;
  instant_share_of_graduations: number | null;
  rugged_within_300s: number | null;
  rug_rate_within_300s: number | null;
  creator_sold_within_60s: number | null;
  creator_sold_within_60s_rate: number | null;
  median_seconds_to_graduation: number | null;
  median_seconds_to_graduation_organic: number | null;
};

export type KindBlock = {
  launches: number | null;
  share_of_launches: number | null;
  graduation_rate: number | null;
  complete_on_chain_share: number | null;
  rug_rate_within_300s: number | null;
  creator_sold_within_60s_rate: number | null;
};

export type DailyPoint = {
  day: string;
  settling: boolean;
  launches: number | null;
  graduation_rate: number | null;
  organic_graduation_rate: number | null;
  instant_share_of_graduations: number | null;
  rug_rate_within_300s: number | null;
  creator_sold_within_60s_rate: number | null;
};

export type WeeklyPoint = {
  from: string;
  to: string;
  launches_per_day: number | null;
  graduation_rate: number | null;
  organic_graduation_rate: number | null;
  instant_share_of_graduations: number | null;
  rug_rate_within_300s: number | null;
  creator_sold_within_60s_rate: number | null;
};

export type AnalysisOverview = {
  contract_version: string;
  generated_at: string | null;
  window: { from: string; to: string; days: number };
  kpis: Kpis;
  by_kind: Record<string, KindBlock>;
  daily: DailyPoint[];
  weekly: WeeklyPoint[];
  trend: {
    launches_growth: number | null;
    graduation_rate_pp: number | null;
    organic_graduation_rate_pp: number | null;
    instant_share_pp: number | null;
  };
  label_check: { recall: number | null; precision: number | null; n: number | null };
  pools: {
    full_pools: number | null;
    share_lost_90pct_in_30m: number | null;
    median_seconds_to_collapse: number | null;
  };
  caveats: Caveat[];
};

export type Distribution = { percentiles: Record<string, number | null> } & {
  n?: number | null;
  share_zero?: number | null;
  share_ge5?: number | null;
  share_ge10?: number | null;
};

export type AnalysisCreators = {
  contract_version: string;
  generated_at: string | null;
  concentration: {
    creators: number | null;
    launches: number | null;
    per_creator_mean: number | null;
    top1: number | null;
    top1_share: number | null;
    top10_share: number | null;
    top100_share: number | null;
    top1000_share: number | null;
    creators_for_half: number | null;
    creators_for_half_share: number | null;
  };
  veteran_by_prior_launches: {
    bucket: string;
    n: number | null;
    graduation_rate: number | null;
    rug_rate: number | null;
    mean_prior_rugs: number | null;
    mean_dev_share: number | null;
    mean_bundle_wallets: number | null;
  }[];
  veteran_sample: {
    rows: number | null;
    tape_replay_rows: number | null;
    tape_replay_missing_rate: number | null;
  };
  bundling: Distribution;
  dev_share_distribution: Distribution;
  peak_rs: { percentiles: Record<string, number | null> } & { n?: number | null };
  tickers: {
    unique: number | null;
    launches: number | null;
    mean_per_ticker: number | null;
    top: { ticker: string; n: number | null; graduated: number | null; rug_rate: number | null }[];
  };
};

export type FeeBlock = {
  protocol_fee: number | null;
  creator_fee: number | null;
  buyback_fee: number | null;
  lp_fee: number | null;
  cashback: number | null;
  holder_rewards: number | null;
  total: number | null;
};

export type AnalysisEconomics = {
  contract_version: string;
  generated_at: string | null;
  structure: Record<"launchpad" | "pumpswap" | "combined", {
    volume_usd: number | null;
    fees_usd: number | null;
    revenue_usd: number | null;
    revenue_rate: number | null;
  }>;
  mix: { pumpswap_volume_share: number | null; pumpswap_revenue_share: number | null };
  fee_floor: {
    window_days: number | null;
    sum_peak_rs_sol: number | null;
    sol_usd: number | null;
    sol_usd_source: string | null;
    volume_floor_usd: number | null;
    fee_floor_gross_usd: number | null;
    fee_floor_protocol_usd: number | null;
    note: string | null;
  };
  caveats: Caveat[];
};

export type AuditSummary = {
  contract_version: string;
  generated_at: string | null;
  sol_usd: number | null;
  lines: string[];
  health: {
    events: number | null;
    first_ts: number | null;
    last_ts: number | null;
    last_age_s: number | null;
    last_10min_events: number | null;
  };
  pricing_quality: {
    mints_total: number | null;
    mints_chosen: number | null;
    priced: number | null;
    major_quote: number | null;
    high_dispersion: number | null;
    min_liquidity_usd: number | null;
  };
  daily: {
    day: string;
    all: FeeBlock;
    liq: FeeBlock;
    n_events: number | null;
    unpriced_mints: number | null;
    illiquid_mints: number | null;
  }[];
  hourly: { hour: string; all: FeeBlock; liq: FeeBlock }[];
  top_mints: { mint: string; usd: number | null }[];
  defillama: Record<string, unknown>;
  official: Record<string, unknown>;
  caveats: Caveat[];
};

export type AuditReconciliation = {
  contract_version: string;
  generated_at: string | null;
  as_of: string | null;
  sol_usd: number | null;
  defillama: {
    combined: Record<string, number | null>;
    curve: Record<string, number | null>;
    pumpswap: Record<string, number | null>;
    combined_take_rate: number | null;
  };
  bottom_up: {
    window: string | null;
    sum_peak_rs_sol: number | null;
    fee_floor_gross_usd: number | null;
    fee_floor_protocol_usd: number | null;
    dl_curve_fees_same_days_usd: number | null;
    floor_vs_dl_fees_rate: number | null;
  };
  turnover: {
    definition: string | null;
    note: string | null;
    pre_cut: { median_turnover_x: number | null } & Record<string, unknown>;
    post_cut: { median_turnover_x: number | null } & Record<string, unknown>;
  };
  dataset: {
    rows: number | null;
    days: number | null;
    from: string | null;
    to: string | null;
    custom_share: number | null;
    quote_assets: Record<string, number>;
  };
  official: {
    scraped_at: string | null;
    data_as_of: string | null;
    annualized_revenue_usd: number | null;
    daily_revenue_avg_usd: number | null;
    bought_back_usd: number | null;
    burned_pump_usd: number | null;
    daily_buyback_usd: number | null;
    active_wallets_thousands: number | null;
    implied_daily_from_annualized_usd: number | null;
    implied_daily_from_buyback_usd: number | null;
    disclaimer: boolean;
  };
  caveats: Caveat[];
};

export type PulseFeed = {
  contract_version: string;
  generated_at: string | null;
  source_generated_at: string | null;
  kpis: {
    launches: number | null;
    graduations: number | null;
    graduation_rate: number | null;
    instant_bundles: number | null;
    instant_share: number | null;
    organic_rate: number | null;
    pool_death_share: number | null;
    median_collapse_s: number | null;
    organic_median_s: number | null;
    window_from: string | null;
    window_to: string | null;
  };
  live: { graduation?: unknown[]; rug?: unknown[] };
  stories: Record<string, unknown>[];
  tape: Record<string, unknown>[];
};

export type RiskScore = {
  ok: true;
  mint: string;
  creator: string | null;
  p_rug_300s: number;
  p_graduation: number;
  flags: string[];
  top_factors: { feature: string; value: number; contribution: number }[];
  inputs: Record<string, number | string | null>;
  curve: Record<string, unknown>;
  model_version: string;
  scored_at: number;
};

export type ApiError = { error: { code: string; message: string; [k: string]: unknown } };
