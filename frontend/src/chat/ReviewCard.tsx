import { useState } from "react";
import { CheckCheck, PencilLine, TrendingUp, TriangleAlert } from "lucide-react";
import type { ExecutionReport } from "../types";

interface Props {
  report: ExecutionReport;
  delivered: boolean;
  sessionId: string;
  artifactBase: string;
  onAccept: () => void;
  onRevise: (note: string) => void;
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

export default function ReviewCard({ report, delivered, artifactBase, onAccept, onRevise }: Props) {
  const [revising, setRevising] = useState(false);
  const [note, setNote] = useState("");
  const warnings = report.steps
    .map((step) => step.result?.multiplicity_warning as string | undefined)
    .filter(Boolean);

  return (
    <div className="animate-fade-in-up rounded-2xl border border-primary-cyan/25 bg-surface-card p-4 shadow-card">
      <div className="mb-3 flex items-center gap-2">
        <TrendingUp className="h-4 w-4 text-primary-cyan" />
        <span className="text-sm font-semibold text-primary-dark">
          {delivered ? "分析交付" : "执行完成，请审阅结果"}
        </span>
        <span className={`ml-auto h-2 w-2 rounded-full ${delivered ? "bg-ok animate-breathe" : "bg-warn"}`} />
      </div>

      {warnings.length > 0 && (
        <div className="mb-3 rounded-lg border border-warn/30 bg-warn/8 p-2.5 text-xs leading-relaxed text-warn">
          <TriangleAlert className="mr-1 inline h-3.5 w-3.5" />
          {warnings[0]}
        </div>
      )}

      <ol className="mb-3 space-y-2">
        {report.steps.map((step, index) => (
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
            {step.table?.rows?.length ? (
              <p className="mt-1.5 text-[11px] text-primary">
                已生成统计表格（{step.table.rows.length} 行）→ 前往「工作区」查看与导出
              </p>
            ) : null}
            <StrategyPanel result={step.result} />
            <details className="mt-1.5">
              <summary className="cursor-pointer text-[11px] text-ink-muted">原始数据</summary>
              <pre className="mt-1 max-h-40 overflow-auto rounded bg-primary-dark/95 p-2 text-[11px] text-primary-cyan">
                {JSON.stringify(step.result, null, 2)}
              </pre>
            </details>
          </li>
        ))}
      </ol>

      {delivered ? (
        <p className="text-xs text-ink-muted">
          结果已交付。如需调整分析方向，直接在下方输入修正意见即可重新讨论。
        </p>
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
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg bg-ok px-3 py-2 text-sm font-medium text-white transition-all hover:brightness-105 active:scale-[0.98]"
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
