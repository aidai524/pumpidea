/** 状态与外壳类小件：加载、错误、空、陈旧度、已知缺口、区块。
 *
 * 设计约束（ui-craft）：用**字重与颜色**表达层级，不用字号；用 1px 边框表达
 * 分隔，不用阴影；每屏最多两三个文字颜色。
 */
import type { ReactNode } from "react";

import { age, staleness } from "../lib/format";
import type { Caveat } from "../api/types";
import { ApiRequestError } from "../api/client";

const TONE: Record<ReturnType<typeof staleness>, string> = {
  fresh: "bg-good",
  stale: "bg-amber",
  old: "bg-bad",
  unknown: "bg-dim",
};

export function Loading({ label = "读取中…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-8 text-sub">
      <span className="inline-block size-3 animate-pulse rounded-full bg-accent" />
      <span className="text-13">{label}</span>
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  const code = error instanceof ApiRequestError ? error.code : "unknown";
  const message =
    error instanceof Error ? error.message : "请求失败，原因未知";
  return (
    <div className="my-4 rounded-card border border-line border-l-2 border-l-bad bg-surface p-4">
      <div className="flex items-baseline justify-between gap-4">
        <div>
          <div className="text-13 font-semibold text-bad">取不到数据</div>
          <div className="mt-1 text-12 text-sub">{message}</div>
          <div className="mt-1 text-11 text-dim">code = {code}</div>
        </div>
        {onRetry && (
          <button
            onClick={onRetry}
            className="shrink-0 rounded-ctl border border-line px-3 py-2 text-12 text-ink hover:border-accent hover:text-accent"
          >
            重试
          </button>
        )}
      </div>
    </div>
  );
}

export function EmptyState({ label }: { label: string }) {
  return (
    <div className="my-4 rounded-card border border-dashed border-line p-6 text-center text-12 text-dim">
      {label}
    </div>
  );
}

/** 数据陈旧度徽标。**这是本应用最重要的一个显示** —— 三条线的产出频率差
 *  几个数量级（pulse 10 秒 / audit 2 分钟 / analysis 1.8 天），不标出来
 *  就会把几天前的分析当实时数据看。 */
export function StaleBadge({
  source,
  ageSeconds,
}: {
  source: string;
  ageSeconds: number | null | undefined;
}) {
  const s = staleness(ageSeconds);
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-line px-3 py-1">
      <span className={`size-2 rounded-full ${TONE[s]}`} />
      <span className="text-11 text-dim">{source}</span>
      <span className="text-11 text-sub">{age(ageSeconds)}</span>
    </span>
  );
}

/** 已知缺口。这些数字的适用范围比"看起来"窄得多，所以必须随页面一起出现。 */
export function CaveatList({
  caveats,
  title = "已知口径缺陷（读结论前先读这里）",
}: {
  caveats: Caveat[];
  title?: string;
}) {
  if (!caveats?.length) return null;
  return (
    <div className="mt-6 rounded-card border border-line border-l-2 border-l-amber bg-surface p-4">
      <div className="text-11 font-semibold tracking-widest text-amber">{title}</div>
      <ul className="mt-3 space-y-2">
        {caveats.map((c) => (
          <li key={c.key} className="text-12 text-sub">
            <span className="font-semibold text-ink">{c.title}</span>
            <span className="text-dim"> —— {c.detail}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Section({
  title,
  hint,
  children,
  right,
}: {
  title: string;
  hint?: string;
  right?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="mt-8">
      <div className="flex items-baseline justify-between gap-4 border-b border-line pb-2">
        <h2 className="text-13 font-semibold tracking-widest text-sub">
          {title}
          {hint && (
            <span className="ml-3 text-11 font-normal tracking-normal text-dim">
              {hint}
            </span>
          )}
        </h2>
        {right}
      </div>
      <div className="mt-3">{children}</div>
    </section>
  );
}
