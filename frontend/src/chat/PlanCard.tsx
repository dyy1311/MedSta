import { useState } from "react";
import { CheckCircle2, ClipboardList, PenLine, Sparkles } from "lucide-react";
import PlanFlowView from "./PlanFlowView";
import type { EstimandSpec, PlanFlow, PlanOption, PlanStep } from "../types";

const METHOD_LABELS: Record<string, string> = {
  describe: "描述统计",
  missing_report: "缺失报告",
  normality_test: "正态性检验",
  group_compare: "两组比较",
  hypothesis_test: "两组比较",
  anova: "多组比较",
  chi_square: "卡方检验",
  correlation: "相关性",
  regression: "线性回归",
  logistic_regression: "Logistic 回归",
  timeseries_forecast: "趋势预测",
};

const ACTION_STYLE: Record<string, string> = {
  confirm: "bg-primary text-white hover:bg-primary-dark",
  revise: "border border-primary/40 text-primary hover:bg-primary/8",
  explain: "border border-ink/15 text-ink-muted hover:bg-ink/5",
  custom: "border border-dashed border-warn/50 text-warn hover:bg-warn/10",
  supplement: "border border-dashed border-warn/50 text-warn hover:bg-warn/10",
};

interface Props {
  message: string;
  steps: PlanStep[];
  options: PlanOption[];
  estimand?: EstimandSpec | null;
  sapStatus?: string;
  /** 047：工作流图（后端 plan_flow 产出；旧后端可能缺省） */
  flow?: PlanFlow | null;
  confirming: boolean;
  onOption: (optionId: string, content?: string) => void;
}

export default function PlanCard({
  message,
  steps,
  options,
  estimand = null,
  sapStatus = "exploratory",
  flow = null,
  confirming,
  onOption,
}: Props) {
  const [active, setActive] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const declared = sapStatus === "estimand_declared";
  const [showEstimand, setShowEstimand] = useState(!declared);
  const activeOption = options.find((option) => option.id === active);
  const factors = estimand
    ? [
        { label: "目标人群", value: estimand.population },
        { label: "结局变量", value: estimand.variable },
        { label: "处理与对照", value: estimand.treatment },
        { label: "汇总指标", value: estimand.summary_measure },
      ]
    : [];
  const missing = factors.filter((item) => !item.value.trim()).map((item) => item.label);

  return (
    <div className="animate-fade-in-up rounded-2xl border border-primary/15 bg-surface-card p-4 shadow-card">
      <div className="mb-3 flex items-center gap-2">
        <ClipboardList className="h-4 w-4 text-primary" />
        <span className="text-sm font-semibold text-primary-dark">分析方案</span>
      </div>
      <p className="mb-3 text-sm leading-relaxed text-ink">{message}</p>

      {flow ? <PlanFlowView flow={flow} /> : null}

      <div className="mb-3">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${
              declared ? "bg-primary/10 text-primary" : "bg-warn/12 text-warn"
            }`}
          >
            {declared ? "已声明估计目标" : "探索性分析"}
          </span>
          {estimand && (
            <button
              onClick={() => setShowEstimand((prev) => !prev)}
              className="cursor-pointer text-[11px] text-ink-muted hover:underline"
            >
              {showEstimand ? "收起估计目标" : "查看估计目标"}
            </button>
          )}
        </div>
        {showEstimand && (
          <div className="mt-2 rounded-lg bg-surface-page px-3 py-2 text-[11px] leading-relaxed">
            {estimand ? (
              <>
                <dl className="space-y-1">
                  {factors.map((item) => (
                    <div key={item.label} className="flex gap-2">
                      <dt className="w-16 shrink-0 text-ink-muted">{item.label}</dt>
                      <dd className={item.value.trim() ? "text-ink" : "text-warn"}>
                        {item.value.trim() || "未填写"}
                      </dd>
                    </div>
                  ))}
                  {estimand.intercurrent_events.length > 0 && (
                    <div className="flex gap-2">
                      <dt className="w-16 shrink-0 text-ink-muted">伴发事件</dt>
                      <dd className="text-ink">
                        {estimand.intercurrent_events
                          .map((item) => `${item.event || "未描述"}（${item.strategy}）`)
                          .join("；")}
                      </dd>
                    </div>
                  )}
                </dl>
                {!declared && missing.length > 0 && (
                  <p className="mt-1.5 text-warn">缺少要素：{missing.join("、")}</p>
                )}
              </>
            ) : (
              <p className="text-ink-muted">
                模型未给出估计目标，本次按探索性分析处理；可在下方补充说明后重新生成方案。
              </p>
            )}
          </div>
        )}
      </div>

      <ol className="mb-4 space-y-2">
        {steps.map((step, index) => (
          <li
            key={index}
            className="flex items-start gap-3 rounded-lg bg-surface-page px-3 py-2 text-sm"
          >
            <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
              {index + 1}
            </span>
            <span className="flex flex-wrap items-baseline gap-x-2">
              <span className="font-medium text-ink">{step.title}</span>
              <span className="rounded bg-primary-cyan/10 px-1.5 py-0.5 text-xs text-primary-cyan">
                {METHOD_LABELS[step.method] ?? step.method}
              </span>
              <span className="text-xs text-ink-muted">{step.target_columns.join(" / ")}</span>
              {step.chart_type !== "none" && (
                <span className="rounded bg-primary/8 px-1.5 py-0.5 text-xs text-primary">
                  {step.chart_type}
                </span>
              )}
            </span>
            {step.rationale ? (
              <details className="mt-1 w-full">
                <summary className="cursor-pointer text-[11px] text-primary">选择依据</summary>
                <p className="mt-1 rounded bg-surface-card/80 p-2 text-[11px] leading-relaxed text-ink-muted">
                  {step.rationale}
                </p>
              </details>
            ) : (
              // 依据缺失不是执行错误（宿主会先自动补一轮），但要让用户知道可以要求补充
              <span className="mt-1 text-[11px] text-warn">依据未提供（可让它补充说明）</span>
            )}
          </li>
        ))}
      </ol>

      <div className="flex flex-wrap gap-2">
        {options.map((option) => (
          <button
            key={option.id}
            disabled={confirming && option.action === "confirm"}
            onClick={() => {
              if (option.action === "custom" || option.action === "supplement") {
                setActive(active === option.id ? null : option.id);
                return;
              }
              onOption(option.id);
            }}
            className={`inline-flex min-h-11 cursor-pointer items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors duration-200 disabled:cursor-wait disabled:opacity-60 ${
              ACTION_STYLE[option.action] ?? ACTION_STYLE.explain
            }`}
          >
            {option.action === "confirm" ? (
              <CheckCircle2 className="h-4 w-4" />
            ) : option.action === "explain" ? (
              <Sparkles className="h-4 w-4" />
            ) : (
              <PenLine className="h-4 w-4" />
            )}
            {option.label}
          </button>
        ))}
      </div>

      {activeOption && (
        <div className="mt-2 flex gap-2">
          <input
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="补充你的分析要求，例如：按性别分层、改用非参数检验"
            className="min-w-0 flex-1 rounded-lg border border-ink/15 bg-surface-page px-3 py-2 text-sm outline-none transition-colors focus:border-primary"
          />
          <button
            onClick={() => {
              onOption(activeOption.id, note.trim());
              setNote("");
              setActive(null);
            }}
            disabled={!note.trim()}
            className="cursor-pointer rounded-lg bg-warn px-3 py-2 text-sm font-medium text-white transition-all hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-50"
          >
            发送
          </button>
        </div>
      )}
    </div>
  );
}
