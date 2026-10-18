import type { ReactNode } from "react";

type Tone = "default" | "good" | "bad" | "amber" | "accent";

const VALUE_TONE: Record<Tone, string> = {
  default: "text-ink",
  good: "text-good",
  bad: "text-bad",
  amber: "text-amber",
  accent: "text-accent",
};

export function KpiCard({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: Tone;
}) {
  return (
    <div className="rounded-card border border-line bg-surface p-4">
      <div className="text-11 tracking-widest text-dim">{label}</div>
      <div className={`mt-1 text-22 font-semibold ${VALUE_TONE[tone]}`}>{value}</div>
      <div className="mt-1 text-11 text-dim">{hint}</div>
    </div>
  );
}

export function KpiGrid({ children }: { children: ReactNode }) {
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(190px,1fr))] gap-3">
      {children}
    </div>
  );
}
