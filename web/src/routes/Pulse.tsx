/** 注意力（pulse）：实时候选、故事墙、毕业流水。
 *
 * 这一页的数据是四条线里最新的（30 秒重建一次），也是唯一"每秒都在变"的。
 * 注意 pulse 的数值口径与其它页不同：`p_rug` / `p_grad` / `top5_share` 上游
 * 就是 0~100 的百分数（pulse 自己的服务格式），所以这里直接显示，不再换算。
 */
import { usePulseFeed } from "../api/client";
import { DataTable } from "../components/DataTable";
import { KpiCard, KpiGrid } from "../components/KpiCard";
import { EmptyState, ErrorState, Loading, Section } from "../components/States";
import { num, pct, secs } from "../lib/format";

type LiveRow = {
  mint: string;
  symbol: string;
  age: string;
  reserve_sol: number;
  n_buys: number;
  unique_buyers_60s: number;
  top5_share: number;
  p_rug: number;
  p_grad: number;
  flags: string[];
};

type Story = {
  id: string;
  type: string;
  kicker: string;
  title: string;
  value: string;
  label: string;
  sub: string;
  stats: [string, string][];
  accent?: string;
  mint: string;
};

type TapeRow = {
  mint: string;
  symbol: string;
  label: string;
  seconds: string;
  when: string;
  copies: number;
  peak_sol: number | null;
  link?: string;
};

function LiveTable({ rows, tone }: { rows: LiveRow[]; tone: "good" | "bad" }) {
  return (
    <DataTable
      columns={[
        { key: "s", label: "代币", render: (r) => r.symbol || r.mint.slice(0, 8) },
        { key: "a", label: "上线", align: "right", render: (r) => r.age },
        { key: "r", label: "曲线储备", align: "right", render: (r) => `${num(r.reserve_sol, 1)} SOL` },
        { key: "b", label: "买单", align: "right", render: (r) => num(r.n_buys) },
        { key: "u", label: "独立买家/60s", align: "right", render: (r) => num(r.unique_buyers_60s) },
        { key: "t", label: "top5 占比", align: "right", render: (r) => `${num(r.top5_share, 1)}%` },
        {
          key: "p", label: tone === "bad" ? "p_rug" : "p_grad", align: "right",
          render: (r) => (
            <span className={tone === "bad" ? "text-bad" : "text-good"}>
              {num(tone === "bad" ? r.p_rug : r.p_grad, 1)}%
            </span>
          ),
        },
        {
          key: "f", label: "标记", align: "right",
          render: (r) => (r.flags?.length ? r.flags.join(", ") : "—"),
        },
      ]}
      rows={rows}
      rowKey={(r) => r.mint}
    />
  );
}

export function Pulse() {
  const q = usePulseFeed();

  if (q.isLoading) return <Loading label="读取注意力数据…" />;
  if (q.error != null) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;

  const d = q.data!;
  const k = d.kpis;
  const live = d.live as { graduation?: LiveRow[]; rug?: LiveRow[] };
  const stories = d.stories as unknown as Story[];
  const tape = d.tape as unknown as TapeRow[];

  return (
    <>
      <Section
        title="注意力"
        hint={`窗口 ${k.window_from?.slice(11, 16) ?? "—"} ~ ${k.window_to?.slice(11, 16) ?? "—"} UTC`}
        right={<span className="text-11 text-dim">每 30 秒刷新</span>}
      >
        <KpiGrid>
          <KpiCard label="24 小时发币" value={num(k.launches)} />
          <KpiCard label="真毕业" value={num(k.graduations)} hint={pct(k.graduation_rate)} />
          <KpiCard
            label="瞬时捆绑占毕业" value={pct(k.instant_share, 1)}
            hint={`${num(k.instant_bundles)} 个`} tone="amber"
          />
          <KpiCard label="有机毕业率" value={pct(k.organic_rate)} tone="bad" />
          <KpiCard
            label="30 分钟内跌 90%+" value={pct(k.pool_death_share, 1)}
            hint="毕业后的池子"
          />
          <KpiCard label="中位崩盘耗时" value={secs(k.median_collapse_s)} hint={`有机毕业中位 ${secs(k.organic_median_s)}`} />
        </KpiGrid>
      </Section>

      <Section title="实时候选" hint="Graduation 观察 / Rug 预警">
        <div className="grid grid-cols-[repeat(auto-fit,minmax(420px,1fr))] gap-4">
          <div>
            <div className="mb-2 text-11 tracking-widest text-good">正在毕业</div>
            {live.graduation?.length ? (
              <LiveTable rows={live.graduation} tone="good" />
            ) : (
              <EmptyState label="这一轮没有候选" />
            )}
          </div>
          <div>
            <div className="mb-2 text-11 tracking-widest text-bad">高风险</div>
            {live.rug?.length ? (
              <LiveTable rows={live.rug} tone="bad" />
            ) : (
              <EmptyState label="这一轮没有候选" />
            )}
          </div>
        </div>
      </Section>

      <Section title="故事墙" hint="每一格都是一个可讲的事件">
        {stories.length ? (
          <div className="grid grid-cols-[repeat(auto-fit,minmax(300px,1fr))] gap-3">
            {stories.map((s) => (
              <article
                key={s.id}
                className="rounded-card border border-line bg-surface p-4"
                style={s.accent ? { borderLeft: `2px solid ${s.accent}` } : undefined}
              >
                <div className="text-11 tracking-widest text-dim">{s.kicker}</div>
                <div className="mt-1 flex items-baseline justify-between gap-2">
                  <span className="text-13 font-semibold text-ink">{s.title}</span>
                  <span className="text-11 text-sub">{s.value}</span>
                </div>
                <div className="mt-1 text-11 text-dim">{s.label}</div>
                <p className="mt-2 text-12 text-sub">{s.sub}</p>
                <dl className="mt-3 space-y-1">
                  {(s.stats ?? []).slice(0, 3).map(([mk, mv]) => (
                    <div key={mk} className="flex justify-between text-11">
                      <dt className="text-dim">{mk}</dt>
                      <dd className="tabular-nums text-sub">{mv}</dd>
                    </div>
                  ))}
                </dl>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState label="这一轮没有故事" />
        )}
      </Section>

      <Section title="毕业流水" hint="最近 60 条">
        <DataTable
          columns={[
            { key: "s", label: "代币", render: (r) => r.symbol },
            { key: "w", label: "时间", align: "right", render: (r) => r.when },
            { key: "l", label: "类型", align: "right", render: (r) => r.label },
            { key: "d", label: "耗时", align: "right", render: (r) => r.seconds },
            { key: "c", label: "同名/周", align: "right", render: (r) => num(r.copies) },
            { key: "p", label: "峰值 SOL", align: "right", render: (r) => num(r.peak_sol, 2) },
          ]}
          rows={tape}
          rowKey={(r) => r.mint}
        />
        <p className="mt-2 text-11 text-dim">数据生成于 {d.generated_at ?? "—"}（上游每 30 秒重建）。</p>
      </Section>
    </>
  );
}
