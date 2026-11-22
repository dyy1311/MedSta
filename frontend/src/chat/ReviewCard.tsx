import { useState } from "react";
import { CheckCheck, PencilLine, TrendingUp, TriangleAlert } from "lucide-react";
import type { ExecutionReport } from "../types";
import ResultTable from "../workspace/ResultTable";

interface Props {
  report: ExecutionReport;
  delivered: boolean;
  sessionId: string;
  artifactBase: string;
  onAccept: () => void;
  onRevise: (note: string) => void;
  /** 修正意见已提交：锁定交互，等待模型按修正重出方案 */
  submitted?: boolean;
  /** 点击「前往工作区」时切换 Tab（041 修复：链接此前无实际行为） */
  onGoWorkspace?: () => void;
}

function StrategyPanel({ result }: { result: Record<string, unknown> }) {
  const [open, setOpen] = useState(false);
  const strategy = result.strategy as
    | { steps: string[]; final_method: string; alternative: string }
    | undefined;
  if (!strategy?.steps?.length) return null;
  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen((prev) => !prev)}
        className="cursor-pointer text-[11px] text-primary hover:underline"
      >
        {open ? "收起检验依据" : "查看检验依据（策略链）"}
      </button>
      {open && (
        <ol className="mt-1.5 space-y-1 rounded-lg bg-primary/5 p-2 text-[11px] leading-relaxed text-ink-muted">
          {strategy.steps.map((item, index) => (
            <li key={index}>· {item}</li>
          ))}
          <li className="font-medium text-primary">
            最终方法：{strategy.final_method}｜{strategy.alternative}
          </li>
        </ol>
      )}
    </div>
  );
}

function MethodNote({ note }: { note: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-1.5">
      <button
        onClick={() => setOpen((prev) => !prev)}
        className="cursor-pointer text-[11px] text-ink-muted hover:underline"
      >
        {open ? "收起方法依据" : "方法依据"}
      </button>
      {open && (
        <p className="mt-1 rounded-lg bg-primary/5 p-2 text-[11px] leading-relaxed text-ink-muted">
          {note}
        </p>
      )}
    </div>
  );
}

export default function ReviewCard({
  report,
  delivered,
  artifactBase,
  onAccept,
  onRevise,
  submitted = false,
  onGoWorkspace,
}: Props) {
  const [revising, setRevising] = useState(false);
  const [note, setNote] = useState("");
  const warnings = report.steps
    .map((step) => step.result?.multiplicity_warning as string | undefined)
    .filter(Boolean);
  const interpretation = report.interpretation ?? null;
  const findingFor = (index: number) =>
    interpretation?.steps.find((item) => item.step_index === index) ?? null;
  const unverified = interpretation?.unverified_numbers ?? [];

  return (
    <div className="animate-fade-in-up rounded-2xl border border-primary-cyan/25 bg-surface-card p-4 shadow-card">
      <div className="mb-3 flex items-center gap-2">
        <TrendingUp className="h-4 w-4 text-primary-cyan" />
        <span className="text-sm font-semibold text-primary-dark">
          {delivered ? "分析交付" : "执行完成，请审阅结果"}
        </span>
        <span className={`ml-auto h-2 w-2 rounded-full ${delivered ? "bg-ok animate-breathe" : "bg-warn"}`} />
      </div>

      {interpretation?.summary && (
        <p className="mb-3 text-xs leading-relaxed text-ink-muted">{interpretation.summary}</p>
      )}

      {warnings.length > 0 && (
        <div className="mb-3 rounded-lg border border-warn/30 bg-warn/8 p-2.5 text-xs leading-relaxed text-warn">
          <TriangleAlert className="mr-1 inline h-3.5 w-3.5" />
          {warnings[0]}
        </div>
      )}

      <ol className="mb-3 space-y-2">
        {report.steps.map((step, index) => {
          const finding = findingFor(index);
          return (
          <li key={index} className="rounded-lg bg-surface-page px-3 py-2 text-sm">
            <div className="flex items-center gap-2">
              <span className={`h-1.5 w-1.5 rounded-full ${step.status === "success" ? "bg-ok" : "bg-danger"}`} />
              <span className="font-medium text-ink">{step.title}</span>
              {step.artifact && (
                <a
                  href={`${artifactBase}/${step.artifact}`}
                  target="_blank"
                  rel="noreferrer"
                  className="ml-auto cursor-pointer text-xs text-primary hover:underline"
                >
                  查看图表
                </a>
              )}
            </div>
            {finding?.finding ? (
              <p className="mt-1.5 text-xs leading-relaxed text-ink">{finding.finding}</p>
            ) : null}
            {finding?.caveat ? (
              <p className="mt-1 text-[11px] leading-relaxed text-warn">{finding.caveat}</p>
            ) : null}
            {step.table?.rows?.length ? (
              <button
                type="button"
                onClick={() => onGoWorkspace?.()}
                className="mt-1.5 cursor-pointer text-left text-[11px] text-primary underline decoration-primary/40 hover:decoration-primary"
              >
                已生成统计表格（{step.table.rows.length} 行）→ 点击前往「工作区」查看与导出报告
              </button>
            ) : null}
            {!step.artifact && typeof step.result?.chart_error === "string" && (
              <p className="mt-1 text-[11px] leading-relaxed text-warn">
                统计结果已生成，但图表渲染失败：{step.result.chart_error}
              </p>
            )}
            <StrategyPanel result={step.result ?? {}} />
            {typeof step.result?.method_note === "string" && step.result.method_note.trim() ? (
              <MethodNote note={step.result.method_note} />
            ) : null}
            {/* 结果数据以表格呈现（用户硬要求）；原始 JSON 仅作折叠后备 */}
            <details className="mt-1.5" open={!step.table?.rows?.length}>
              <summary className="cursor-pointer text-[11px] text-ink-muted">结果数据</summary>
              <div className="mt-1.5">
                <ResultTable result={step.result} compact />
              </div>
              <details className="mt-1.5">
                <summary className="cursor-pointer text-[11px] text-ink-faint">原始 JSON</summary>
                <pre className="mt-1 max-h-40 overflow-auto rounded bg-primary-dark/95 p-2 text-[11px] text-primary-cyan">
                  {JSON.stringify(step.result, null, 2)}
                </pre>
              </details>
            </details>
          </li>
          );
        })}
      </ol>

      {unverified.length > 0 && (
        <p className="mb-2 text-[11px] leading-relaxed text-warn">
          <TriangleAlert className="mr-1 inline h-3 w-3" />
          解读含未核验数值：{unverified.join("、")}（仅作参考，以统计表为准）
        </p>
      )}

      {interpretation && interpretation.caveats.length > 0 && (
        <ul className="mb-3 space-y-1 rounded-lg border border-ink/10 bg-surface-page p-2.5 text-[11px] leading-relaxed text-ink-muted">
          {interpretation.caveats.map((item, index) => (
            <li key={index}>· {item}</li>
          ))}
        </ul>
      )}

      {submitted ? (
        <p data-testid="review-submitted" className="text-xs text-ink-muted">
          修正意见已提交，正在按修正重新生成方案…
        </p>
      ) : delivered ? (
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-xs text-ink-muted">
            结果已交付。可直接在下方提问，或回到方案调整。
          </p>
          <button
            onClick={() => onRevise("")}
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-warn/40 px-3 py-1.5 text-xs font-medium text-warn transition-colors hover:bg-warn/10"
          >
            <PencilLine className="h-3.5 w-3.5" />
            调整分析方案
          </button>
        </div>
      ) : revising ? (
        <div className="flex gap-2">
          <input
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="例如：不要用直方图，改成看相关性"
            className="min-w-0 flex-1 rounded-lg border border-ink/15 bg-surface-page px-3 py-2 text-sm outline-none transition-colors focus:border-primary"
          />
          <button
            onClick={() => note.trim() && onRevise(note.trim())}
            disabled={!note.trim()}
            className="cursor-pointer rounded-lg bg-warn px-3 py-2 text-sm font-medium text-white transition-all hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-50"
          >
            提交修正
          </button>
        </div>
      ) : (
        <div className="flex gap-2">
          <button
            onClick={onAccept}
            className="inline-flex min-h-11 cursor-pointer items-center gap-1.5 rounded-lg bg-ok px-3 py-2 text-sm font-medium text-white transition-colors duration-200 hover:brightness-105"
          >
            <CheckCheck className="h-4 w-4" />
            确认交付
          </button>
          <button
            onClick={() => setRevising(true)}
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-warn/40 px-3 py-2 text-sm font-medium text-warn transition-colors hover:bg-warn/10"
          >
            <PencilLine className="h-4 w-4" />
            提出修正
          </button>
        </div>
      )}
    </div>
  );
}
