import { useRef, useState } from "react";
import { BarChart3, ChevronDown, CloudUpload, Eraser, FileSpreadsheet, Inbox, Plus } from "lucide-react";
import type { ExecutionReport, PlotStyle, ReportStep, WorkspaceTab } from "../types";
import { withToken } from "../api/client";
import { CHART_OPTIONS } from "../chat/chartOptions";
import ClearOutputsDialog from "../components/ClearOutputsDialog";
import ProfileTable from "./ProfileTable";
import ChartCard from "./ChartCard";
import ResultTable from "./ResultTable";

/** 产物文件名 step_{n}_{method}_{chart}.png 与注册表同源，用来回填出图后修改标注 */
const ARTIFACT_CHARTS = CHART_OPTIONS
  .map((item) => item.value)
  .filter((value) => value !== "none")
  .sort((a, b) => b.length - a.length);

function chartTypeOf(step: Pick<ReportStep, "chart_type" | "artifact" | "method">): string | undefined {
  if (step.chart_type && step.chart_type !== "none") return step.chart_type;
  const stem = String(step.artifact ?? "").split("?")[0].replace(/\.[^.]+$/, "");
  if (step.method) {
    const token = `_${step.method}_`;
    const at = stem.lastIndexOf(token);
    if (at >= 0) {
      const chart = stem.slice(at + token.length);
      if (ARTIFACT_CHARTS.includes(chart)) return chart;
    }
    return undefined;
  }
  return ARTIFACT_CHARTS.find((chart) => stem.endsWith(`_${chart}`));
}

/** 历史报告可寻址导出：带 report_id 定位对应报告，缺省由后端取最新（M2）。 */
function reportQuery(report: ExecutionReport): string {
  return report.report_id ? `&report_id=${report.report_id}` : "";
}

/** 模块卡折叠按钮（标题行右侧）：折叠后只留标题，结果默认可见优先 */
function CollapseToggle({
  collapsed,
  label,
  onToggle,
}: {
  collapsed: boolean;
  label: string;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={!collapsed}
      aria-label={collapsed ? `展开${label}` : `收起${label}`}
      className="ml-auto cursor-pointer rounded-lg p-1 text-ink-muted transition-colors hover:bg-surface-page hover:text-ink"
    >
      <ChevronDown
        className={`h-4 w-4 transition-transform ${collapsed ? "-rotate-90" : ""}`}
      />
    </button>
  );
}

interface Props {
  sessionId: string;
  workspaces: WorkspaceTab[];
  activeId: string | null;
  uploading: boolean;
  onActivate: (datasetId: string) => void;
  onUpload: (file: File) => void;
  /** 单列类型修改：带 datasetId——工作区标签与「会话绑定数据集」可能不同 */
  onSetColumnType: (
    datasetId: string,
    column: string,
    type: string,
    source?: "manual" | "ai"
  ) => void;
  onSetColumnTypes?: (
    datasetId: string,
    types: Record<string, string>,
    source?: "manual" | "ai"
  ) => void;
  /** 041 AI 确认类型：触发建议请求 / 当前建议列表 / 模型分析中 */
  onSuggestTypes?: () => void;
  columnSuggestions?: { name: string; suggested_type: string; confidence: number; reason: string }[];
  suggesting?: boolean;
  /** 清空工作区既往产出（保留导入表格）；未传入则不展示入口 */
  onClearOutputs?: () => void;
  /** 执行中禁止清空，避免删掉正在写入的图表 */
  clearDisabled?: boolean;
  onRestyleChart?: (stepIndex: number, chartType: string, style: PlotStyle, method: string) => void;
}

export default function WorkspacePanel({
  sessionId,
  workspaces,
  activeId,
  uploading,
  onActivate,
  onUpload,
  onSetColumnType,
  onSetColumnTypes,
  onSuggestTypes,
  columnSuggestions,
  suggesting = false,
  onClearOutputs,
  clearDisabled = false,
  onRestyleChart,
}: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [reportStyle, setReportStyle] = useState("academic");
  const [reportFormat, setReportFormat] = useState("docx");
  const [confirmClear, setConfirmClear] = useState(false);
  // 模块卡折叠：画像/统计表/图表各自独立，默认展开（结果默认可见优先于省空间）
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const toggleSection = (key: string) =>
    setCollapsed((prev) => ({ ...prev, [key]: !prev[key] }));
  const active = workspaces.find((workspace) => workspace.datasetId === activeId) ?? workspaces[0];
  const reports = active?.reports ?? [];
  // 统计表按轮次保留（可对照前后两次执行）
  const tableSteps = reports.flatMap((report) =>
    report.steps
      .filter((step) => step.table?.rows?.length)
      .map((step) => ({ report, step, reportIndex: report.steps.indexOf(step) }))
  );
  // 实时图表倒序：所有轮次都展示，最新交付的在最上面
  const latestReport = reports[reports.length - 1];
  const charts = reports
    .flatMap((report) =>
      report.steps.map((step, stepIndex) => ({
        filename: step.artifact,
        stepIndex,
        method: step.method,
        reportId: report.report_id,
        title: step.title,
        chartType: chartTypeOf(step),
        plotStyle: step.plot_style,
        plotRev: typeof step.result?.plot_rev === "number" ? step.result.plot_rev : undefined,
        restylable: report === latestReport,
      }))
    )
    .filter(
      (item): item is {
        filename: string;
        stepIndex: number;
        method: string;
        reportId: string | undefined;
        title: string;
        chartType: string | undefined;
        plotStyle: PlotStyle | undefined;
        plotRev: number | undefined;
        restylable: boolean;
      } => typeof item.filename === "string"
    )
    .reverse();
  // 无专用表格但 result 含数据的步骤：由 JSON 解析生成结果卡（用户要求表格化呈现）
  const resultOnlySteps = reports.flatMap((report, reportIdx) =>
    report.steps
      .map((step, stepIndex) => ({ step, stepIndex, reportIdx }))
      .filter(
        ({ step }) =>
          !step.table?.rows?.length &&
          Object.keys(step.result ?? {}).filter((key) => key !== "method_note").length > 0
      )
  );

  return (
    <div className="flex h-full min-h-0 flex-col break-words">
      {/* 工作区分页 Tab */}
      <input
        ref={fileRef}
        type="file"
        accept=".csv,.xlsx,.xls"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onUpload(file);
          event.target.value = "";
        }}
      />
      <div className="flex shrink-0 items-center gap-1 overflow-x-auto border-b border-ink/8 bg-surface-card px-3 py-2">
        {workspaces.map((workspace) => {
          const isActive = workspace.datasetId === active?.datasetId;
          return (
            <button
              key={workspace.datasetId}
              onClick={() => onActivate(workspace.datasetId)}
              className={`min-h-11 shrink-0 cursor-pointer rounded-lg border-b-2 px-3 py-1.5 text-xs font-medium transition-colors duration-200 ${
                isActive
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-transparent text-ink-muted hover:bg-surface-page hover:text-ink"
              }`}
            >
              {workspace.name}
              {workspace.imputed && (
                <span className="ml-1 rounded bg-warn/15 px-1 py-0.5 text-[10px] font-normal text-warn">
                  已插补
                </span>
              )}
            </button>
          );
        })}
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          title="上传新表格（新建工作区）"
          className="shrink-0 cursor-pointer rounded-lg border border-dashed border-ink/20 px-2.5 py-1.5 text-xs text-ink-muted transition-colors hover:border-primary hover:text-primary disabled:cursor-wait disabled:opacity-50"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          className="inline-flex min-h-11 shrink-0 cursor-pointer items-center gap-1 rounded-lg bg-primary/8 px-2.5 py-1.5 text-xs font-medium text-primary transition-colors duration-200 hover:bg-primary/15 disabled:cursor-wait disabled:opacity-50"
        >
          <CloudUpload className="h-3.5 w-3.5" aria-hidden="true" />
          {uploading ? "导入中…" : "导入表格"}
        </button>
        {onClearOutputs && workspaces.length > 0 && (
          <button
            type="button"
            onClick={() => setConfirmClear(true)}
            disabled={clearDisabled}
            title={clearDisabled ? "分析正在执行，结束后再清空" : "清空工作台既往产出（保留导入表格）"}
            className="ml-auto inline-flex min-h-11 shrink-0 cursor-pointer items-center gap-1 rounded-lg border border-ink/15 px-2.5 py-1.5 text-xs font-medium text-ink-muted transition-colors duration-200 hover:border-danger/40 hover:text-danger disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Eraser className="h-3.5 w-3.5" aria-hidden="true" />
            清空产出
          </button>
        )}
      </div>
      {confirmClear && onClearOutputs && (
        <ClearOutputsDialog
          onCancel={() => setConfirmClear(false)}
          onConfirm={() => {
            setConfirmClear(false);
            onClearOutputs();
          }}
        />
      )}

      <div className="flex min-h-0 flex-1 flex-col">
        <section className="flex min-h-32 min-w-0 flex-1 flex-col overflow-hidden border-b border-ink/10">
          <div className="shrink-0 border-b border-ink/8 px-3 py-1.5 text-xs font-medium text-primary-dark">
            导入表格
          </div>
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        {!active ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-ink-muted">
            <Inbox className="h-10 w-10 opacity-40" />
            <p className="text-sm leading-relaxed">上传数据并确认方案后，数据画像与图表将展示在这里</p>
          </div>
        ) : (
          <>
            {active.imputed && (
              <div className="rounded-lg border border-warn/30 bg-warn/8 p-2.5 text-xs leading-relaxed text-warn">
                该数据集为 MICE 单数据集插补结果：缺失值已填补，但标准误偏小，不宜直接当作确证性结论；原始数据仍在其他标签页。
              </div>
            )}
            {active.profile && (
              <ProfileTable
                profile={active.profile}
                onSetColumnType={(column, type, source) =>
                  onSetColumnType(active.datasetId, column, type, source)
                }
                onSetColumnTypes={
                  onSetColumnTypes
                    ? (types, source) => onSetColumnTypes(active.datasetId, types, source)
                    : undefined
                }
                onSuggestTypes={onSuggestTypes}
                suggestions={columnSuggestions}
                suggesting={suggesting}
                collapsed={Boolean(collapsed.profile)}
                onToggleCollapse={() => toggleSection("profile")}
              />
            )}
          </>
        )}
          </div>
        </section>
        <section className="flex min-h-32 min-w-0 flex-1 flex-col overflow-hidden">
          <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-ink/8 px-3 py-1.5">
            <BarChart3 className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
            <span className="min-w-0 text-xs font-medium leading-relaxed text-primary-dark">
              图表交付
              {charts.length > 0 ? `（${charts.length}）` : ""}
              {reports.length > 1 ? ` · ${reports.length} 轮` : ""}
            </span>
            {reports.length > 0 && (
              <span className="ml-auto flex flex-wrap items-center gap-1.5 text-xs">
                <select
                  aria-label="报告风格"
                  value={reportStyle}
                  onChange={(event) => setReportStyle(event.target.value)}
                  className="cursor-pointer rounded-lg border border-ink/15 bg-white px-1.5 py-0.5 text-[11px]"
                >
                  <option value="academic">学术风</option>
                  <option value="lite">轻量</option>
                </select>
                <select
                  aria-label="报告格式"
                  value={reportFormat}
                  onChange={(event) => setReportFormat(event.target.value)}
                  className="cursor-pointer rounded-lg border border-ink/15 bg-white px-1.5 py-0.5 text-[11px]"
                >
                  <option value="docx">Word</option>
                  <option value="pdf">PDF</option>
                  <option value="md">Markdown</option>
                </select>
                <a
                  href={withToken(`/report/${sessionId}?style=${reportStyle}&format=${reportFormat}`)}
                  className="cursor-pointer rounded-lg border border-primary/40 px-2 py-0.5 text-[11px] font-medium text-primary transition-colors hover:bg-primary/5"
                >
                  导出报告
                </a>
              </span>
            )}
          </div>
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
            {charts.length === 0 && tableSteps.length === 0 && resultOnlySteps.length === 0 && (
              <p className="text-sm leading-relaxed text-ink-muted">
                执行后图表按时间倒序展示在这里，最新的在最上面。
              </p>
            )}
            {charts.length > 0 && (
              <div className="grid grid-cols-1 gap-4">
                {charts.map(({ filename, stepIndex, method, reportId, title, chartType, plotStyle, plotRev, restylable }, index) => (
                  <ChartCard
                    key={`${reportId ?? "r"}-${filename}-${index}`}
                    baseUrl={withToken(`/data/${sessionId}/${active!.datasetId}/artifacts`)}
                    filename={filename}
                    caption={title}
                    cacheRev={plotRev}
                    chartType={chartType}
                    plotStyle={plotStyle}
                    onRestyle={
                      restylable && onRestyleChart && chartType && chartType !== "none"
                        ? (style) => onRestyleChart(stepIndex, chartType, style, method)
                        : undefined
                    }
                    extraFormats={["JPG", "PDF", "TIF"].map((label) => ({
                      label,
                      href: withToken(`/export/${sessionId}/${stepIndex}?format=${label.toLowerCase()}${
                        reportId ? `&report_id=${reportId}` : ""
                      }`),
                    }))}
                  />
                ))}
              </div>
            )}
            {tableSteps.length > 0 && (
              <div data-testid="table-delivery">
                <div className="mb-2 flex items-center gap-2">
                  <FileSpreadsheet className="h-4 w-4 text-primary" />
                  <span className="text-sm font-semibold text-primary-dark">
                    统计表交付（{tableSteps.length}）
                  </span>
                  <CollapseToggle
                    collapsed={Boolean(collapsed.tables)}
                    label="统计表交付"
                    onToggle={() => toggleSection("tables")}
                  />
                </div>
                {!collapsed.tables && (
                <div className="space-y-3">
                  {tableSteps.map(({ step, report, reportIndex }) => (
                    <div
                      // 跨报告可能同名同下标步骤：key 需带报告标识，否则 React 复用错行
                      key={`${report.report_id ?? reportIndex}-${reportIndex}-${step.title}`}
                      className="animate-fade-in-up rounded-2xl bg-surface-card p-3 shadow-card transition-shadow duration-300 hover:shadow-hover"
                    >
                      <div className="mb-1.5 flex items-center gap-2">
                        <span className="text-sm font-medium text-ink">{step.title}</span>
                        <a
                          href={withToken(
                            `/export/${sessionId}/${reportIndex}?format=json${reportQuery(report)}`
                          )}
                          className="ml-auto cursor-pointer text-[11px] text-primary hover:underline"
                        >
                          JSON
                        </a>
                        <a
                          href={withToken(
                            `/export/${sessionId}/${reportIndex}?format=csv${reportQuery(report)}`
                          )}
                          className="cursor-pointer text-[11px] text-primary hover:underline"
                        >
                          CSV
                        </a>
                        <a
                          href={withToken(
                            `/export/${sessionId}/${reportIndex}?format=xlsx${reportQuery(report)}`
                          )}
                          className="cursor-pointer text-[11px] text-primary hover:underline"
                        >
                          Excel
                        </a>
                      </div>
                      <div className="overflow-x-auto rounded-lg border border-ink/8">
                        <table className="w-full text-left text-xs">
                          <thead>
                            <tr className="border-b border-ink/8 bg-surface-raised text-ink-muted">
                              {step.table!.columns.map((col) => (
                                <th key={col} className="break-words px-2.5 py-1.5 font-medium">
                                  {col}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {step.table!.rows.map((row, rowIndex) => (
                              <tr
                                key={rowIndex}
                                className={`transition-colors hover:bg-primary-soft/50 ${
                                  rowIndex % 2 ? "bg-surface-page/60" : ""
                                }`}
                              >
                                {step.table!.columns.map((col) => (
                                  <td
                                    key={col}
                                    className="break-words px-2.5 py-1.5 text-ink"
                                  >
                                    {String(row[col] ?? "—")}
                                  </td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  ))}
                </div>
                )}
              </div>
            )}
            {resultOnlySteps.length > 0 && (
              <div>
                <div className="mb-2 flex items-center gap-2">
                  <FileSpreadsheet className="h-4 w-4 text-primary" />
                  <span className="text-sm font-semibold text-primary-dark">
                    结果数据（{resultOnlySteps.length}）
                  </span>
                  <span className="text-[11px] text-ink-faint">无专用表格的步骤，由结果 JSON 解析生成</span>
                  <CollapseToggle
                    collapsed={Boolean(collapsed.results)}
                    label="结果数据"
                    onToggle={() => toggleSection("results")}
                  />
                </div>
                {!collapsed.results && (
                <div className="space-y-3">
                  {resultOnlySteps.map(({ step, stepIndex, reportIdx }) => (
                    <div
                      key={`result-${reportIdx}-${stepIndex}`}
                      data-testid={`result-card-${stepIndex}`}
                      className="animate-fade-in-up rounded-2xl bg-surface-card p-3 shadow-card"
                    >
                      <div className="mb-2 flex items-center gap-2">
                        <span className="text-sm font-medium text-ink">{step.title}</span>
                        <span
                          className={`h-1.5 w-1.5 rounded-full ${
                            step.status === "success" ? "bg-ok" : "bg-danger"
                          }`}
                        />
                      </div>
                      <ResultTable result={step.result} />
                    </div>
                  ))}
                </div>
                )}
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
