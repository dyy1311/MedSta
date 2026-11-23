import { useState } from "react";
import { CheckCircle2, CircleDashed, RotateCcw, Wand2, XCircle } from "lucide-react";
import { withToken } from "../api/client";
import type { StepDelivery } from "../types";

/**
 * 节点级交付（047）：每个工作节点完成即展示结果或错误。
 *
 * 失败节点不再是「整条链重来」：可以直接重跑该节点，或补充信息让模型只重写这一个节点。
 */
interface Props {
  sessionId: string;
  datasetId: string | null;
  items: StepDelivery[];
  busy: boolean;
  onRetry: (index: number) => void;
  onAmend: (index: number, note: string) => void;
}

function StatusIcon({ status }: { status: StepDelivery["status"] }) {
  if (status === "success") return <CheckCircle2 className="h-3.5 w-3.5 text-ok" />;
  return <XCircle className="h-3.5 w-3.5 text-danger" />;
}

export default function StepDeliveryCard({
  sessionId,
  datasetId,
  items,
  busy,
  onRetry,
  onAmend,
}: Props) {
  const [open, setOpen] = useState<number | null>(null);
  const [note, setNote] = useState<Record<number, string>>({});

  if (!items.length) return null;
  const done = items.filter((item) => item.status === "success").length;
  const failed = items.filter((item) => item.status === "failed").length;

  return (
    <div
      data-testid="step-delivery"
      className="animate-fade-in-up rounded-2xl border border-primary/15 bg-surface-card p-3 shadow-card"
    >
      <div className="mb-2 flex items-center gap-2">
        <CircleDashed className={`h-4 w-4 text-primary ${busy ? "animate-spin" : ""}`} />
        <span className="text-sm font-semibold text-primary-dark">节点交付</span>
        <span className="text-[11px] text-ink-muted">
          {done}/{items.length} 完成{failed ? ` · ${failed} 个失败` : ""}
        </span>
      </div>

      <ul className="space-y-1.5">
        {items.map((item) => {
          const expanded = open === item.index;
          return (
            <li key={item.index} data-testid={`step-delivery-${item.index}`}>
              <button
                type="button"
                onClick={() => setOpen(expanded ? null : item.index)}
                aria-expanded={expanded}
                className="flex w-full cursor-pointer items-center gap-2 rounded-lg bg-surface-page px-2.5 py-1.5 text-left"
              >
                <span className="text-[11px] text-ink-faint">{item.index + 1}</span>
                <StatusIcon status={item.status} />
                <span className="text-xs font-medium text-ink">{item.title}</span>
                <code className="rounded bg-primary-cyan/10 px-1 py-0.5 text-[10px] text-primary-cyan">
                  {item.method}
                </code>
                {item.updated && (
                  <span className="rounded bg-warn/10 px-1 py-0.5 text-[10px] text-warn">已更新</span>
                )}
                <span className="ml-auto text-[10px] text-ink-faint">
                  {expanded ? "收起" : "详情"}
                </span>
              </button>

              {expanded && (
                <div className="mt-1 space-y-2 rounded-lg bg-surface-page/70 px-3 py-2">
                  {item.status === "failed" && (
                    <>
                      <p className="text-[11px] leading-relaxed text-danger">
                        {item.error?.message ?? "执行失败"}
                      </p>
                      {item.error?.hint && (
                        <p className="text-[11px] leading-relaxed text-warn">{item.error.hint}</p>
                      )}
                      <div className="flex flex-wrap items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => onRetry(item.index)}
                          disabled={busy}
                          className="inline-flex cursor-pointer items-center gap-1 rounded-md border border-primary/40 px-2 py-0.5 text-[11px] text-primary hover:bg-primary/5 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <RotateCcw className="h-3 w-3" />
                          重跑该节点及其下游
                        </button>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <input
                          value={note[item.index] ?? ""}
                          onChange={(event) =>
                            setNote((prev) => ({ ...prev, [item.index]: event.target.value }))
                          }
                          placeholder="补充说明（如：按 group 分组比较 value）"
                          aria-label={`节点${item.index + 1}补充说明`}
                          className="min-w-0 flex-1 rounded-md border border-ink/15 bg-white px-2 py-1 text-[11px] outline-none focus:border-primary"
                        />
                        <button
                          type="button"
                          onClick={() => {
                            onAmend(item.index, note[item.index] ?? "");
                            setNote((prev) => ({ ...prev, [item.index]: "" }));
                          }}
                          disabled={busy || !(note[item.index] ?? "").trim()}
                          className="inline-flex cursor-pointer items-center gap-1 rounded-md bg-primary px-2 py-1 text-[11px] font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <Wand2 className="h-3 w-3" />
                          让 AI 修正
                        </button>
                      </div>
                    </>
                  )}

                  {item.status === "success" && item.table?.rows?.length ? (
                    <div className="overflow-x-auto rounded border border-ink/8">
                      <table className="w-full text-left text-[11px]">
                        <thead>
                          <tr className="bg-surface-card text-ink-muted">
                            {item.table.columns.map((column) => (
                              <th key={column} className="px-2 py-1 font-medium">
                                {column}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {item.table.rows.map((row, rowIndex) => (
                            <tr key={rowIndex} className="border-t border-ink/5">
                              {item.table!.columns.map((column) => (
                                <td key={column} className="whitespace-nowrap px-2 py-1 text-ink">
                                  {String(row[column] ?? "—")}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : null}

                  {item.status === "success" && item.artifact && datasetId && (
                    <a
                      href={withToken(`/data/${sessionId}/${datasetId}/artifacts/${item.artifact}`)}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-block text-[11px] text-primary hover:underline"
                    >
                      查看图表
                    </a>
                  )}
                  {item.status === "success" && !item.table?.rows?.length && !item.artifact && (
                    <p className="text-[11px] text-ink-muted">该节点无表格产出（结果见审阅卡）</p>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
