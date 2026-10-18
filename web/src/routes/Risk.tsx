/** 风险评分（risk）。全站唯一需要用户输入 + 等待的视图。
 *
 * 实测单次约 18 秒（要扇出约 80 次链上 RPC），所以必须有明确的"进行中"状态，
 * 不能让它悬着。查询只在提交时触发（不是每次输入都打），并且不重试 ——
 * 一个 18 秒的失败重试会让用户等更久。
 */
import { useState } from "react";

import { useRiskScore } from "../api/client";
import { DataTable } from "../components/DataTable";
import { ErrorState, Section } from "../components/States";
import { num } from "../lib/format";

const EXAMPLE = "FgYrixb7ditkeWGoJiYTZDe3ygLmbz9SxEawzyiEpump";

const FLAG_LABELS: Record<string, string> = {
  no_history: "无历史（新钱包）",
  early_missing: "早期特征缺失",
  early_rpc: "早期特征来自 RPC",
  early_stream: "早期特征来自实时流",
  dev_share_high: "创建者持仓高",
  serial_rugger: "连续跑路创建者",
  mayhem: "mayhem 币",
  curve_complete: "曲线已完成",
  non_sol_quote: "非 SOL 计价",
};

export function Risk() {
  const [input, setInput] = useState(EXAMPLE);
  const [mint, setMint] = useState<string | null>(null);
  const q = useRiskScore(mint);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const m = input.trim();
    if (m) setMint(m);
  };

  return (
    <>
      <Section title="风险评分" hint="实时读链 + 模型打分">
        <form onSubmit={submit} className="flex flex-wrap gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            spellCheck={false}
            placeholder="mint 地址（…pump）"
            className="min-w-[320px] flex-1 rounded-ctl border border-line bg-surface px-3 py-2 text-13 text-ink outline-none placeholder:text-dim focus:border-accent"
          />
          <button
            type="submit"
            disabled={q.isFetching}
            className="rounded-ctl border border-accent px-4 py-2 text-13 font-semibold text-accent disabled:border-line disabled:text-dim"
          >
            {q.isFetching ? "读取链上…" : "评分"}
          </button>
        </form>

        <p className="mt-2 text-11 text-dim">
          单次约 18 秒（要读 bonding curve、创建者持仓与前 10 秒的链上事件）。
          结果里带 <span className="text-sub">no_history</span> 表示该创建者没有历史，
          模型在用冷启动特征打分 —— 这是设计内的降级，不是错误。
        </p>

        {q.isFetching && (
          <div className="mt-4 rounded-card border border-line bg-surface p-6 text-center">
            <span className="inline-block size-3 animate-pulse rounded-full bg-accent" />
            <div className="mt-2 text-12 text-sub">正在读链并打分…（约 18 秒）</div>
            <div className="mt-1 text-11 text-dim">{mint}</div>
          </div>
        )}

        {q.error != null && !q.isFetching && (
          <ErrorState error={q.error} />
        )}

        {q.data && !q.isFetching && (
          <>
            <div className="mt-4 grid grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-3">
              <div className="rounded-card border border-line bg-surface p-4">
                <div className="text-11 tracking-widest text-dim">300 秒内跑路概率</div>
                <div
                  className={`mt-1 text-[34px] font-extrabold leading-none ${
                    q.data.p_rug_300s > 0.5 ? "text-bad" : "text-good"
                  }`}
                >
                  {(q.data.p_rug_300s * 100).toFixed(1)}%
                </div>
                <div className="mt-1 text-11 text-dim">模型 {q.data.model_version}</div>
              </div>
              <div className="rounded-card border border-line bg-surface p-4">
                <div className="text-11 tracking-widest text-dim">真毕业概率</div>
                <div className="mt-1 text-[34px] font-extrabold leading-none text-accent">
                  {(q.data.p_graduation * 100).toFixed(1)}%
                </div>
                <div className="mt-1 text-11 text-dim">
                  毕业侧校准较弱，仅作参考（见 risk/report.md）
                </div>
              </div>
              <div className="rounded-card border border-line bg-surface p-4">
                <div className="text-11 tracking-widest text-dim">标记</div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {q.data.flags.length === 0 && (
                    <span className="rounded-full border border-line px-2 py-1 text-11 text-dim">
                      无
                    </span>
                  )}
                  {q.data.flags.map((f) => (
                    <span
                      key={f}
                      className={`rounded-full px-2 py-1 text-11 ${
                        f === "no_history" || f === "early_missing"
                          ? "border border-line text-amber"
                          : "border border-line text-sub"
                      }`}
                    >
                      {FLAG_LABELS[f] ?? f}
                    </span>
                  ))}
                </div>
                <div className="mt-2 text-11 text-dim">
                  creator {q.data.creator ? `${q.data.creator.slice(0, 12)}…` : "—"}
                </div>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-[repeat(auto-fit,minmax(340px,1fr))] gap-4">
              <div>
                <div className="mb-2 text-11 tracking-widest text-dim">贡献最大的因子（系数×z）</div>
                <DataTable
                  columns={[
                    { key: "f", label: "特征", render: (r) => r.feature },
                    { key: "v", label: "值", align: "right", render: (r) => num(r.value as number, 4) },
                    {
                      key: "c", label: "贡献", align: "right",
                      render: (r) => (
                        <span className={r.contribution > 0 ? "text-bad" : "text-good"}>
                          {r.contribution > 0 ? "+" : ""}
                          {num(r.contribution, 3)}
                        </span>
                      ),
                    },
                  ]}
                  rows={q.data.top_factors}
                  rowKey={(r) => r.feature}
                />
              </div>
              <div>
                <div className="mb-2 text-11 tracking-widest text-dim">模型输入</div>
                <DataTable
                  columns={[
                    { key: "k", label: "字段", render: (r) => r.k },
                    { key: "v", label: "值", align: "right", render: (r) => r.v },
                  ]}
                  rows={Object.entries(q.data.inputs).map(([k, v]) => ({
                    k,
                    v: v == null ? "—" : String(v),
                  }))}
                  rowKey={(r) => r.k}
                />
              </div>
            </div>
          </>
        )}
      </Section>
    </>
  );
}
