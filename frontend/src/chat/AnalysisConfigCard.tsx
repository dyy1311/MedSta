import { useState } from "react";
import { Image, LayoutGrid, Sigma, Play, SkipForward } from "lucide-react";
import type { ChartConfigRequest } from "../types";

const CHART_OPTIONS = [
  { value: "boxplot", label: "箱线图" },
  { value: "violin", label: "提琴图" },
  { value: "line", label: "折线图" },
  { value: "bar", label: "柱状图" },
  { value: "grouped_bar", label: "分组柱状图" },
  { value: "histogram", label: "直方图" },
  { value: "scatter", label: "散点图" },
  { value: "pie", label: "饼图" },
  { value: "heatmap", label: "热力图" },
  { value: "qq_plot", label: "Q-Q 图" },
  { value: "residual_plot", label: "残差图" },
  { value: "none", label: "不出图" },
];

interface Props {
  config: ChartConfigRequest;
  submitting: boolean;
  onConfirm: (payload: {
    choices: { step_id: string; chart_type: string }[];
    layout: string;
    alpha: number;
    correction: string;
    use_default?: boolean;
  }) => void;
}

export default function AnalysisConfigCard({ config, submitting, onConfirm }: Props) {
  const [chartChoices, setChartChoices] = useState<Record<string, string>>(
    Object.fromEntries(config.steps.map((s) => [s.step_id, s.default_chart]))
  );
  const [layout, setLayout] = useState("separate");
  const [alpha, setAlpha] = useState(String(config.alpha));
  const [correction, setCorrection] = useState(config.correction);

  const submit = (useDefault = false) => {
    onConfirm({
      choices: config.steps.map((step) => ({
        step_id: step.step_id,
        chart_type: chartChoices[step.step_id] ?? step.default_chart,
      })),
      layout,
      alpha: Number(alpha) || 0.05,
      correction,
      ...(useDefault ? { use_default: true } : {}),
    });
  };

  return (
    <div className="animate-fade-in-up rounded-2xl border border-primary-cyan/30 bg-surface-card p-4 shadow-card">
      <div className="mb-3 flex items-center gap-2">
        <Image className="h-4 w-4 text-primary-cyan" />
        <span className="text-sm font-semibold text-primary-dark">出图前确认</span>
      </div>
      <p className="mb-3 text-xs text-ink-muted">{config.message}</p>

      <div className="space-y-2">
        {config.steps.map((step) => (
          <div key={step.step_id} className="flex flex-wrap items-center gap-2 rounded-lg bg-surface-page px-3 py-2">
            <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">{step.title}</span>
            <select
              value={chartChoices[step.step_id] ?? step.default_chart}
              onChange={(event) =>
                setChartChoices((prev) => ({ ...prev, [step.step_id]: event.target.value }))
              }
              className="cursor-pointer rounded-md border border-ink/15 bg-white px-2 py-1 text-xs outline-none focus:border-primary"
            >
              {CHART_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        ))}
      </div>

      {config.multi_chart && (
        <div className="mt-3">
          <div className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-ink-muted">
            <LayoutGrid className="h-3.5 w-3.5" /> 多图画板
          </div>
          <div className="flex gap-2">
            {[
              { value: "separate", label: "分别出图" },
              { value: "shared", label: "同一画板拼图" },
            ].map((option) => (
              <button
                key={option.value}
                onClick={() => setLayout(option.value)}
                className={`cursor-pointer rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                  layout === option.value
                    ? "bg-primary text-white"
                    : "border border-ink/15 text-ink-muted hover:border-primary/50"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="mt-3 grid grid-cols-2 gap-3">
        <div>
          <div className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-ink-muted">
            <Sigma className="h-3.5 w-3.5" /> 显著性水平 α
          </div>
          <select
            value={alpha}
            onChange={(event) => setAlpha(event.target.value)}
            className="w-full cursor-pointer rounded-md border border-ink/15 bg-white px-2 py-1.5 text-xs outline-none focus:border-primary"
          >
            <option value="0.05">0.05（常用）</option>
            <option value="0.01">0.01（更严格）</option>
            <option value="0.001">0.001（非常严格）</option>
            <option value="0.1">0.1（探索性）</option>
          </select>
        </div>
        <div>
          <div className="mb-1.5 text-xs font-medium text-ink-muted">多重比较校正</div>
          <select
            value={correction}
            onChange={(event) => setCorrection(event.target.value)}
            className="w-full cursor-pointer rounded-md border border-ink/15 bg-white px-2 py-1.5 text-xs outline-none focus:border-primary"
          >
            <option value="holm">Holm（推荐）</option>
            <option value="bonferroni">Bonferroni</option>
            <option value="none">不校正</option>
          </select>
        </div>
      </div>

      <div className="mt-3 flex gap-2">
        <button
          onClick={() => submit(false)}
          disabled={submitting}
          className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-white transition-all hover:bg-primary-dark active:scale-[0.98] disabled:cursor-wait disabled:opacity-60"
        >
          <Play className="h-4 w-4" />
          {submitting ? "正在执行…" : "按此配置执行"}
        </button>
        <button
          onClick={() => submit(true)}
          disabled={submitting}
          className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-ink/15 px-3 py-2 text-sm text-ink-muted transition-colors hover:bg-surface-page disabled:cursor-wait"
        >
          <SkipForward className="h-4 w-4" />
          跳过，用默认
        </button>
      </div>
    </div>
  );
}
