import { useState } from "react";
import { GitBranch, Waypoints } from "lucide-react";
import type { PlanFlow } from "../types";

/**
 * 方案流程图（047）：节点即注册表工具，边即依赖。
 *
 * 不引入 mermaid 渲染依赖（体积/离线），用纵向节点 + 依赖标注表达同一张图；
 * mermaid 文本保留在折叠区，便于用户复制到文档或评审。
 */
export default function PlanFlowView({ flow }: { flow: PlanFlow }) {
  const [open, setOpen] = useState<number | null>(null);

  if (!flow.nodes.length) return null;

  return (
    <div
      data-testid="plan-flow"
      className="mb-3 rounded-xl border border-primary/20 bg-primary/5 p-3"
    >
      <div className="mb-2 flex items-center gap-2">
        <Waypoints className="h-4 w-4 text-primary" />
        <span className="text-xs font-semibold text-primary-dark">
          工作流图（{flow.nodes.length} 个节点）
        </span>
        <span className="text-[11px] text-ink-muted">按依赖顺序执行，每节点独立交付</span>
      </div>

      <ol className="space-y-1.5">
        {flow.nodes.map((node) => {
          const expanded = open === node.index;
          return (
            <li key={node.index} data-testid={`flow-node-${node.index}`}>
              <button
                type="button"
                onClick={() => setOpen(expanded ? null : node.index)}
                aria-expanded={expanded}
                className="flex w-full cursor-pointer items-center gap-2 rounded-lg bg-white/70 px-2.5 py-1.5 text-left transition-colors hover:bg-white"
              >
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/12 text-[11px] font-semibold text-primary">
                  {node.index + 1}
                </span>
                <span className="text-sm font-medium text-ink">{node.title}</span>
                <code className="rounded bg-primary-cyan/10 px-1.5 py-0.5 text-[10px] text-primary-cyan">
                  {node.method}
                </code>
                {node.depends_on.length > 0 && (
                  <span className="inline-flex items-center gap-0.5 text-[10px] text-ink-muted">
                    <GitBranch className="h-3 w-3" />
                    依赖 {node.depends_on.map((dep) => dep + 1).join("、")}
                  </span>
                )}
                <span className="ml-auto text-[10px] text-ink-faint">
                  {expanded ? "收起" : "详情"}
                </span>
              </button>
              {expanded && (
                <div className="mt-1 space-y-1 rounded-lg bg-surface-page px-3 py-2 text-[11px] leading-relaxed text-ink-muted">
                  <p>目标列：{node.target_columns.join("、") || "—"}</p>
                  <p>
                    参数：
                    {Object.keys(node.params).length
                      ? Object.entries(node.params)
                          .map(([key, value]) => `${key}=${String(value)}`)
                          .join("；")
                      : "—"}
                  </p>
                  <p>图表：{node.chart_type === "none" ? "不出图" : node.chart_type}</p>
                  {node.rationale && <p>依据：{node.rationale}</p>}
                </div>
              )}
            </li>
          );
        })}
      </ol>

      <details className="mt-2">
        <summary className="cursor-pointer text-[10px] text-ink-faint">Mermaid 文本</summary>
        <pre className="mt-1 max-h-40 overflow-auto rounded bg-primary-dark/95 p-2 text-[10px] leading-relaxed text-primary-cyan">
          {flow.mermaid}
        </pre>
      </details>
    </div>
  );
}
