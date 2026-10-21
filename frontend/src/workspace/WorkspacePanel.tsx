import { useRef } from "react";
import { BarChart3, CloudUpload, FileSpreadsheet, Inbox, Plus } from "lucide-react";
import type { WorkspaceTab } from "../types";
import ProfileTable from "./ProfileTable";
import ChartCard from "./ChartCard";

interface Props {
  sessionId: string;
  workspaces: WorkspaceTab[];
  activeId: string | null;
  uploading: boolean;
  onActivate: (datasetId: string) => void;
  onUpload: (file: File) => void;
  onSetColumnType: (column: string, type: string) => void;
}

export default function WorkspacePanel({
  sessionId,
  workspaces,
  activeId,
  uploading,
  onActivate,
  onUpload,
  onSetColumnType,
}: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const active = workspaces.find((workspace) => workspace.datasetId === activeId) ?? workspaces[0];
  const reports = active?.reports ?? [];
  const tableSteps = reports.flatMap((report) =>
    report.steps
      .filter((step) => step.table?.rows?.length)
      .map((step) => ({ report, step, reportIndex: report.steps.indexOf(step) }))
  );
  const charts = reports.flatMap((report) =>
    report.steps.filter((step) => step.artifact).map((step) => step.artifact as string)
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
            {active.profile && (
              <ProfileTable
                profile={active.profile}
                onSetColumnType={(column, type) => onSetColumnType(column, type)}
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
                  {tableSteps.map(({ step, reportIndex }) => (
                    <div
                      key={`${step.title}-${reportIndex}`}
                      className="rounded-2xl bg-surface-card p-3 shadow-card"
                    >
                      <div className="mb-1.5 flex items-center gap-2">
                        <span className="text-sm font-medium text-ink">{step.title}</span>
                        <a
                          href={`/export/${sessionId}/${reportIndex}?format=csv`}
                          className="ml-auto cursor-pointer text-[11px] text-primary hover:underline"
                        >
                          CSV
                        </a>
                        <a
                          href={`/export/${sessionId}/${reportIndex}?format=xlsx`}
                          className="cursor-pointer text-[11px] text-primary hover:underline"
                        >
                          Excel
                        </a>
                      </div>
                      <div className="overflow-x-auto rounded-lg border border-ink/8">
                        <table className="w-full text-left text-xs">
                          <thead>
                            <tr className="bg-surface-page text-ink-muted">
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
                                className={rowIndex % 2 ? "bg-surface-page/60" : ""}
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
            {charts.length > 0 && (
              <div>
                <div className="mb-2 flex items-center gap-2">
                  <BarChart3 className="h-4 w-4 text-primary" />
                  <span className="text-sm font-semibold text-primary-dark">
                    执行产出（{charts.length}）
                  </span>
                </div>
                <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                  {charts.map((filename, index) => (
                    <ChartCard
                      key={`${filename}-${index}`}
                      baseUrl={`/data/${sessionId}/${active.datasetId}/artifacts`}
                      filename={filename}
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
