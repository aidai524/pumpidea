/** 收入对账（audit）。两件事：链上一手重建的六条费用线，和三方口径对账。
 *
 * 这一页最容易误读的地方是**双口径**：`all`（含长尾报价资产）会被单一低流动性
 * 资产放大两个数量级 —— 实测某天 holder_rewards 全价口径 23.5 亿 USD。
 * 所以两个口径必须视觉上分开，并且把"`all` 不能当收入"写在页面上。
 */
import { useAuditReconciliation, useAuditSummary } from "../api/client";
import type { FeeBlock } from "../api/types";
import { DataTable } from "../components/DataTable";
import { KpiCard, KpiGrid } from "../components/KpiCard";
import { CaveatList, ErrorState, Loading, Section } from "../components/States";
import { age, num, pct, usd } from "../lib/format";

const LINE_LABELS: Record<string, string> = {
  protocol_fee: "协议费",
  creator_fee: "创作者",
  buyback_fee: "回购",
  lp_fee: "LP",
  cashback: "返现",
  holder_rewards: "持币奖励",
};

export function Audit() {
  const sum = useAuditSummary();
  const rec = useAuditReconciliation();

  if (sum.isLoading) return <Loading label="读取链上报表…" />;
  if (sum.error != null) {
    return <ErrorState error={sum.error} onRetry={() => sum.refetch()} />;
  }
  const d = sum.data!;
  const latest = d.daily.at(-1);

  return (
    <>
      <Section
        title="收入对账"
        hint={`数据 ${d.generated_at ?? "—"} · SOL $${d.sol_usd ?? "—"}`}
        right={
          <span className="text-11 text-dim">
            事件 {num(d.health.events)} · 最后一条 {age(d.health.last_age_s)}
          </span>
        }
      >
        <KpiGrid>
          <KpiCard
            label="最新一天 · 六线合计（流动性达标）"
            value={usd(latest?.liq.total)}
            hint={latest?.day ?? "—"}
            tone="good"
          />
          <KpiCard
            label="同一天 · 全价口径"
            value={usd(latest?.all.total)}
            hint="含长尾报价资产，不可当收入"
            tone="amber"
          />
          <KpiCard
            label="已定价 mint"
            value={num(d.pricing_quality.priced)}
            hint={`共 ${num(d.pricing_quality.mints_total)} 个，取 top ${num(d.pricing_quality.mints_chosen)}`}
          />
          <KpiCard
            label="流动性门槛"
            value={usd(d.pricing_quality.min_liquidity_usd)}
            hint={`流动性达标 ${num(d.pricing_quality.major_quote)}，高离散 ${num(d.pricing_quality.high_dispersion)}`}
          />
        </KpiGrid>

        <div className="mt-4 rounded-card border border-line border-l-2 border-l-amber bg-surface p-4 text-12 text-sub">
          <span className="font-semibold text-amber">不要把「全价口径」当收入。</span>
          {" "}它把每一个可定价的报价资产都算进去，而长尾资产的定价来自单个交易对，
          会被一条几乎没有流动性的池子放大两个数量级。
          <span className="text-ink"> 判断收入看「流动性达标」那一列。</span>
        </div>
      </Section>

      <Section title="六条费用线" hint={latest ? latest.day : ""}>
        <DataTable
          columns={[
            { key: "l", label: "费用线", render: (r) => LINE_LABELS[r.line] ?? r.line },
            { key: "a", label: "全价口径", align: "right", render: (r) => usd(r.all) },
            { key: "q", label: "流动性达标口径", align: "right", render: (r) => usd(r.liq) },
            {
              key: "s", label: "达标占比", align: "right",
              render: (r) => (r.all ? pct(Math.min(1, (r.liq ?? 0) / r.all), 1) : "—"),
            },
          ]}
          rows={d.lines.map((line) => {
            const a = (latest?.all as unknown as FeeBlock)?.[line as keyof FeeBlock] ?? null;
            const q = (latest?.liq as unknown as FeeBlock)?.[line as keyof FeeBlock] ?? null;
            return { line, all: a as number | null, liq: q as number | null };
          })}
          rowKey={(r) => r.line}
        />
      </Section>

      <Section title="逐日" hint="双口径并排；看最后一列判断数据可信度">
        <DataTable
          columns={[
            { key: "d", label: "日期", render: (r) => r.day },
            { key: "a", label: "全价合计", align: "right", render: (r) => usd(r.all.total) },
            { key: "q", label: "达标合计", align: "right", render: (r) => usd(r.liq.total) },
            { key: "n", label: "事件数", align: "right", render: (r) => num(r.n_events) },
            { key: "u", label: "未定价 mint", align: "right", render: (r) => num(r.unpriced_mints) },
            { key: "i", label: "低流动性 mint", align: "right", render: (r) => num(r.illiquid_mints) },
          ]}
          rows={[...d.daily].reverse()}
          rowKey={(r) => r.day}
        />
      </Section>

      <Section title="三方口径对账" hint="官方 / DefiLlama / 自建下界">
        {rec.isLoading && <Loading />}
        {rec.error != null && <ErrorState error={rec.error} onRetry={() => rec.refetch()} />}
        {rec.data && (
          <>
            <DataTable
              columns={[
                { key: "k", label: "口径", render: (r) => r.k },
                { key: "v", label: "值", align: "right", render: (r) => r.v },
              ]}
              rows={[
                {
                  k: "官方看板 · 年化收入",
                  v: `${usd(rec.data.official.annualized_revenue_usd)}（截至 ${rec.data.official.data_as_of ?? "—"}）`,
                },
                { k: "官方 · 日均收入", v: usd(rec.data.official.daily_revenue_avg_usd) },
                { k: "官方 · 已回购", v: usd(rec.data.official.bought_back_usd) },
                { k: "DefiLlama · 30 天费用", v: usd(rec.data.defillama.combined.fees_usd as number | null) },
                { k: "DefiLlama · 30 天收入", v: usd(rec.data.defillama.combined.revenue_usd as number | null) },
                { k: "自建下界 · 协议分成", v: usd(rec.data.bottom_up.fee_floor_protocol_usd) },
                { k: "自建下界 ÷ DefiLlama 曲线费用", v: pct(rec.data.bottom_up.floor_vs_dl_fees_rate, 1) },
                {
                  k: "周转倍数（09-09 后）",
                  v: `${num(rec.data.turnover.post_cut.median_turnover_x, 2)}×`,
                },
              ]}
              rowKey={(r) => r.k}
            />
            <p className="mt-2 text-11 text-dim">
              {rec.data.turnover.note}
              {" "}下界只含曲线买入净流入，不含卖出侧、不含同一笔钱的周转、不含毕业后的 PumpSwap ——
              所以它比实际低一个数量级是**预期的**，用途是校验量级而不是估计值。
            </p>
          </>
        )}
      </Section>

      <CaveatList caveats={d.caveats} title="与 DefiLlama 对账时的已知口径差异" />
    </>
  );
}
