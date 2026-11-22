/** 出图配置可选图表：与后端 stats/registry.py 的 CHART_TYPES ∪ {none} 同源
 *  （AnalysisConfigCard.charts.test.tsx 守护全集，缺项会导致默认图显示错误且无法选回）。 */
export const CHART_OPTIONS = [
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
  { value: "survival_curve", label: "生存曲线" },
  { value: "none", label: "不出图" },
];
