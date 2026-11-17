import { useRef, useState } from "react";
import { BarChart3, CloudUpload, FileSpreadsheet, Inbox, Plus } from "lucide-react";
import type { ExecutionReport, WorkspaceTab } from "../types";
import ProfileTable from "./ProfileTable";
import ChartCard from "./ChartCard";
import ResultTable from "./ResultTable";

/** 历史报告可寻址导出：带 report_id 定位对应报告，缺省由后端取最新（M2）。 */
function reportQuery(report: ExecutionReport): string {
  return report.report_id ? `&report_id=${report.report_id}` : "";
}

interface Props {
  sessionId: string;
  workspaces: WorkspaceTab[];
  activeId: string | null;
  uploading: boolean;
  onActivate: (datasetId: string) => void;
  onUpload: (file: File) => void;
  onSetColumnType: (column: string, type: string) => void;
  onSetColumnTypes?: (datasetId: string, types: Record<string, string>) => void;
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
}: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [reportStyle, setReportStyle] = useState("academic");
  const [reportFormat, setReportFormat] = useState("docx");
  const active = workspaces.find((workspace) => workspace.datasetId === activeId) ?? workspaces[0];
  const reports = active?.reports ?? [];
  const tableSteps = reports.flatMap((report) =>
    report.steps
      .filter((step) => step.table?.rows?.length)
      .map((step) => ({ report, step, reportIndex: report.steps.indexOf(step) }))
  );
  const charts = reports.flatMap((report) =>
    report.steps
      .map((step, stepIndex) => ({
        filename: step.artifact,
        stepIndex,
        reportId: report.report_id,
      }))
      .filter(
        (item): item is {
          filename: string;
          stepIndex: number;
          reportId: string | undefined;
        } => typeof item.filename === "string"
      )
  );
  // 无专用表格但 result 含数据的步骤：由 JSON 解析生成结果卡（用户要求表格化呈现）
  const resultOnlySteps = reports.flatMap((report) =>
    report.steps
      .map((step, stepIndex) => ({ step, stepIndex }))
      .filter(
        ({ step }) =>
          !step.table?.rows?.length &&
          Object.keys(step.result ?? {}).filter((key) => key !== "method_note").length > 0
      )
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
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
      <div className="flex items-center gap-1 overflow-x-auto border-b border-ink/8 bg-surface-card px-3 py-2">
        {workspaces.map((workspace) => {
          const isActive = workspace.datasetId === active?.datasetId;
          return (
            <button
              key={workspace.datasetId}
              onClick={() => onActivate(workspace.datasetId)}
              className={`shrink-0 cursor-pointer rounded-lg px-3 py-1.5 text-xs font-medium transition-all duration-200 ${
                isActive
                  ? "bg-primary/10 text-primary shadow-[inset_0_-2px_0_0_#3B5BDB]"
                  : "text-ink-muted hover:bg-surface-page hover:text-ink"
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
          className="inline-flex shrink-0 cursor-pointer items-center gap-1 rounded-lg bg-primary/8 px-2.5 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary/15 disabled:cursor-wait disabled:opacity-50"
        >
          <CloudUpload className="h-3.5 w-3.5" />
          {uploading ? "导入中…" : "导入表格"}
        </button>
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        {!active ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-ink-muted">
            <Inbox className="h-10 w-10 opacity-40" />
            <p className="text-sm">上传数据并确认方案后，数据画像与图表将展示在这里</p>
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
                onSetColumnType={(column, type) => onSetColumnType(column, type)}
                onSetColumnTypes={
                  onSetColumnTypes
                    ? (types) => onSetColumnTypes(active.datasetId, types)
                    : undefined
                }
              />
            )}
            {tableSteps.length > 0 && (
              <div>
                <div className="mb-2 flex items-center gap-2">
                  <FileSpreadsheet className="h-4 w-4 text-primary" />
                  <span className="text-sm font-semibold text-primary-dark">
                    统计表交付（{tableSteps.length}）
                  </span>
                </div>
                <div className="space-y-3">
                  {tableSteps.map(({ step, report, reportIndex }) => (
                    <div
                      key={`${step.title}-${reportIndex}`}
                      className="animate-fade-in-up rounded-2xl bg-surface-card p-3 shadow-card transition-shadow duration-300 hover:shadow-hover"
                    >
                      <div className="mb-1.5 flex items-center gap-2">
                        <span className="text-sm font-medium text-ink">{step.title}</span>
                        <a
                          href={`/export/${sessionId}/${reportIndex}?format=json${reportQuery(report)}`}
                          className="ml-auto cursor-pointer text-[11px] text-primary hover:underline"
                        >
                          JSON
                        </a>
                        <a
                          href={`/export/${sessionId}/${reportIndex}?format=csv${reportQuery(report)}`}
                          className="cursor-pointer text-[11px] text-primary hover:underline"
                        >
                          CSV
                        </a>
                        <a
                          href={`/export/${sessionId}/${reportIndex}?format=xlsx${reportQuery(report)}`}
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
                                <th key={col} className="whitespace-nowrap px-2.5 py-1.5 font-medium">
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
                                    className="whitespace-nowrap px-2.5 py-1.5 text-ink"
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
                </div>
                <div className="space-y-3">
                  {resultOnlySteps.map(({ step, stepIndex }) => (
                    <div
                      key={`result-${stepIndex}`}
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
              </div>
            )}
            {reports.length > 0 && (
              <div>
                <div className="mb-2 flex items-center gap-2">
                  <BarChart3 className="h-4 w-4 text-primary" />
                  <span className="text-sm font-semibold text-primary-dark">
                    {`执行产出${charts.length > 0 ? `（${charts.length} 图）` : ""}`}
                  </span>
                  {reports.length > 0 && (
                    <span className="ml-auto flex items-center gap-1.5 text-xs">
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
                        href={`/report/${sessionId}?style=${reportStyle}&format=${reportFormat}`}
                        className="cursor-pointer rounded-lg border border-primary/40 px-2 py-0.5 text-[11px] font-medium text-primary transition-colors hover:bg-primary/5"
                      >
                        导出报告
                      </a>
                    </span>
                  )}
                </div>
                <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                  {charts.map(({ filename, stepIndex, reportId }, index) => (
                    <ChartCard
                      key={`${filename}-${index}`}
                      baseUrl={`/data/${sessionId}/${active.datasetId}/artifacts`}
                      filename={filename}
                      extraFormats={["JPG", "PDF", "TIF"].map((label) => ({
                        label,
                        href: `/export/${sessionId}/${stepIndex}?format=${label.toLowerCase()}${
                          reportId ? `&report_id=${reportId}` : ""
                        }`,
                      }))}
                    />
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
