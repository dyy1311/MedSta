import { useState } from "react";
import { ImagePlus, Play } from "lucide-react";
import type { PlotSuggestStep } from "../types";

interface Props {
  steps: PlotSuggestStep[];
  submitting: boolean;
  onPlotLater: (stepIndex: number, chartType: string) => void;
}

const CHART_LABELS: Record<string, string> = {
  histogram: "直方图",
  boxplot: "箱线图",
  violin: "提琴图",
  bar: "柱状图",
  grouped_bar: "分组柱状图",
  pie: "饼图",
  line: "折线图",
  scatter: "散点图",
  heatmap: "热力图",
  qq_plot: "Q-Q 图",
  residual_plot: "残差图",
};

export default function PlotSuggestCard({ steps, submitting, onPlotLater }: Props) {
  const [choices, setChoices] = useState<Record<number, string>>(
    Object.fromEntries(steps.map((step) => [step.step_index, step.charts[0]]))
  );

  return (
    <div className="animate-fade-in-up rounded-2xl border border-primary-cyan/30 bg-surface-card p-4 shadow-card">
      <div className="mb-1 flex items-center gap-2">
        <ImagePlus className="h-4 w-4 text-primary-cyan" />
        <span className="text-sm font-semibold text-primary-dark">是否为结果绘图？</span>
      </div>
      <p className="mb-3 text-xs text-ink-muted">
        以下步骤已产出统计表格，可选择图表类型补绘（稍后也可在工作区查看表格）。
      </p>
      <div className="space-y-2">
        {steps.map((step) => (
          <div key={step.step_index} className="flex flex-wrap items-center gap-2 rounded-lg bg-surface-page px-3 py-2">
            <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">{step.title}</span>
            <select
              value={choices[step.step_index]}
              onChange={(event) =>
                setChoices((prev) => ({ ...prev, [step.step_index]: event.target.value }))
              }
              className="cursor-pointer rounded-md border border-ink/15 bg-white px-2 py-1 text-xs outline-none focus:border-primary"
            >
              {step.charts.map((chart) => (
                <option key={chart} value={chart}>
                  {CHART_LABELS[chart] ?? chart}
                </option>
              ))}
            </select>
            <button
              onClick={() => onPlotLater(step.step_index, choices[step.step_index])}
              disabled={submitting}
              className="inline-flex cursor-pointer items-center gap-1 rounded-md bg-primary px-2.5 py-1 text-xs font-medium text-white transition-all hover:bg-primary-dark disabled:cursor-wait disabled:opacity-60"
            >
              <Play className="h-3 w-3" />
              绘图
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
