import { useState } from "react";
import { CheckCircle2, Tags } from "lucide-react";
import { COLUMN_TYPE_LABELS, type ColumnType, type TypeReviewRequest } from "../types";

const SELECTABLE: ColumnType[] = ["continuous", "ordinal", "categorical", "index"];

interface Props {
  request: TypeReviewRequest;
  submitting: boolean;
  onConfirm: (types: Record<string, string>) => void;
}

export default function TypeReviewCard({ request, submitting, onConfirm }: Props) {
  const [types, setTypes] = useState<Record<string, string>>(
    Object.fromEntries(request.columns.map((col) => [col.name, col.type]))
  );

  const setAllNumericToContinuous = () => {
    setTypes((prev) => {
      const next = { ...prev };
      for (const col of request.columns) {
        const current = next[col.name] ?? col.type;
        if (current === "continuous" || current === "ordinal") {
          next[col.name] = "continuous";
        }
      }
      return next;
    });
  };

  return (
    <div className="animate-fade-in-up rounded-2xl border border-primary-cyan/30 bg-surface-card p-4 shadow-card">
      <div className="mb-1 flex items-center gap-2">
        <Tags className="h-4 w-4 text-primary-cyan" />
        <span className="text-sm font-semibold text-primary-dark">请敲定变量类型</span>
      </div>
      <p className="mb-3 text-xs leading-relaxed text-ink-muted">{request.message}</p>

      <div className="space-y-2">
        {request.columns.map((col) => (
          <div key={col.name} className="flex items-center gap-2 rounded-lg bg-surface-page px-3 py-2">
            <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">{col.name}</span>
            {col.missing > 0 && (
              <span className="text-[11px] text-warn">缺失 {col.missing}</span>
            )}
            <select
              value={types[col.name] ?? col.type}
              onChange={(event) =>
                setTypes((prev) => ({ ...prev, [col.name]: event.target.value }))
              }
              className="cursor-pointer rounded-md border border-ink/15 bg-white px-2 py-1 text-xs outline-none focus:border-primary"
            >
              {SELECTABLE.map((type) => (
                <option key={type} value={type}>
                  {COLUMN_TYPE_LABELS[type] ?? type}
                </option>
              ))}
            </select>
          </div>
        ))}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <p className="min-w-0 flex-1 text-[11px] text-ink-muted">
          连续型可用于参数检验；等级型将优先非参数方法；索引列默认不参与统计。
        </p>
        <button
          type="button"
          onClick={setAllNumericToContinuous}
          className="shrink-0 cursor-pointer rounded-md border border-ink/15 px-2 py-1 text-[11px] text-ink-muted transition-colors hover:border-primary hover:text-primary"
        >
          数值列全部设为连续
        </button>
      </div>

      <button
        onClick={() => onConfirm(types)}
        disabled={submitting}
        className="mt-3 inline-flex cursor-pointer items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-white transition-all hover:bg-primary-dark active:scale-[0.98] disabled:cursor-wait disabled:opacity-60"
      >
        <CheckCircle2 className="h-4 w-4" />
        {submitting ? "提交中…" : "确认类型，开始讨论"}
      </button>
    </div>
  );
}
