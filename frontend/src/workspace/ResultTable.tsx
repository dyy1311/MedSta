/**
 * 通用「结果 JSON → 表格」渲染器（034）：任何工具的 result 都以表格呈现，
 * 原始 JSON 仅作为折叠后备。这是用户硬要求「结果解析成表格」的统一出口。
 */
import { useMemo } from "react";

/** 已知非数据键：不在表格中呈现（另有专属 UI） */
const META_KEYS = new Set(["method_note", "strategy", "artifact", "chart_error"]);

type Scalar = string | number | boolean | null;

const isScalar = (value: unknown): value is Scalar =>
  value === null || ["string", "number", "boolean"].includes(typeof value);

const fmt = (value: unknown): string => {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : String(Math.round(value * 1e4) / 1e4);
  }
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value);
};

interface KVTable {
  kind: "kv";
  rows: [string, string][];
}
interface MatrixTable {
  kind: "matrix";
  title: string;
  columns: string[];
  rows: string[][];
}
type Section = KVTable | MatrixTable;

/** 把任意 result 对象拆成「指标键值表 + 若干数据子表」 */
export function resultToSections(result: Record<string, unknown>): Section[] {
  const kv: [string, string][] = [];
  const tables: Section[] = [];

  const walk = (prefix: string, source: Record<string, unknown>) => {
    for (const [key, value] of Object.entries(source)) {
      if (META_KEYS.has(key)) continue;
      const label = prefix ? `${prefix}.${key}` : key;
      if (isScalar(value)) {
        kv.push([label, fmt(value)]);
      } else if (Array.isArray(value)) {
        const objects = value.filter(
          (item): item is Record<string, unknown> =>
            typeof item === "object" && item !== null && !Array.isArray(item)
        );
        if (objects.length > 0) {
          const columns = [...new Set(objects.flatMap((item) => Object.keys(item)))];
          tables.push({
            kind: "matrix",
            title: label,
            columns,
            rows: objects.map((item) => columns.map((col) => fmt(item[col]))),
          });
        } else if (value.length > 0) {
          kv.push([label, value.map((item) => fmt(item)).join("、")]);
        }
      } else if (typeof value === "object" && value !== null) {
        const nested = value as Record<string, unknown>;
        const scalars = Object.entries(nested).filter(([, v]) => isScalar(v));
        const complexes = Object.entries(nested).filter(([, v]) => !isScalar(v) && !META_KEYS.has(""));
        if (complexes.length === 0) {
          // 纯标量对象（如 odds_ratios、stats）：并入键值表
          for (const [sub, subValue] of scalars) kv.push([`${label}.${sub}`, fmt(subValue)]);
        } else {
          walk(label, nested);
        }
      }
    }
  };

  walk("", result);
  if (kv.length > 0) tables.unshift({ kind: "kv", rows: kv });
  return tables;
}

export default function ResultTable({
  result,
  compact = false,
}: {
  result: Record<string, unknown>;
  compact?: boolean;
}) {
  const sections = useMemo(() => resultToSections(result), [result]);
  if (sections.length === 0) return null;

  return (
    <div className={compact ? "space-y-2" : "space-y-3"}>
      {sections.map((section, index) =>
        section.kind === "kv" ? (
          <table
            key={`kv-${index}`}
            className="w-full text-left text-xs"
            data-testid={`result-kv-${index}`}
          >
            <tbody>
              {section.rows.map(([label, value]) => (
                <tr key={label} className="border-b border-ink/5 last:border-0">
                  <td className="whitespace-nowrap py-1 pr-3 text-ink-muted">{label}</td>
                  <td className="num py-1 font-medium text-ink">{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div key={`mx-${index}`}>
            {section.title && (
              <p className="mb-1 text-[11px] font-medium text-ink-muted">{section.title}</p>
            )}
            <div className="overflow-x-auto rounded-lg border border-ink/8">
              <table
                className="w-full text-left text-xs"
                data-testid={`result-matrix-${index}`}
              >
                <thead>
                  <tr className="border-b border-ink/8 bg-surface-raised text-ink-muted">
                    {section.columns.map((col) => (
                      <th key={col} className="whitespace-nowrap px-2 py-1 font-medium">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {section.rows.map((row, rowIndex) => (
                    <tr
                      key={rowIndex}
                      className={`transition-colors hover:bg-primary-soft/50 ${
                        rowIndex % 2 ? "bg-surface-page/60" : ""
                      }`}
                    >
                      {row.map((cell, cellIndex) => (
                        <td key={cellIndex} className="num whitespace-nowrap px-2 py-1 text-ink">
                          {cell}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )
      )}
    </div>
  );
}
