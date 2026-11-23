import { useState } from "react";
import { ChevronDown, Database, Loader2 } from "lucide-react";
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

interface ColumnSuggestion {
  name: string;
  suggested_type: string;
  confidence: number;
  reason: string;
}

interface Props {
  profile: TableProfile;
  onSetColumnType?: (column: string, type: string, source?: "manual" | "ai") => void;
  /** 批量列类型修改：一次回调 {列名: 类型}，source 区分「采纳建议」与手动批量 */
  onSetColumnTypes?: (types: Record<string, string>, source?: "manual" | "ai") => void;
  /** 触发模型列类型建议（041 AI 确认） */
  onSuggestTypes?: () => void;
  /** 模型建议（041）；用户采纳后经宿主校验落库 */
  suggestions?: ColumnSuggestion[];
  /** 模型正在生成建议：按钮进入加载态，避免重复点击与「没反应」的错觉 */
  suggesting?: boolean;
  /** 折叠：模块卡可收起 */
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

export default function ProfileTable({
  profile,
  onSetColumnType,
  onSetColumnTypes,
  onSuggestTypes,
  suggestions = [],
  suggesting = false,
  collapsed = false,
  onToggleCollapse,
}: Props) {
  const columns = Object.values(profile.columns);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [batchType, setBatchType] = useState("continuous");
  const editable = Boolean(onSetColumnType || onSetColumnTypes);
  const suggestionByColumn = new Map(suggestions.map((item) => [item.name, item]));

  const allSelected = columns.length > 0 && selected.size === columns.length;
  const toggleAll = () => {
    setSelected(allSelected ? new Set() : new Set(columns.map((col) => col.name)));
  };
  const toggleOne = (name: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };
  const applyBatch = () => {
    if (!onSetColumnTypes || selected.size === 0) return;
    const types: Record<string, string> = {};
    for (const name of selected) types[name] = batchType;
    onSetColumnTypes(types);
    setSelected(new Set());
  };

  return (
    <div className="rounded-2xl bg-surface-card p-4 shadow-card">
      <div className="mb-3 flex items-center gap-2">
        <Database className="h-4 w-4 text-primary-cyan" />
        <span className="text-sm font-semibold text-primary-dark">数据画像</span>
        <span className="ml-auto text-xs text-ink-muted">
          {profile.row_count} 行 × {profile.column_count} 列
        </span>
        {onToggleCollapse && (
          <button
            type="button"
            onClick={onToggleCollapse}
            aria-expanded={!collapsed}
            aria-label={collapsed ? "展开数据画像" : "收起数据画像"}
            className="cursor-pointer rounded-lg p-1 text-ink-muted transition-colors hover:bg-surface-page hover:text-ink"
          >
            <ChevronDown className={`h-4 w-4 transition-transform ${collapsed ? "-rotate-90" : ""}`} />
          </button>
        )}
      </div>

      {!collapsed && (
        <>
      {editable && suggestions.length > 0 && (
        <div
          data-testid="suggestions-bar"
          className="animate-fade-in-up mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-primary-cyan/30 bg-primary-cyan/5 px-3 py-2"
        >
          <span className="text-xs font-medium text-primary-dark">AI 类型建议</span>
          <span className="text-[11px] text-ink-muted">（模型建议仅供参考，采纳后生效）</span>
          <button
            type="button"
            onClick={() => {
              if (!onSetColumnTypes) return;
              const types: Record<string, string> = {};
              for (const item of suggestions) types[item.name] = item.suggested_type;
              onSetColumnTypes(types, "ai");
            }}
            className="ml-auto cursor-pointer rounded-lg bg-primary px-2.5 py-1 text-[11px] font-medium text-white transition-colors hover:bg-primary-hover"
          >
            全部采纳建议
          </button>
        </div>
      )}
      {editable && onSuggestTypes && (
        <div className="mb-3">
          <button
            type="button"
            onClick={onSuggestTypes}
            disabled={suggesting}
            aria-busy={suggesting}
            data-testid="suggest-types"
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-primary-cyan/50 px-2.5 py-1 text-[11px] font-medium text-primary-cyan transition-colors hover:bg-primary-cyan/10 disabled:cursor-wait disabled:opacity-70"
          >
            {suggesting && <Loader2 className="h-3 w-3 animate-spin" />}
            {suggesting ? "正在分析列含义…" : "AI 确认类型"}
          </button>
          {suggesting && (
            <p
              data-testid="suggest-pending"
              className="mt-1.5 text-[11px] leading-relaxed text-ink-muted"
            >
              模型正在逐列判断语义类型（表越大越慢，通常几秒到十几秒），结果到达后会自动出现在下表。
            </p>
          )}
        </div>
      )}

      {editable && (
        <div
          data-testid="batch-bar"
          className="mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-primary/20 bg-primary/5 px-3 py-2"
        >
          <span className="text-xs font-medium text-primary-dark">
            {`已选 ${selected.size} 列`}
          </span>
          <button
            type="button"
            onClick={() => setSelected(new Set())}
            disabled={selected.size === 0}
            className="cursor-pointer text-xs text-ink-muted hover:text-ink disabled:opacity-40"
          >
            清除选择
          </button>
          <label className="ml-auto flex items-center gap-1.5 text-xs text-ink">
            批量设为
            <select
              aria-label="批量类型"
              value={batchType}
              onChange={(event) => setBatchType(event.target.value)}
              disabled={selected.size === 0}
              className="cursor-pointer rounded-lg border border-ink/15 bg-white px-2 py-1 text-xs disabled:opacity-40"
            >
              {SELECTABLE.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={applyBatch}
            disabled={selected.size === 0}
            className="cursor-pointer rounded-lg bg-primary px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-40"
          >
            应用类型
          </button>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-ink/10 text-xs text-ink-muted">
              {editable && (
                <th className="w-8 py-2 pr-1">
                  <input
                    type="checkbox"
                    aria-label="全选列"
                    checked={allSelected}
                    onChange={toggleAll}
                    className="cursor-pointer"
                  />
                </th>
              )}
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
                className={`border-b border-ink/5 transition-colors last:border-0 hover:bg-surface-page ${
                  selected.has(col.name) ? "bg-primary-soft/40" : ""
                }`}
              >
                {editable && (
                  <td className="w-8 py-2 pr-1 align-middle">
                    <input
                      type="checkbox"
                      aria-label={`选择列 ${col.name}`}
                      checked={selected.has(col.name)}
                      onChange={() => toggleOne(col.name)}
                      className="cursor-pointer"
                    />
                  </td>
                )}
                <td className="py-2 pr-3 font-medium text-ink">{col.name}</td>
                <td className="py-2 pr-3">
                  {suggestionByColumn.has(col.name) && (
                    <div className="mb-1 flex items-center gap-1">
                      <span className="rounded bg-primary-cyan/10 px-1 py-0.5 text-[10px] text-primary-cyan">
                        {`建议: ${COLUMN_TYPE_LABELS[suggestionByColumn.get(col.name)!.suggested_type] ?? suggestionByColumn.get(col.name)!.suggested_type}（${Math.round(suggestionByColumn.get(col.name)!.confidence * 100)}%）`}
                      </span>
                      {onSetColumnType && (
                        <button
                          type="button"
                          title={`采纳建议：${col.name}`}
                          onClick={() =>
                            onSetColumnType(
                              col.name,
                              suggestionByColumn.get(col.name)!.suggested_type,
                              "ai"
                            )
                          }
                          className="cursor-pointer text-[10px] font-medium text-primary hover:underline"
                        >
                          采纳
                        </button>
                      )}
                      <span className="text-[10px] text-ink-faint">
                        {suggestionByColumn.get(col.name)!.reason}
                      </span>
                    </div>
                  )}
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
        </>
      )}
    </div>
  );
}
