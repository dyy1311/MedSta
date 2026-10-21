import { useEffect, useState } from "react";
import { BookOpen, Boxes, X } from "lucide-react";
import type { Capabilities } from "../types";
import { fetchCapabilities } from "../api/client";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function CapabilityDrawer({ open, onClose }: Props) {
  const [data, setData] = useState<Capabilities | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!open || data) return;
    fetchCapabilities()
      .then(setData)
      .catch((error) => {
        console.error("加载能力目录失败", error);
        setFailed(true);
      });
  }, [open, data]);

  if (!open) return null;
  const groups = data
    ? Array.from(new Set(data.tools.map((tool) => tool.category)))
    : [];

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-primary-dark/40 backdrop-blur-sm">
      <div className="h-full w-full max-w-md animate-fade-in-up overflow-y-auto bg-surface-card p-5 shadow-2xl">
        <div className="mb-4 flex items-center gap-2">
          <Boxes className="h-5 w-5 text-primary" />
          <h2 className="text-base font-semibold text-primary-dark">统计能力披露</h2>
          <button
            onClick={onClose}
            aria-label="关闭能力抽屉"
            className="ml-auto cursor-pointer rounded-lg p-1.5 text-ink-muted transition-colors hover:bg-surface-page hover:text-ink"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {failed && (
          <p className="rounded-lg bg-danger/5 p-3 text-sm text-danger">
            能力目录加载失败，请确认后端已启动。
          </p>
        )}

        {data && (
          <>
            <p className="mb-4 rounded-lg bg-surface-page p-3 text-xs leading-relaxed text-ink-muted">
              {data.methodology}。执行由确定性 pipeline 完成，模型只负责选择方法与参数。
            </p>
            {groups.map((group) => (
              <section key={group} className="mb-4">
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                  {group}
                </h3>
                <div className="space-y-2">
                  {data.tools
                    .filter((tool) => tool.category === group)
                    .map((tool) => (
                      <article
                        key={tool.name}
                        className="rounded-xl border border-ink/8 bg-surface-page/60 p-3"
                      >
                        <div className="flex items-baseline gap-2">
                          <span className="text-sm font-medium text-ink">{tool.title}</span>
                          <span className="font-mono text-[11px] text-ink-muted">
                            {tool.name}
                          </span>
                        </div>
                        <p className="mt-1 text-xs leading-relaxed text-ink-muted">
                          {tool.description}
                        </p>
                        {tool.applicability && (
                          <p className="mt-1 rounded bg-primary/5 p-1.5 text-[11px] leading-relaxed text-primary">
                            适用条件：{tool.applicability}
                          </p>
                        )}
                        <div className="mt-2 flex flex-wrap gap-1">
                          {tool.params
                            .filter((param) => param.required)
                            .map((param) => (
                              <span
                                key={param.name}
                                className="rounded bg-danger/8 px-1.5 py-0.5 text-[11px] text-danger"
                              >
                                必填 {param.name}
                              </span>
                            ))}
                          {tool.charts.map((chart) => (
                            <span
                              key={chart}
                              className="rounded bg-primary/8 px-1.5 py-0.5 text-[11px] text-primary"
                            >
                              {chart}
                            </span>
                          ))}
                        </div>
                      </article>
                    ))}
                </div>
              </section>
            ))}

            <section className="mb-4">
              <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                <BookOpen className="h-3.5 w-3.5" /> 规划中（暂不可执行）
              </h3>
              <ul className="space-y-1.5">
                {data.planned.map((item) => (
                  <li key={item.name} className="rounded-lg bg-warn/5 p-2.5 text-xs">
                    <span className="font-medium text-warn">{item.title}</span>
                    <p className="mt-0.5 leading-relaxed text-ink-muted">{item.description}</p>
                  </li>
                ))}
              </ul>
            </section>
          </>
        )}
      </div>
    </div>
  );
}
