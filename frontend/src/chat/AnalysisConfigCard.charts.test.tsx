import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import AnalysisConfigCard from "./AnalysisConfigCard";
import { CHART_OPTIONS } from "./chartOptions";

// 与后端 stats/registry.py 的 CHART_TYPES ∪ {none} 严格同源（契约镜像）：
// 缺项会导致该图表的默认值在下拉框显示错误且无法手动选回。
const BACKEND_CHART_TYPES = [
  "histogram",
  "boxplot",
  "violin",
  "scatter",
  "line",
  "bar",
  "grouped_bar",
  "heatmap",
  "qq_plot",
  "residual_plot",
  "pie",
  "survival_curve",
  "none",
];

describe("出图配置图表枚举", () => {
  it("覆盖后端 ChartType 全集", () => {
    const values = CHART_OPTIONS.map((option) => option.value);
    for (const type of BACKEND_CHART_TYPES) {
      expect(values, `缺图表类型 ${type}`).toContain(type);
    }
  });

  it("后端下发 charts 白名单时只列该工具支持的图（+ 不出图）", () => {
    render(
      <AnalysisConfigCard
        submitting={false}
        onConfirm={vi.fn()}
        config={{
          steps: [
            { step_id: "step_1", title: "两组比较", default_chart: "boxplot", charts: ["boxplot", "violin"] },
          ],
          multi_chart: false,
          alpha: 0.05,
          correction: "holm",
          message: "确认图表类型",
        }}
      />
    );

    const select = screen.getAllByRole("combobox")[0]; // [0]=步骤图表，后续是 α/校正
    const values = within(select)
      .getAllByRole("option")
      .map((option) => (option as HTMLOptionElement).value);

    // 只保留工具支持的图 + none；不再把生存曲线等无关图列给两组比较
    expect(values).toEqual(["boxplot", "violin", "none"]);
  });
});
