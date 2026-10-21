import { Database } from "lucide-react";
import { COLUMN_TYPE_LABELS, type TableProfile } from "../types";

const SELECTABLE: { value: string; label: string }[] = [
  { value: "continuous", label: "数值-连续型" },
  { value: "ordinal", label: "数值-等级型" },
  { value: "categorical", label: "类别型" },
  { value: "index", label: "序列索引" },
];

const TYPE_COLORS: Record<string, string> = {
  continuous: "bg-primary-cyan/10 text-primary-cyan",
  ordinal: "bg-violet-100 text-violet-700",
  categorical: "bg-primary/10 text-primary",
  index: "bg-ink/8 text-ink-muted",
  datetime: "bg-warn/10 text-warn",
  boolean: "bg-ok/10 text-ok",
  text: "bg-ink/8 text-ink-muted",
};

interface Props {
  profile: TableProfile;
  onSetColumnType?: (column: string, type: string) => void;
}

export default function ProfileTable({ profile, onSetColumnType }: Props) {
  const columns = Object.values(profile.columns);
  return (
    <div className="rounded-2xl bg-surface-card p-4 shadow-card">
      <div className="mb-3 flex items-center gap-2">
        <Database className="h-4 w-4 text-primary-cyan" />
        <span className="text-sm font-semibold text-primary-dark">数据画像</span>
        <span className="ml-auto text-xs text-ink-muted">
          {profile.row_count} 行 × {profile.column_count} 列
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-ink/10 text-xs text-ink-muted">
              <th className="py-2 pr-3 font-medium">列名</th>
              <th className="py-2 pr-3 font-medium">类型</th>
              <th className="py-2 pr-3 font-medium">缺失</th>
              <th className="py-2 font-medium">关键统计</th>
            </tr>
          </thead>
          <tbody>
            {columns.map((col) => (
              <tr
                key={col.name}
                className="border-b border-ink/5 transition-colors last:border-0 hover:bg-surface-page"
              >
                <td className="py-2 pr-3 font-medium text-ink">{col.name}</td>
                <td className="py-2 pr-3">
                  {onSetColumnType ? (
                    <select
                      value={
                        ["continuous", "ordinal", "categorical", "index"].includes(col.type)
                          ? col.type
                          : "categorical"
                      }
                      onChange={(event) => onSetColumnType(col.name, event.target.value)}
                      className={`cursor-pointer rounded px-1.5 py-0.5 text-xs outline-none ${
                        TYPE_COLORS[col.type] ?? TYPE_COLORS.text
                      }`}
                    >
                      {SELECTABLE.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span
                      className={`rounded px-1.5 py-0.5 text-xs ${
                        TYPE_COLORS[col.type] ?? TYPE_COLORS.text
                      }`}
                    >
                      {COLUMN_TYPE_LABELS[col.type] ?? col.type}
                    </span>
                  )}
                </td>
                <td className={`py-2 pr-3 text-xs ${col.missing > 0 ? "text-warn" : "text-ink-muted"}`}>
                  {col.missing}
                </td>
                <td className="py-2 text-xs text-ink-muted">
                  {col.type === "continuous" || col.type === "ordinal"
                    ? `均值 ${(Number(col.stats.mean) || 0).toFixed(2)} · 中位数 ${col.stats.median} · q25 ${col.stats.q25} · q75 ${col.stats.q75} · 最小 ${col.stats.min} · 最大 ${col.stats.max} · 计数 ${col.stats.count}`
                    : col.type === "categorical" || col.type === "boolean"
                      ? `${col.stats.distinct} 个类别 · 最高频 ${col.stats.top}`
                      : `${col.stats.count} 个非空值`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
