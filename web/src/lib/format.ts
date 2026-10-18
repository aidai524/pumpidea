/** 展示层的格式化。集中在一处，避免每个组件各写一套。
 *
 * 注意契约已经把量纲统一了（比率 0~1、金额绝对 USD），所以这里**只负责显示**，
 * 不做任何业务换算。
 */

export const pct = (x: number | null | undefined, digits = 2): string =>
  x == null ? "—" : `${(x * 100).toFixed(digits)}%`;

/** 百分点（契约里的 `*_pp` 字段已经是百分点，不要再乘 100） */
export const pp = (x: number | null | undefined, digits = 2): string =>
  x == null ? "—" : `${x > 0 ? "+" : ""}${x.toFixed(digits)}pp`;

export const num = (x: number | null | undefined, digits = 0): string =>
  x == null ? "—" : x.toLocaleString("en-US", {
    minimumFractionDigits: digits, maximumFractionDigits: digits,
  });

export const usd = (x: number | null | undefined): string => {
  if (x == null) return "—";
  const a = Math.abs(x);
  if (a >= 1e9) return `$${(x / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `$${(x / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `$${(x / 1e3).toFixed(1)}K`;
  return `$${x.toFixed(2)}`;
};

/** 秒 → 人话。中位毕业耗时是 0.367 秒，而崩盘耗时是 475 秒，量级差太大。 */
export const secs = (x: number | null | undefined): string => {
  if (x == null) return "—";
  if (x < 1) return `${x.toFixed(2)}s`;
  if (x < 120) return `${x.toFixed(0)}s`;
  if (x < 7200) return `${(x / 60).toFixed(1)} 分钟`;
  if (x < 172800) return `${(x / 3600).toFixed(1)} 小时`;
  return `${(x / 86400).toFixed(1)} 天`;
};

/** 数据陈旧度。这是本应用最重要的一个显示 —— 三条线频率差几个数量级，
 *  不标出来就会把 1.8 天前的分析当实时数据看。 */
export const age = (seconds: number | null | undefined): string => {
  if (seconds == null) return "未知";
  if (seconds < 60) return `${seconds.toFixed(0)} 秒前`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(0)} 分钟前`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)} 小时前`;
  return `${(seconds / 86400).toFixed(1)} 天前`;
};

/** 陈旧度分级：<=10 分钟算新，<=24 小时算旧，更久算很久。 */
export const staleness = (
  seconds: number | null | undefined,
): "fresh" | "stale" | "old" | "unknown" => {
  if (seconds == null) return "unknown";
  if (seconds <= 600) return "fresh";
  if (seconds <= 86400) return "stale";
  return "old";
};

export const day = (iso: string | null | undefined): string =>
  iso ? iso.slice(5, 10) : "—";
