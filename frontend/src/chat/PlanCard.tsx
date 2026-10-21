import { useState } from "react";
import { CheckCircle2, ClipboardList, PenLine, Sparkles } from "lucide-react";
import type { PlanOption, PlanStep } from "../types";

const METHOD_LABELS: Record<string, string> = {
  describe: "描述统计",
  missing_report: "缺失报告",
  normality_test: "正态性检验",
  group_compare: "两组比较",
  hypothesis_test: "两组比较",
  anova: "多组比较",
  chi_square: "卡方检验",
  correlation: "相关性",
  regression: "线性回归",
  logistic_regression: "Logistic 回归",
  timeseries_forecast: "趋势预测",
};

const ACTION_STYLE: Record<string, string> = {
  confirm: "bg-primary text-white hover:bg-primary-dark",
  revise: "border border-primary/40 text-primary hover:bg-primary/8",
  explain: "border border-ink/15 text-ink-muted hover:bg-ink/5",
  custom: "border border-dashed border-warn/50 text-warn hover:bg-warn/10",
  supplement: "border border-dashed border-warn/50 text-warn hover:bg-warn/10",
};

interface Props {
  message: string;
  steps: PlanStep[];
  options: PlanOption[];
  confirming: boolean;
  onOption: (optionId: string, content?: string) => void;
}

export default function PlanCard({ message, steps, options, confirming, onOption }: Props) {
  const [active, setActive] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const activeOption = options.find((option) => option.id === active);

  return (
    <div className="animate-fade-in-up rounded-2xl border border-primary/15 bg-surface-card p-4 shadow-card">
      <div className="mb-3 flex items-center gap-2">
        <ClipboardList className="h-4 w-4 text-primary" />
        <span className="text-sm font-semibold text-primary-dark">分析方案</span>
      </div>
      <p className="mb-3 text-sm leading-relaxed text-ink">{message}</p>
      <ol className="mb-4 space-y-2">
        {steps.map((step, index) => (
          <li
            key={index}
            className="flex items-start gap-3 rounded-lg bg-surface-page px-3 py-2 text-sm"
          >
            <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
              {index + 1}
            </span>
            <span className="flex flex-wrap items-baseline gap-x-2">
              <span className="font-medium text-ink">{step.title}</span>
              <span className="rounded bg-primary-cyan/10 px-1.5 py-0.5 text-xs text-primary-cyan">
                {METHOD_LABELS[step.method] ?? step.method}
              </span>
              <span className="text-xs text-ink-muted">{step.target_columns.join(" / ")}</span>
              {step.chart_type !== "none" && (
                <span className="rounded bg-primary/8 px-1.5 py-0.5 text-xs text-primary">
                  {step.chart_type}
                </span>
              )}
            </span>
            {step.rationale && (
              <details className="mt-1 w-full">
                <summary className="cursor-pointer text-[11px] text-primary">选择依据</summary>
                <p className="mt-1 rounded bg-surface-card/80 p-2 text-[11px] leading-relaxed text-ink-muted">
                  {step.rationale}
                </p>
              </details>
            )}
          </li>
        ))}
      </ol>

      <div className="flex flex-wrap gap-2">
        {options.map((option) => (
          <button
            key={option.id}
            disabled={confirming && option.action === "confirm"}
            onClick={() => {
              if (option.action === "custom" || option.action === "supplement") {
                setActive(active === option.id ? null : option.id);
                return;
              }
              onOption(option.id);
            }}
            className={`inline-flex cursor-pointer items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-all active:scale-[0.98] disabled:cursor-wait disabled:opacity-60 ${
              ACTION_STYLE[option.action] ?? ACTION_STYLE.explain
            }`}
          >
            {option.action === "confirm" ? (
              <CheckCircle2 className="h-4 w-4" />
            ) : option.action === "explain" ? (
              <Sparkles className="h-4 w-4" />
            ) : (
              <PenLine className="h-4 w-4" />
            )}
            {option.label}
          </button>
        ))}
      </div>

      {activeOption && (
        <div className="mt-2 flex gap-2">
          <input
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="补充你的分析要求，例如：按性别分层、改用非参数检验"
            className="min-w-0 flex-1 rounded-lg border border-ink/15 bg-surface-page px-3 py-2 text-sm outline-none transition-colors focus:border-primary"
          />
          <button
            onClick={() => {
              onOption(activeOption.id, note.trim());
              setNote("");
              setActive(null);
            }}
            disabled={!note.trim()}
            className="cursor-pointer rounded-lg bg-warn px-3 py-2 text-sm font-medium text-white transition-all hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-50"
          >
            发送
          </button>
        </div>
      )}
    </div>
  );
}
