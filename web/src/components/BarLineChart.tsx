/** 双轴柱线图 —— 从 `analysis/make_dashboard.py` 里手写的内联 SVG 移植过来。
 *
 * 为什么是双轴而不是归一化：发币量是万级、毕业率是零点几个百分点，量纲差三个
 * 数量级。共用一根轴必然撒谎（要么柱全贴地，要么线全贴顶），所以左轴给柱、
 * 右轴给线，并在图例里写明。
 *
 * 为什么不引图表库：现有两张图已经够用，echarts/recharts 会带来第二套视觉
 * 语言和一个重依赖（见 spec §4.1）。
 */
type Point = { label: string; bar: number | null; line: number | null };

export function BarLineChart({
  points,
  barFormatter,
  lineFormatter,
  barLabel,
  lineLabel,
  caption,
}: {
  points: Point[];
  barFormatter: (v: number) => string;
  lineFormatter: (v: number) => string;
  barLabel: string;
  lineLabel: string;
  caption?: string;
}) {
  const W = 1000;
  const H = 340;
  const L = 74;
  const R = 74;
  const T = 46;
  const B = 46;

  const bars = points.map((p) => p.bar ?? 0);
  const lines = points.map((p) => p.line ?? 0);
  const barMax = Math.max(...bars, 1) * 1.12;
  const lineMax = Math.max(...lines, 0.0001) * 1.3;
  const plotH = H - T - B;
  const band = (W - L - R) / Math.max(points.length, 1);

  const yBar = (v: number) => H - B - (v / barMax) * plotH;
  const yLine = (v: number) => H - B - (v / lineMax) * plotH;
  const xMid = (i: number) => L + i * band + band / 2;

  const step = Math.max(1, Math.ceil(points.length / 12));
  const linePts = points
    .map((p, i) => `${xMid(i).toFixed(1)},${yLine(p.line ?? 0).toFixed(1)}`)
    .join(" ");

  return (
    <div className="rounded-card border border-line bg-surface p-3">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img">
        {/* 网格 + 左右两轴的刻度 */}
        {[0, 0.5, 1].map((f) => {
          const y = yBar(barMax * f);
          return (
            <g key={f}>
              <line
                x1={L} y1={y} x2={W - R} y2={y}
                className="stroke-line" strokeDasharray="3 3"
              />
              <text
                x={L - 10} y={y + 4} textAnchor="end"
                className="fill-dim text-[11px]"
              >
                {barFormatter(barMax * f)}
              </text>
              <text x={W - R + 10} y={y + 4} className="fill-accent text-[11px]">
                {lineFormatter(lineMax * f)}
              </text>
            </g>
          );
        })}

        {/* 柱：左轴 */}
        {points.map((p, i) => {
          const v = p.bar ?? 0;
          const h = (v / barMax) * plotH;
          return (
            <rect
              key={`b${i}`}
              x={L + i * band + band * 0.22}
              y={H - B - h}
              width={band * 0.56}
              height={Math.max(h, 0)}
              rx={1.5}
              className="fill-bar"
              opacity={0.9}
            />
          );
        })}

        {/* 线：右轴 */}
        <polyline
          points={linePts}
          fill="none"
          className="stroke-accent"
          strokeWidth={2.4}
          strokeLinejoin="round"
        />

        {/* 横轴标签 */}
        {points.map((p, i) =>
          i % step === 0 ? (
            <text
              key={`x${i}`}
              x={xMid(i)} y={H - B + 20}
              textAnchor="middle"
              className="fill-dim text-[11px]"
            >
              {p.label.slice(5)}
            </text>
          ) : null,
        )}

        {/* 图例 */}
        {caption && (
          <text x={L} y={20} className="fill-dim text-[11px]">{caption}</text>
        )}
        <rect x={L} y={28} width={10} height={10} rx={2} className="fill-bar" />
        <text x={L + 16} y={37} className="fill-dim text-[11px]">{barLabel}（左轴）</text>
        <line
          x1={L + 210} y1={32} x2={L + 232} y2={32}
          className="stroke-accent" strokeWidth={2.4}
        />
        <text x={L + 240} y={37} className="fill-dim text-[11px]">{lineLabel}（右轴）</text>
      </svg>
    </div>
  );
}

/** 占比条：用于"量在 PumpSwap、收入在曲线"这类倒挂对比。 */
export function ShareBar({
  value,
  label,
  color = "bg-bar",
}: {
  value: number | null;
  label: string;
  color?: string;
}) {
  const w = value == null ? 0 : Math.min(100, Math.max(0, value * 100));
  return (
    <div className="flex items-center gap-3 py-1">
      <span className="w-40 shrink-0 text-12 text-ink">{label}</span>
      <span className="h-2.5 flex-1 overflow-hidden rounded-full bg-bg">
        <span className={`block h-full ${color}`} style={{ width: `${w}%` }} />
      </span>
      <span className="w-20 shrink-0 text-right text-12 tabular-nums text-sub">
        {value == null ? "—" : `${w.toFixed(1)}%`}
      </span>
    </div>
  );
}
