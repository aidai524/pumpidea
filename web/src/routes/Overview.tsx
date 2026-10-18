/** 总览：四条线的入口 + 各一条真实数字。
 *
 * 每个数字来自各自的查询，**互不阻塞** —— 一条线挂了不该让整页白屏
 * （这是 BFF 返回 503 而不是崩掉的意义）。
 */
import { Link } from "react-router-dom";

import { useAnalysisOverview, useAuditSummary, useHealth, usePulseFeed } from "../api/client";
import { age, num, pct, secs, usd } from "../lib/format";
import { ErrorState, Loading, Section } from "../components/States";

function Card({
  to,
  title,
  line,
  children,
}: {
  to: string;
  title: string;
  line: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      to={to}
      className="block rounded-card border border-line bg-surface p-4 transition-colors hover:border-accent"
    >
      <div className="flex items-baseline justify-between">
        <div className="text-13 font-semibold text-ink">{title}</div>
        <div className="text-11 text-dim">{line}</div>
      </div>
      <div className="mt-3">{children}</div>
    </Link>
  );
}

function Stat({ k, v, h }: { k: string; v: string; h?: string }) {
  return (
    <div className="mt-2 flex items-baseline justify-between gap-3">
      <span className="text-11 text-dim">{k}</span>
      <span className="text-13 font-semibold tabular-nums text-ink">{v}</span>
      {h && <span className="w-24 text-right text-11 text-dim">{h}</span>}
    </div>
  );
}

export function Overview() {
  const health = useHealth();
  const analysis = useAnalysisOverview();
  const audit = useAuditSummary();
  const pulse = usePulseFeed();

  const a = analysis.data;
  const p = pulse.data;
  const latestAuditDay = audit.data?.daily.at(-1);

  return (
    <>
      <Section
        title="总览"
        hint="四条线各自产出，经 /api/v1 归一化"
        right={
          health.data && (
            <span className="text-11 text-dim">
              {health.data.ok ? "四路上游均可达" : "部分上游不可达"}
            </span>
          )
        }
      >
        <div className="grid grid-cols-[repeat(auto-fit,minmax(300px,1fr))] gap-3">
          <Card to="/analysis" title="研究" line="离线 · 静态">
            {analysis.isLoading && <Loading />}
            {analysis.error != null && (
              <ErrorState error={analysis.error} onRetry={() => analysis.refetch()} />
            )}
            {a && (
              <>
                <Stat k="30 天发币" v={num(a.kpis.launches)} h={`${a.window.days} 天窗口`} />
                <Stat k="名义毕业率" v={pct(a.kpis.graduation_rate)} />
                <Stat k="有机毕业率" v={pct(a.kpis.organic_graduation_rate)} h="扣掉捆绑" />
                <Stat k="数据年龄" v={age(health.data?.sources.find((s) => s.source === "analysis")?.age_seconds)} h="离线" />
              </>
            )}
          </Card>

          <Card to="/audit" title="收入对账" line="链上一手 · 每小时">
            {audit.isLoading && <Loading />}
            {audit.error != null && (
              <ErrorState error={audit.error} onRetry={() => audit.refetch()} />
            )}
            {latestAuditDay && (
              <>
                <Stat
                  k={`六线合计 · ${latestAuditDay.day.slice(5)}`}
                  v={usd(latestAuditDay.liq.total)}
                  h="流动性达标口径"
                />
                <Stat k="全价口径（勿当收入）" v={usd(latestAuditDay.all.total)} />
                <Stat k="事件数" v={num(audit.data?.health.events)} />
                <Stat k="最后事件" v={age(audit.data?.health.last_age_s)} />
              </>
            )}
          </Card>

          <Card to="/pulse" title="注意力" line="实时 · 30 秒">
            {pulse.isLoading && <Loading />}
            {pulse.error != null && (
              <ErrorState error={pulse.error} onRetry={() => pulse.refetch()} />
            )}
            {p && (
              <>
                <Stat k="24 小时发币" v={num(p.kpis.launches)} />
                <Stat k="真毕业" v={num(p.kpis.graduations)} h={pct(p.kpis.graduation_rate)} />
                <Stat k="瞬时捆绑占比" v={pct(p.kpis.instant_share, 1)} />
                <Stat k="中位崩盘" v={secs(p.kpis.median_collapse_s)} />
              </>
            )}
          </Card>

          <Card to="/risk" title="风险评分" line="实时 · 单次约 18 秒">
            <div className="text-12 text-sub">
              输入任意 pump.fun mint，实时读链（bonding curve + 创建者持仓 + 历史）
              后出两个概率：<span className="text-ink">300 秒内跑路</span> 与
              <span className="text-ink"> 真毕业</span>。
            </div>
            <Stat
              k="服务状态"
              v={health.data?.sources.find((s) => s.source === "risk")?.ok ? "可达" : "不可达"}
            />
          </Card>
        </div>

        <p className="mt-4 text-11 text-dim">
          说明：三条线的产出频率差几个数量级（pulse 10 秒 / audit 几分钟 / analysis 是离线静态），
          所以顶部的每个徽标都标了各自的数据年龄 —— 不标出来会把几天前的分析当实时数据看。
        </p>
      </Section>
    </>
  );
}
