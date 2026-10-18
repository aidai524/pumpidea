/** 统一外壳：导航 + 数据新鲜度条。
 *
 * 新鲜度放在**每一页都看得见的地方**，因为三条线的产出频率差几个数量级：
 * pulse 10 秒重建、audit 几分钟、analysis 是离线静态（实测 age ≈ 1.8 天）。
 * 把它藏在设置页里，等于默认"用户不会误读"。
 */
import { NavLink, Outlet } from "react-router-dom";

import { useHealth } from "../api/client";
import { StaleBadge } from "./States";

const NAV = [
  { to: "/", label: "总览", end: true },
  { to: "/analysis", label: "研究" },
  { to: "/audit", label: "收入对账" },
  { to: "/pulse", label: "注意力" },
  { to: "/risk", label: "打分" },
];

export function AppShell() {
  const health = useHealth();

  return (
    <div className="mx-auto max-w-[1280px] px-6 pb-16 pt-8">
      <header className="border-b border-line pb-4">
        <div className="flex flex-wrap items-baseline justify-between gap-4">
          <div>
            <div className="text-[18px] font-semibold tracking-[2px]">pumpidea</div>
            <div className="mt-1 text-11 text-dim">
              pump.fun 发币经济 · 研究 / 收入对账 / 注意力 / 风险评分
            </div>
          </div>

          <nav className="flex flex-wrap gap-1">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `rounded-ctl px-3 py-2 text-12 ${
                    isActive
                      ? "bg-surface text-accent"
                      : "text-sub hover:bg-surface hover:text-ink"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>

        {/* 数据新鲜度：四路来源各自多久以前 */}
        <div className="mt-4 flex flex-wrap gap-2">
          {health.data?.sources.map((s) => (
            <StaleBadge
              key={s.source}
              source={s.source}
              ageSeconds={s.age_seconds ?? null}
            />
          ))}
          {health.isError && (
            <span className="rounded-full border border-line px-3 py-1 text-11 text-bad">
              健康检查失败
            </span>
          )}
        </div>
      </header>

      <main className="mt-2">
        <Outlet />
      </main>

      <footer className="mt-12 border-t border-line pt-4 text-11 text-dim">
        数字来源：analysis / audit / pulse 三份产出物 + risk 实时打分；经
        <span className="text-sub"> /api/v1 </span>
        契约读取。口径与已知缺陷见各页底部，完整推导见仓库的 report.md。
      </footer>
    </div>
  );
}
