/** 通用表格。
 *
 * 现有静态页里有 12 张表，形状都是"分位/分组 → 若干指标"。所以抽一个组件
 * 而不是每处手写 <table>，保证列宽、对齐、分隔线一致。
 * 数字列一律右对齐 + 等宽（tabular-nums），否则扫读时会错位。
 */
import type { ReactNode } from "react";

export type Column<T> = {
  key: string;
  label: ReactNode;
  align?: "left" | "right";
  render: (row: T) => ReactNode;
  width?: string;
};

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  empty = "没有数据",
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T, i: number) => string;
  empty?: string;
}) {
  if (!rows.length) {
    return (
      <div className="rounded-card border border-dashed border-line p-4 text-center text-12 text-dim">
        {empty}
      </div>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                style={c.width ? { width: c.width } : undefined}
                className={`border-b border-line px-3 py-2 text-11 font-normal tracking-widest text-dim ${
                  c.align === "right" ? "text-right" : "text-left"
                }`}
              >
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={rowKey(row, i)}>
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={`border-b border-line px-3 py-2 text-13 tabular-nums ${
                    c.align === "right" ? "text-right text-sub" : "text-left text-ink"
                  }`}
                >
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** 表格里嵌的迷你条：用来给"分位分布"这类数字一个视觉权重。 */
export function MiniBar({
  value,
  max,
  className = "bg-violet",
}: {
  value: number | null;
  max: number;
  className?: string;
}) {
  const w = value == null || !max ? 0 : Math.min(100, (value / max) * 100);
  return (
    <span className="inline-block h-1.5 w-24 overflow-hidden rounded-full bg-bg align-middle">
      <span className={`block h-full ${className}`} style={{ width: `${w}%` }} />
    </span>
  );
}
