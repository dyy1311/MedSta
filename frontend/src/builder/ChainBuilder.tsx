import { useEffect, useMemo, useState } from "react";
import { ArrowDown, ArrowUp, FlaskConical, ListPlus, Play, Trash2, Upload } from "lucide-react";

export interface ChainStep {
  method: string;
  title: string;
  target_columns: string[];
  chart_type: string;
  params: Record<string, unknown>;
}

interface ToolParamSpec {
  name: string;
  type: string;
  required: boolean;
  description: string;
  choices: string[];
  default: unknown;
}

interface ToolSpecView {
  name: string;
  title: string;
  category: string;
  description: string;
  task: string;
  applicability: string;
  params: ToolParamSpec[];
  charts: string[];
  /** 工具可接受的目标列类型（037 置灰依据） */
  accepts?: string[];
}

interface TemplateView {
  name: string;
  steps: ChainStep[];
}

interface Props {
  sessionId: string;
  columns: string[];
  /** 列名 → 画像类型（快捷勾选按列类型批量选择） */
  columnTypes?: Record<string, string>;
  busy: boolean;
  importSteps: ChainStep[] | null;
  onRun: (steps: ChainStep[]) => void;
}

export default function ChainBuilder({
  columns,
  columnTypes = {},
  busy,
  importSteps,
  onRun,
}: Props) {
  const [tools, setTools] = useState<ToolSpecView[]>([]);
  const [selected, setSelected] = useState("");
  const [targets, setTargets] = useState<string[]>([]);
  const [chart, setChart] = useState<string>("none");
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [chain, setChain] = useState<ChainStep[]>([]);
  const [templates, setTemplates] = useState<TemplateView[]>([]);
  const [tplName, setTplName] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetch("/capabilities")
      .then((resp) => (resp.ok ? resp.json() : Promise.reject(new Error(String(resp.status)))))
      .then((payload: { tools: ToolSpecView[] }) => {
        if (!cancelled) setTools(payload.tools ?? []);
      })
      .catch(() => undefined); // 目录加载失败仅影响装配，不影响既有会话
    fetch("/templates")
      .then((resp) => (resp.ok ? resp.json() : Promise.reject(new Error(String(resp.status)))))
      .then((payload: { templates: TemplateView[] }) => {
        if (!cancelled) setTemplates(payload.templates ?? []);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const tool = useMemo(() => tools.find((t) => t.name === selected) ?? null, [tools, selected]);
  /** 037 置灰：数据列类型与工具 accepts 完全不相交时禁选（提示而非隐藏） */
  const dataTypes = useMemo(
    () =>
      new Set(
        columns
          .map((name) => columnTypes[name] ?? "")
          .filter(Boolean)
      ),
    [columns, columnTypes]
  );
  const isInapplicable = (item: ToolSpecView): boolean => {
    if (!item.accepts || item.accepts.length === 0 || dataTypes.size === 0) return false;
    return !item.accepts.some((type) => dataTypes.has(type));
  };
  const categories = useMemo(() => {
    const grouped = new Map<string, ToolSpecView[]>();
    for (const item of tools) {
      grouped.set(item.category, [...(grouped.get(item.category) ?? []), item]);
    }
    return [...grouped.entries()];
  }, [tools]);

  const resetDraft = (next: ToolSpecView | null) => {
    setTargets([]);
    setChart("none");
    const initial: Record<string, unknown> = {};
    for (const param of next?.params ?? []) {
      if (param.default !== null && param.default !== undefined) initial[param.name] = param.default;
    }
    setDraft(initial);
  };

  const selectTool = (name: string) => {
    setSelected(name);
    resetDraft(tools.find((t) => t.name === name) ?? null);
  };

  const addStep = () => {
    if (!tool) return;
    setChain((prev) => [
      ...prev,
      {
        method: tool.name,
        title: tool.title,
        target_columns: [...targets],
        chart_type: chart,
        params: { ...draft },
      },
    ]);
    resetDraft(tool);
  };

  const move = (index: number, delta: number) => {
    setChain((prev) => {
      const next = [...prev];
      const target = index + delta;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };

  const remove = (index: number) => {
    setChain((prev) => prev.filter((_, i) => i !== index));
  };

  const run = () => {
    if (busy || chain.length === 0) return;
    onRun(
      chain.map((step, index) => ({
        ...step,
        title: step.title || `步骤 ${index + 1}`,
      })),
    );
  };

  const importPlan = () => {
    if (importSteps && importSteps.length > 0) setChain(importSteps);
  };

  const toggleTarget = (column: string) => {
    setTargets((prev) =>
      prev.includes(column) ? prev.filter((c) => c !== column) : [...prev, column]
    );
  };

  const selectByTypes = (typeSet: Set<string>) => {
    setTargets(columns.filter((name) => typeSet.has(columnTypes[name] ?? "")));
  };

  const refreshTemplates = () => {
    fetch("/templates")
      .then((resp) => (resp.ok ? resp.json() : Promise.reject(new Error(String(resp.status)))))
      .then((payload: { templates: TemplateView[] }) => setTemplates(payload.templates ?? []))
      .catch(() => undefined);
  };

  const saveTemplate = async () => {
    const name = tplName.trim();
    if (!name || chain.length === 0) return;
    try {
      const resp = await fetch(`/templates/${encodeURIComponent(name)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ steps: chain }),
      });
      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({ detail: resp.statusText }));
        setNotice(`保存失败：${String((detail as Record<string, unknown>).detail ?? resp.status)}`);
        return;
      }
      setNotice(`已保存「${name}」`);
      setTplName("");
      refreshTemplates();
    } catch {
      setNotice("保存失败：网络异常");
    }
  };

  const loadTemplate = (template: TemplateView) => {
    setChain(
      template.steps.map((step) => ({
        method: String(step.method),
        title: String(step.title ?? step.method),
        target_columns: Array.isArray(step.target_columns)
          ? step.target_columns.map(String)
          : [],
        chart_type: String(step.chart_type ?? "none"),
        params: typeof step.params === "object" && step.params !== null ? { ...step.params } : {},
      }))
    );
    setNotice(`已载入「${template.name}」`);
  };

  const removeTemplate = async (name: string) => {
    try {
      await fetch(`/templates/${encodeURIComponent(name)}`, { method: "DELETE" });
      refreshTemplates();
    } catch {
      setNotice("删除失败：网络异常");
    }
  };

  /** 037 模板导入：读取 JSON 文件（FileReader 兼容 jsdom；重名由 notice 提示） */
  const importTemplateFile = async (file: File) => {
    const readAsText = () =>
      new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = () => reject(reader.error);
        reader.readAsText(file);
      });
    try {
      const payload = JSON.parse(await readAsText()) as {
        name?: string;
        steps?: ChainStep[];
      };
      if (!payload.name || !Array.isArray(payload.steps) || payload.steps.length === 0) {
        setNotice("导入失败：文件需含 name 与非空 steps");
        return;
      }
      const resp = await fetch("/templates/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: payload.name, steps: payload.steps }),
      });
      if (resp.status === 409) {
        setNotice(`模板「${payload.name}」已存在；如需覆盖请先删除原模板`);
        return;
      }
      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({ detail: resp.statusText }));
        setNotice(`导入失败：${String((detail as Record<string, unknown>).detail ?? resp.status)}`);
        return;
      }
      setNotice(`已导入「${payload.name}」`);
      refreshTemplates();
    } catch {
      setNotice("导入失败：文件不是合法 JSON");
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto p-4">
      <div className="flex items-center gap-2">
        <FlaskConical className="h-4 w-4 text-primary" />
        <span className="text-sm font-semibold text-primary-dark">工具装配</span>
        <span className="text-xs text-ink-muted">选择原子统计工具，装配你的工作链</span>
      </div>

      <section className="rounded-2xl bg-surface-card p-3 shadow-card">
        <div className="mb-2 flex items-center gap-2">
          <label className="text-xs font-medium text-ink" htmlFor="tool-select">
            统计工具
          </label>
          <select
            id="tool-select"
            aria-label="统计工具"
            className="ml-auto rounded-lg border border-ink/10 bg-white px-2 py-1 text-xs"
            value={selected}
            onChange={(e) => selectTool(e.target.value)}
          >
            <option value="">选择工具…</option>
            {categories.map(([category, items]) => (
              <optgroup key={category} label={category}>
                {items.map((item) => {
                  const inapplicable = isInapplicable(item);
                  return (
                    <option
                      key={item.name}
                      value={item.name}
                      disabled={inapplicable}
                      title={
                        inapplicable
                          ? `类型不适用：数据列为 [${[...dataTypes].join("、")}]，需要 [${item.accepts?.join("、")}]`
                          : undefined
                      }
                    >
                      {item.title}
                      {inapplicable ? "（类型不适用）" : ""}
                    </option>
                  );
                })}
              </optgroup>
            ))}
          </select>
        </div>

        {tool && (
          <div className="space-y-3 border-t border-ink/8 pt-3">
            <p className="text-xs text-ink-muted">{tool.description}</p>
            {tool.applicability && (
              <p className="text-xs text-primary-dark">适用：{tool.applicability}</p>
            )}

            <fieldset>
              <legend className="mb-1 text-xs font-medium text-ink">目标列</legend>
              <div className="mb-1.5 flex flex-wrap gap-1.5">
                <button
                  type="button"
                  onClick={() => selectByTypes(new Set(["continuous", "ordinal"]))}
                  className="cursor-pointer rounded-md border border-primary/30 px-2 py-0.5 text-[11px] text-primary hover:bg-primary/5"
                >
                  全部数值列
                </button>
                <button
                  type="button"
                  onClick={() =>
                    selectByTypes(new Set(["categorical", "text", "boolean"]))
                  }
                  className="cursor-pointer rounded-md border border-primary/30 px-2 py-0.5 text-[11px] text-primary hover:bg-primary/5"
                >
                  全部类别列
                </button>
                <button
                  type="button"
                  onClick={() => setTargets(columns)}
                  className="cursor-pointer rounded-md border border-ink/20 px-2 py-0.5 text-[11px] text-ink-muted hover:bg-surface-page"
                >
                  全选
                </button>
                <button
                  type="button"
                  onClick={() => setTargets([])}
                  className="cursor-pointer rounded-md border border-ink/20 px-2 py-0.5 text-[11px] text-ink-muted hover:bg-surface-page"
                >
                  清空
                </button>
              </div>
              <div className="flex flex-wrap gap-3">
                {columns.map((column) => (
                  <label key={column} className="flex items-center gap-1 text-xs text-ink">
                    <input
                      type="checkbox"
                      aria-label={column}
                      checked={targets.includes(column)}
                      onChange={() => toggleTarget(column)}
                    />
                    {column}
                  </label>
                ))}
              </div>
            </fieldset>

            {tool.params.map((param) => (
              <div key={param.name} className="flex items-center gap-2">
                {param.type === "boolean" ? (
                  <label className="flex items-center gap-1 text-xs text-ink">
                    <input
                      type="checkbox"
                      aria-label={param.name}
                      checked={Boolean(draft[param.name])}
                      onChange={(e) =>
                        setDraft((prev) => ({ ...prev, [param.name]: e.target.checked }))
                      }
                    />
                    {param.name}
                  </label>
                ) : (
                  <>
                    <label
                      className="w-40 shrink-0 text-xs text-ink"
                      htmlFor={`param-${param.name}`}
                    >
                      {param.name}
                      {param.required ? "（必填）" : ""}
                    </label>
                    {param.type === "choice" ? (
                      <select
                        id={`param-${param.name}`}
                        aria-label={`${param.name}${param.required ? "（必填）" : ""}`}
                        className="flex-1 rounded-lg border border-ink/10 bg-white px-2 py-1 text-xs"
                        value={String(draft[param.name] ?? "")}
                        onChange={(e) =>
                          setDraft((prev) => ({ ...prev, [param.name]: e.target.value }))
                        }
                      >
                        <option value="">选择…</option>
                        {param.choices.map((choice) => (
                          <option key={choice} value={choice}>
                            {choice}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        id={`param-${param.name}`}
                        aria-label={`${param.name}${param.required ? "（必填）" : ""}`}
                        type={param.type === "integer" ? "number" : "text"}
                        className="flex-1 rounded-lg border border-ink/10 bg-white px-2 py-1 text-xs"
                        value={String(draft[param.name] ?? "")}
                        onChange={(e) =>
                          setDraft((prev) => ({
                            ...prev,
                            [param.name]:
                              param.type === "integer" ? Number(e.target.value) : e.target.value,
                          }))
                        }
                      />
                    )}
                  </>
                )}
              </div>
            ))}

            <div className="flex items-center gap-2">
              <label className="text-xs font-medium text-ink" htmlFor="chart-select">
                图表
              </label>
              <select
                id="chart-select"
                aria-label="图表"
                className="rounded-lg border border-ink/10 bg-white px-2 py-1 text-xs"
                value={chart}
                onChange={(e) => setChart(e.target.value)}
              >
                <option value="none">不出图</option>
                {tool.charts
                  .filter((c) => c !== "none")
                  .map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
              </select>
              <button
                type="button"
                onClick={addStep}
                disabled={!selected}
                className="ml-auto flex items-center gap-1 rounded-lg bg-primary px-3 py-1 text-xs text-white disabled:opacity-40"
              >
                <ListPlus className="h-3.5 w-3.5" />
                添加到工作链
              </button>
            </div>
          </div>
        )}
      </section>

      <section className="rounded-2xl bg-surface-card p-3 shadow-card">
        <div className="mb-2 flex items-center gap-2">
          <span className="text-sm font-semibold text-primary-dark">
            工作链（{chain.length}）
          </span>
          {importSteps && importSteps.length > 0 && (
            <button
              type="button"
              onClick={importPlan}
              className="ml-auto flex items-center gap-1 rounded-lg border border-primary px-2 py-0.5 text-xs text-primary"
            >
              <Upload className="h-3 w-3" />
              导入最新方案
            </button>
          )}
        </div>
        {chain.length === 0 ? (
          <p className="text-xs text-ink-muted">尚未装配步骤。选择工具并添加，或导入模型建议。</p>
        ) : (
          <ol className="space-y-2">
            {chain.map((step, index) => (
              <li
                key={`${step.method}-${index}`}
                data-testid={`chain-step-${index}`}
                className="flex items-center gap-2 rounded-xl border border-ink/8 px-3 py-2 text-xs"
              >
                <span className="font-medium text-ink">{index + 1}. {step.title}</span>
                <span className="text-ink-muted">
                  {step.target_columns.join("、") || "—"} · {step.chart_type === "none" ? "不出图" : step.chart_type}
                </span>
                <span className="ml-auto flex items-center gap-1">
                  <button
                    type="button"
                    aria-label={`上移 ${step.title}`}
                    data-testid={`chain-up-${index}`}
                    disabled={index === 0}
                    onClick={() => move(index, -1)}
                    className="p-1 disabled:opacity-30"
                  >
                    <ArrowUp className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    aria-label={`下移 ${step.title}`}
                    data-testid={`chain-down-${index}`}
                    disabled={index === chain.length - 1}
                    onClick={() => move(index, 1)}
                    className="p-1 disabled:opacity-30"
                  >
                    <ArrowDown className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    aria-label={`删除 ${step.title}`}
                    data-testid={`chain-remove-${index}`}
                    onClick={() => remove(index)}
                    className="p-1 text-red-500"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </span>
              </li>
            ))}
          </ol>
        )}
        {chain.some((step) => step.method === "impute") && (
          <p
            data-testid="pipeline-hint"
            className="mt-2 rounded-lg bg-primary/5 px-2.5 py-1.5 text-[11px] text-primary-dark"
          >
            后续步骤将使用插补数据（链间管道：插补后的数据集自动作为后续步骤的输入）
          </p>
        )}
        <button
          type="button"
          onClick={run}
          disabled={busy || chain.length === 0}
          className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          <Play className="h-4 w-4" />
          执行工作链
        </button>
      </section>

      <section className="rounded-2xl bg-surface-card p-3 shadow-card">
        <div className="mb-2 flex items-center gap-2">
          <span className="text-sm font-semibold text-primary-dark">我的工作链</span>
          <span className="text-xs text-ink-muted">保存当前装配，跨会话复用</span>
        </div>
        <div className="flex items-center gap-2">
          <input
            value={tplName}
            onChange={(event) => setTplName(event.target.value)}
            placeholder="模板名称"
            className="min-w-0 flex-1 rounded-lg border border-ink/15 bg-white px-2 py-1 text-xs"
          />
          <button
            type="button"
            onClick={() => void saveTemplate()}
            disabled={!tplName.trim() || chain.length === 0}
            className="shrink-0 cursor-pointer rounded-lg border border-primary px-2.5 py-1 text-xs font-medium text-primary transition-colors hover:bg-primary/5 disabled:cursor-not-allowed disabled:opacity-40"
          >
            保存模板
          </button>
        </div>
        {notice && (
          <p className="mt-1.5 text-[11px] text-primary" data-testid="tpl-notice">
            {notice}
          </p>
        )}
        {templates.length === 0 ? (
          <p className="mt-2 text-xs text-ink-muted">暂无已保存的工作链。</p>
        ) : (
          <ul className="mt-2 space-y-1.5">
            {templates.map((template) => (
              <li
                key={template.name}
                className="flex items-center gap-2 rounded-xl border border-ink/8 px-3 py-1.5 text-xs"
              >
                <span className="font-medium text-ink">{template.name}</span>
                <span className="text-ink-faint">
                  {Array.isArray(template.steps) ? `${template.steps.length} 步` : ""}
                </span>
                <span className="ml-auto flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => loadTemplate(template)}
                    className="cursor-pointer rounded-md border border-primary/40 px-2 py-0.5 text-primary transition-colors hover:bg-primary/5"
                  >
                    载入
                  </button>
                  <a
                    href={`/templates/${encodeURIComponent(template.name)}/export`}
                    aria-label={`导出 ${template.name}`}
                    className="cursor-pointer rounded-md border border-primary/40 px-2 py-0.5 text-primary transition-colors hover:bg-primary/5"
                  >
                    导出
                  </a>
                  <button
                    type="button"
                    aria-label={`删除 ${template.name}`}
                    onClick={() => void removeTemplate(template.name)}
                    className="cursor-pointer rounded-md border border-ink/15 px-2 py-0.5 text-ink-muted transition-colors hover:border-danger/40 hover:text-danger"
                  >
                    删除
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}
        <label className="mt-2 flex w-fit cursor-pointer items-center gap-1.5 rounded-md border border-dashed border-ink/20 px-2 py-1 text-[11px] text-ink-muted transition-colors hover:border-primary/40 hover:text-primary">
          导入模板文件…
          <input
            data-testid="import-template-input"
            type="file"
            accept="application/json,.json"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void importTemplateFile(file);
              event.target.value = "";
            }}
          />
        </label>
      </section>
    </div>
  );
}
