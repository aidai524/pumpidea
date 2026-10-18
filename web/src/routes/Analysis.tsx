/** 研究（analysis）。这是离线管线的产物：一个 30~32 天的全量观察。
 *
 * 三个查询分别对应后端的三个端点。分开而不是一个大接口，是因为它们的
 * 使用场景不同（概览要快、创建者结构是深读、经济结构是对外沟通）。
 */
import {
  useAnalysisCreators,
  useAnalysisEconomics,
  useAnalysisOverview,
} from "../api/client";
import { BarLineChart } from "../components/BarLineChart";
import { DataTable, MiniBar, type Column } from "../components/DataTable";
import { KpiCard, KpiGrid } from "../components/KpiCard";
import { CaveatList, ErrorState, Loading, Section } from "../components/States";
import { num, pct, pp, secs, usd } from "../lib/format";

type Dist = Record<string, number | null>;

function DistTable({
  title,
  pctiles,
  fmt,
  color,
}: {
  title: string;
  pctiles: Dist;
  fmt: (v: number | null) => string;
  color?: string;
}) {
  const keys = ["p25", "p50", "p75", "p90", "p95", "p99"].filter((k) => k in pctiles);
  const max = Math.max(...keys.map((k) => pctiles[k] ?? 0), 1);
  const cols: Column<{ k: string; v: number | null }>[] = [
    { key: "k", label: "分位", render: (r) => r.k },
    { key: "v", label: "值", align: "right", render: (r) => fmt(r.v) },
    {
      key: "bar", label: "", align: "right",
      render: (r) => <MiniBar value={r.v} max={max} className={color} />,
    },
  ];
  return (
    <div>
      <div className="mb-2 text-11 tracking-widest text-dim">{title}</div>
      <DataTable
        columns={cols}
        rows={keys.map((k) => ({ k, v: pctiles[k] ?? null }))}
        rowKey={(r) => r.k}
      />
    </div>
  );
}

export function Analysis() {
  const ov = useAnalysisOverview();
  const cr = useAnalysisCreators();
  const ec = useAnalysisEconomics();

  if (ov.isLoading) return <Loading label="读取研究数据…" />;
  if (ov.error != null) {
    return <ErrorState error={ov.error} onRetry={() => ov.refetch()} />;
  }
  const d = ov.data!;
  const k = d.kpis;

  return (
    <>
      <Section
        title="研究"
        hint={`${d.window.from} ~ ${d.window.to}（${d.window.days} 天，全量）`}
        right={
          <span className="text-11 text-dim">
            标签校验 召回 {pct(d.label_check.recall)} / 精确 {pct(d.label_check.precision)}
          </span>
        }
      >
        <KpiGrid>
          <KpiCard label="30 天新发代币" value={num(k.launches)} hint={`毕业 ${num(k.graduated)}`} />
          <KpiCard label="名义毕业率" value={pct(k.graduation_rate)} hint="曲线吃满 85 SOL" />
          <KpiCard
            label="有机毕业率" value={pct(k.organic_graduation_rate)} tone="bad"
            hint={`扣掉 ${pct(k.instant_share_of_graduations, 1)} 的机器人捆绑`}
          />
          <KpiCard
            label="中位毕业耗时" value={secs(k.median_seconds_to_graduation)} tone="amber"
            hint={`有机 ${secs(k.median_seconds_to_graduation_organic)}`}
          />
          <KpiCard label="300s 内被判跑路" value={pct(k.rug_rate_within_300s, 1)} hint={num(k.rugged_within_300s)} />
          <KpiCard label="创建者 60s 内卖出" value={pct(k.creator_sold_within_60s_rate, 1)} hint={num(k.creator_sold_within_60s)} />
          <KpiCard
            label="毕业后 30 分钟跌 90%+" value={pct(d.pools.share_lost_90pct_in_30m, 1)}
            hint={`${num(d.pools.full_pools)} 个池，中位 ${secs(d.pools.median_seconds_to_collapse)}`}
          />
          <KpiCard
            label="首周 → 末周发币量"
            value={d.trend.launches_growth == null ? "—" : `+${(d.trend.launches_growth * 100).toFixed(1)}%`}
            tone="amber"
            hint={`同期毕业率 ${pp(d.trend.graduation_rate_pp)}`}
          />
        </KpiGrid>
      </Section>

      <Section title="规模与节奏" hint="供给在涨，真实质量在跌">
        <BarLineChart
          points={d.daily.map((x) => ({
            label: x.day, bar: x.launches, line: x.organic_graduation_rate,
          }))}
          barFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
          lineFormatter={(v) => `${(v * 100).toFixed(1)}%`}
          barLabel="每日发币量"
          lineLabel="有机毕业率"
          caption="30 天：供给与真实有机质量反向"
        />

        <div className="mt-3">
          <DataTable
            columns={[
              { key: "w", label: "周（UTC）", render: (r) => `${r.from.slice(5)} ~ ${r.to.slice(5)}` },
              { key: "l", label: "发币/日", align: "right", render: (r) => num(r.launches_per_day) },
              { key: "g", label: "名义毕业率", align: "right", render: (r) => pct(r.graduation_rate) },
              { key: "o", label: "有机毕业率", align: "right", render: (r) => pct(r.organic_graduation_rate) },
              { key: "i", label: "捆绑占毕业", align: "right", render: (r) => pct(r.instant_share_of_graduations, 1) },
              { key: "r", label: "300s 跑路率", align: "right", render: (r) => pct(r.rug_rate_within_300s, 1) },
            ]}
            rows={d.weekly}
            rowKey={(r) => r.from}
          />
        </div>
      </Section>

      <Section title="三种发币模式" hint="不要混算">
        <DataTable
          columns={[
            { key: "k", label: "模式", render: (r) => r.k },
            { key: "l", label: "发币", align: "right", render: (r) => num(r.b.launches) },
            { key: "s", label: "占发币量", align: "right", render: (r) => pct(r.b.share_of_launches, 1) },
            { key: "g", label: "名义毕业率", align: "right", render: (r) => pct(r.b.graduation_rate, r.b.graduation_rate != null && r.b.graduation_rate < 0.001 ? 3 : 2) },
            { key: "c", label: "链上标 complete", align: "right", render: (r) => pct(r.b.complete_on_chain_share) },
            { key: "r", label: "300s 跑路率", align: "right", render: (r) => pct(r.b.rug_rate_within_300s, 1) },
            { key: "d", label: "创建者 60s 卖出", align: "right", render: (r) => pct(r.b.creator_sold_within_60s_rate, 1) },
          ]}
          rows={Object.entries(d.by_kind).map(([name, b]) => ({ k: name, b }))}
          rowKey={(r) => r.k}
        />
        <p className="mt-2 text-11 text-dim">
          「链上标 complete」与「毕业」是两回事；mayhem 币会被链上标 complete 但储备远低于 85 SOL。
        </p>
      </Section>

      <Section title="谁在发币" hint="工厂，不是社区">
        {cr.isLoading && <Loading />}
        {cr.error != null && <ErrorState error={cr.error} onRetry={() => cr.refetch()} />}
        {cr.data && (
          <>
            <div className="grid grid-cols-[repeat(auto-fit,minmax(320px,1fr))] gap-4">
              <div>
                <div className="mb-2 text-11 tracking-widest text-dim">创建者集中度</div>
                <DataTable
                  columns={[
                    { key: "k", label: "指标", render: (r) => r.k },
                    { key: "v", label: "值", align: "right", render: (r) => r.v },
                  ]}
                  rows={[
                    { k: "唯一创建者", v: num(cr.data.concentration.creators) },
                    { k: "人均发币", v: num(cr.data.concentration.per_creator_mean, 2) },
                    { k: "单个钱包最多", v: num(cr.data.concentration.top1) },
                    { k: "top 1000 份额", v: pct(cr.data.concentration.top1000_share) },
                    {
                      k: "占一半发币量所需",
                      v: `${num(cr.data.concentration.creators_for_half)} 人（${pct(cr.data.concentration.creators_for_half_share, 1)}）`,
                    },
                  ]}
                  rowKey={(r) => r.k}
                />
              </div>
              <div>
                <div className="mb-2 text-11 tracking-widest text-dim">
                  按创建者历史发币数分层
                </div>
                <DataTable
                  columns={[
                    { key: "b", label: "此前发过", render: (r) => r.bucket },
                    { key: "n", label: "币数", align: "right", render: (r) => num(r.n) },
                    { key: "g", label: "毕业率", align: "right", render: (r) => pct(r.graduation_rate) },
                    { key: "r", label: "跑路率", align: "right", render: (r) => pct(r.rug_rate) },
                    { key: "p", label: "历史均跑路", align: "right", render: (r) => num(r.mean_prior_rugs, 2) },
                  ]}
                  rows={cr.data.veteran_by_prior_launches}
                  rowKey={(r) => r.bucket}
                />
                <p className="mt-2 text-11 text-dim">
                  反直觉：职业发币者的成功率更低。新钱包的毕业率是「发过 20+ 次」那批的
                  <span className="text-ink"> 7 倍以上</span>，而那批地址平均已跑路 0.69 次。
                </p>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-[repeat(auto-fit,minmax(300px,1fr))] gap-4">
              <DistTable title="发币首分钟的捆绑钱包数（个）" pctiles={cr.data.bundling.percentiles} fmt={(v) => num(v)} color="bg-accent" />
              <DistTable title="创建者首分钟持仓占比" pctiles={cr.data.dev_share_distribution.percentiles} fmt={(v) => pct(v)} color="bg-violet" />
              <DistTable title="曲线储备峰值（SOL，上限 85）" pctiles={cr.data.peak_rs.percentiles} fmt={(v) => num(v, 2)} color="bg-amber" />
            </div>

            <div className="mt-4">
              <div className="mb-2 text-11 tracking-widest text-dim">
                被发最多的 ticker（{num(cr.data.tickers.unique)} 个不同 ticker /
                {" "}{num(cr.data.tickers.launches)} 个币，平均每个出现 {num(cr.data.tickers.mean_per_ticker, 2)} 次）
              </div>
              <DataTable
                columns={[
                  { key: "t", label: "ticker", render: (r) => r.ticker },
                  { key: "n", label: "币数", align: "right", render: (r) => num(r.n) },
                  { key: "g", label: "毕业", align: "right", render: (r) => num(r.graduated) },
                  { key: "r", label: "跑路率", align: "right", render: (r) => pct(r.rug_rate, 1) },
                ]}
                rows={cr.data.tickers.top.slice(0, 8)}
                rowKey={(r) => r.ticker}
              />
            </div>
          </>
        )}
      </Section>

      <Section title="钱去哪了" hint="量与收入的倒挂">
        {ec.isLoading && <Loading />}
        {ec.error != null && <ErrorState error={ec.error} onRetry={() => ec.refetch()} />}
        {ec.data && (
          <>
            <DataTable
              columns={[
                { key: "k", label: "30 天", render: (r) => r.k },
                { key: "v", label: "交易量", align: "right", render: (r) => usd(r.volume_usd) },
                { key: "f", label: "用户付费", align: "right", render: (r) => usd(r.fees_usd) },
                { key: "r", label: "平台净收入", align: "right", render: (r) => usd(r.revenue_usd) },
                { key: "t", label: "抽成率", align: "right", render: (r) => pct(r.revenue_rate, 3) },
              ]}
              rows={[
                { k: "发币曲线", ...ec.data.structure.launchpad },
                { k: "PumpSwap", ...ec.data.structure.pumpswap },
                { k: "合计", ...ec.data.structure.combined },
              ]}
              rowKey={(r) => r.k}
            />

            <div className="mt-3 rounded-card border border-line bg-surface p-4">
              <div className="text-11 tracking-widest text-dim">一手结构与收入结构的错配</div>
              <div className="mt-2 space-y-1">
                <div className="flex items-center gap-3">
                  <span className="w-40 text-12 text-ink">PumpSwap 交易量占比</span>
                  <span className="h-2.5 flex-1 overflow-hidden rounded-full bg-bg">
                    <span className="block h-full bg-bar" style={{ width: `${(ec.data.mix.pumpswap_volume_share ?? 0) * 100}%` }} />
                  </span>
                  <span className="w-20 text-right text-12 tabular-nums text-sub">{pct(ec.data.mix.pumpswap_volume_share, 1)}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="w-40 text-12 text-ink">PumpSwap 收入占比</span>
                  <span className="h-2.5 flex-1 overflow-hidden rounded-full bg-bg">
                    <span className="block h-full bg-amber" style={{ width: `${(ec.data.mix.pumpswap_revenue_share ?? 0) * 100}%` }} />
                  </span>
                  <span className="w-20 text-right text-12 tabular-nums text-sub">{pct(ec.data.mix.pumpswap_revenue_share, 1)}</span>
                </div>
              </div>
              <p className="mt-3 text-11 text-dim">
                PumpSwap 的协议分成只有 0.05%（曲线是 0.95%）——
                <span className="text-ink"> 76% 的量只换来 28% 的收入</span>。
              </p>
            </div>

            <div className="mt-3 rounded-card border border-line bg-surface p-4">
              <div className="text-11 tracking-widest text-dim">
                独立校验：不依赖任何第三方，只用公开链上数据把量级钉住
              </div>
              <DataTable
                columns={[
                  { key: "k", label: "", render: (r) => r.k },
                  { key: "v", label: "", align: "right", render: (r) => r.v },
                ]}
                rows={[
                  { k: `Σ peak_rs（${ec.data.fee_floor.window_days ?? "?"} 天）`, v: `${num(ec.data.fee_floor.sum_peak_rs_sol)} SOL` },
                  { k: "按 SOL 价换算", v: `${usd(ec.data.fee_floor.volume_floor_usd)}（@ $${ec.data.fee_floor.sol_usd}）` },
                  { k: "曲线毛手续费下界", v: usd(ec.data.fee_floor.fee_floor_gross_usd) },
                  { k: "其中协议分成下界", v: usd(ec.data.fee_floor.fee_floor_protocol_usd) },
                ]}
                rowKey={(r) => r.k}
              />
              <p className="mt-2 text-11 text-dim">{ec.data.fee_floor.note}</p>
            </div>
          </>
        )}
      </Section>

      <CaveatList caveats={d.caveats} />
    </>
  );
}
