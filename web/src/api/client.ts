/** 对 `/api/v1` 的唯一访问处。
 *
 * 路径用 `import.meta.env.BASE_URL` 拼接，所以同一份代码在两个环境都对：
 *   dev  base="/"           → /api/v1/...        （vite proxy 转发到 BFF）
 *   prod base="/pumpfun/"   → /pumpfun/api/v1/... （Caddy 剥掉前缀后到 BFF）
 *
 * 轮询间隔按**上游产出频率**给，不是按"看起来快不快"给：
 *   pulse     30 秒重建 → 30 秒轮询
 *   audit     每小时重建 → 5 分钟轮询（多轮一次不亏，能及时看到重建）
 *   analysis  离线静态   → 10 分钟（它基本不变）
 *   health    60 秒
 */
import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import type {
  AnalysisCreators,
  AnalysisEconomics,
  AnalysisOverview,
  ApiError,
  AuditReconciliation,
  AuditSummary,
  Health,
  PulseFeed,
  RiskScore,
} from "./types";

const BASE = `${import.meta.env.BASE_URL}api/v1`;

export class ApiRequestError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "ApiRequestError";
    this.code = code;
    this.status = status;
  }
}

async function get<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { Accept: "application/json" },
    ...init,
  });
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // 非 JSON（例如代理返回的错误页）—— 下面的分支会给一个可读消息
  }
  if (!res.ok) {
    const err = (body as ApiError | null)?.error;
    throw new ApiRequestError(
      err?.code ?? `http_${res.status}`,
      err?.message ?? res.statusText ?? "请求失败",
      res.status,
    );
  }
  return body as T;
}

export const api = {
  health: () => get<Health>("/health"),
  analysisOverview: () => get<AnalysisOverview>("/analysis/overview"),
  analysisCreators: () => get<AnalysisCreators>("/analysis/creators"),
  analysisEconomics: () => get<AnalysisEconomics>("/analysis/economics"),
  auditSummary: () => get<AuditSummary>("/audit/summary"),
  auditReconciliation: () => get<AuditReconciliation>("/audit/reconciliation"),
  pulseFeed: () => get<PulseFeed>("/pulse/feed"),
  riskScore: (mint: string) => get<RiskScore>(`/risk/score/${encodeURIComponent(mint)}`),
};

export const qk = {
  health: ["health"] as const,
  analysisOverview: ["analysis", "overview"] as const,
  analysisCreators: ["analysis", "creators"] as const,
  analysisEconomics: ["analysis", "economics"] as const,
  auditSummary: ["audit", "summary"] as const,
  auditReconciliation: ["audit", "reconciliation"] as const,
  pulseFeed: ["pulse", "feed"] as const,
  riskScore: (mint: string) => ["risk", "score", mint] as const,
};

const MIN = 60_000;

export function useHealth(): UseQueryResult<Health> {
  return useQuery({ queryKey: qk.health, queryFn: api.health, refetchInterval: MIN });
}

export function useAnalysisOverview(): UseQueryResult<AnalysisOverview> {
  return useQuery({
    queryKey: qk.analysisOverview,
    queryFn: api.analysisOverview,
    refetchInterval: 10 * MIN,
  });
}

export function useAnalysisCreators(): UseQueryResult<AnalysisCreators> {
  return useQuery({
    queryKey: qk.analysisCreators,
    queryFn: api.analysisCreators,
    refetchInterval: 10 * MIN,
  });
}

export function useAnalysisEconomics(): UseQueryResult<AnalysisEconomics> {
  return useQuery({
    queryKey: qk.analysisEconomics,
    queryFn: api.analysisEconomics,
    refetchInterval: 10 * MIN,
  });
}

export function useAuditSummary(): UseQueryResult<AuditSummary> {
  return useQuery({
    queryKey: qk.auditSummary,
    queryFn: api.auditSummary,
    refetchInterval: 5 * MIN,
  });
}

export function useAuditReconciliation(): UseQueryResult<AuditReconciliation> {
  return useQuery({
    queryKey: qk.auditReconciliation,
    queryFn: api.auditReconciliation,
    refetchInterval: 10 * MIN,
  });
}

export function usePulseFeed(): UseQueryResult<PulseFeed> {
  return useQuery({
    queryKey: qk.pulseFeed,
    queryFn: api.pulseFeed,
    refetchInterval: 30_000,
  });
}

/** 打分**不轮询** —— 它是用户显式触发的一次操作，且实测要 18 秒。 */
export function useRiskScore(mint: string | null) {
  return useQuery({
    queryKey: qk.riskScore(mint ?? ""),
    queryFn: () => api.riskScore(mint as string),
    enabled: Boolean(mint),
    retry: false,
    staleTime: 5 * MIN,
    gcTime: 30 * MIN,
  });
}
