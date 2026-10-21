import { useEffect, useRef, useState } from "react";
import { CircleStop, Play, SendHorizonal, Sparkles } from "lucide-react";
import type { ChatMessage, Phase } from "../types";
import PlanCard from "./PlanCard";
import ReviewCard from "./ReviewCard";
import UploadZone from "./UploadZone";
import ErrorCard from "./ErrorCard";

import AnalysisConfigCard from "./AnalysisConfigCard";
import PlotSuggestCard from "./PlotSuggestCard";
import TypeReviewCard from "./TypeReviewCard";
import type { PlotSuggestStep, TypeReviewRequest } from "../types";
import type { ChartConfigRequest } from "../types";

export interface Props {
  messages: ChatMessage[];
  uploaded: boolean;
  bindingName: string;
  confirming: boolean;
  sessionId: string;
  phase: Phase;
  streamText: string;
  progress: { step: number; total: number; title: string } | null;
  chartConfig: ChartConfigRequest | null;
  typeReview: TypeReviewRequest | null;
  plotSuggest: PlotSuggestStep[] | null;
  onTypeConfirm: (types: Record<string, string>) => void;
  onPlotLater: (stepIndex: number, chartType: string) => void;
  onChartChoice: (payload: {
    choices: { step_id: string; chart_type: string }[];
    layout: string;
    alpha: number;
    correction: string;
    use_default?: boolean;
  }) => void;
  onUpload: (file: File) => void;
  onSend: (content: string) => void;
  onConfirm: () => void;
  onAccept: () => void;
  onRevise: (note: string) => void;
  onOption: (optionId: string, content?: string) => void;
  onInterrupt: () => void;
  onResume: () => void;
  artifactBase: string;
}

export default function ChatPanel({
  messages,
  uploaded,
  bindingName,
  confirming,
  sessionId,
  phase,
  streamText,
  progress,
  onUpload,
  onSend,
  onAccept,
  onRevise,
  onOption,
  onInterrupt,
  onResume,
  chartConfig,
  typeReview,
  plotSuggest,
  onTypeConfirm,
  onPlotLater,
  onChartChoice,
  artifactBase,
}: Props) {
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const busy = phase === "thinking" || phase === "executing";

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamText, progress]);

  const submit = () => {
    const content = draft.trim();
    if (!content || busy) return;
    onSend(content);
    setDraft("");
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-ink/8 bg-primary/5 px-4 py-1.5 text-[11px] text-primary">
        当前会话绑定表格：<span className="font-medium">{bindingName}</span>
      </div>
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-5 py-4">
        {!uploaded && (
          <div className="animate-fade-in-up rounded-2xl bg-primary-dark px-4 py-3 text-sm text-white shadow-card">
            <div className="mb-1 flex items-center gap-2 font-semibold">
              <Sparkles className="h-4 w-4 text-primary-cyan" />
              欢迎使用 MedSta
            </div>
            <p className="leading-relaxed text-white/85">
              上传数据（CSV / Excel）后，我会解析画像；用自然语言说明分析目标，
              我们讨论出方案并确认执行，最终交付图表与解释。
            </p>
          </div>
        )}

        {!uploaded && <UploadZone uploaded={uploaded} onUpload={onUpload} />}

        {messages.map((message, index) => {
          if (message.role === "user") {
            return (
              <div key={index} className="flex justify-end">
                <div className="animate-fade-in-up max-w-[80%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm leading-relaxed text-white shadow-card">
                  {message.content}
                </div>
              </div>
            );
          }
          if (message.kind === "error") {
            return <ErrorCard key={index} {...message} />;
          }
          if (message.kind === "thinking") {
            return <ThinkingCard key={index} content={message.content} />;
          }
          if (message.kind === "notice") {
            return (
              <div
                key={index}
                className="animate-fade-in-up rounded-xl bg-surface-card px-3 py-2 text-sm text-ink-muted shadow-card"
              >
                {message.content}
              </div>
            );
          }
          if (message.kind === "plan") {
            return (
              <PlanCard
                key={index}
                message={message.message}
                steps={message.steps}
                options={message.options ?? []}
                confirming={confirming}
                onOption={onOption}
              />
            );
          }
          return (
            <ReviewCard
              key={index}
              report={message.report}
              delivered={message.delivered}
              sessionId={sessionId}
              artifactBase={artifactBase}
              onAccept={onAccept}
              onRevise={onRevise}
            />
          );
        })}

        {typeReview && (
          <TypeReviewCard request={typeReview} submitting={phase === "thinking"} onConfirm={onTypeConfirm} />
        )}

        {plotSuggest && plotSuggest.length > 0 && (
          <PlotSuggestCard steps={plotSuggest} submitting={false} onPlotLater={onPlotLater} />
        )}

        {chartConfig && (
          <AnalysisConfigCard config={chartConfig} submitting={confirming} onConfirm={onChartChoice} />
        )}

        {streamText && (
          <div className="animate-fade-in-up rounded-2xl border border-primary/15 bg-surface-card px-4 py-3 text-sm leading-relaxed text-ink shadow-card">
            <div className="mb-1 flex items-center gap-2 text-xs text-primary">
              <span className="h-1.5 w-1.5 animate-breathe rounded-full bg-primary-cyan" />
              正在思考
            </div>
            <p className="whitespace-pre-wrap">{streamText}</p>
          </div>
        )}

        {phase === "thinking" && !streamText && (
          <div className="animate-fade-in-up flex items-center gap-2 rounded-xl bg-surface-card px-3 py-2 text-sm text-ink-muted shadow-card">
            <span className="h-2 w-2 animate-breathe rounded-full bg-primary-cyan" />
            正在结合数据画像生成方案…
          </div>
        )}

        {phase === "executing" && (
          <div className="animate-fade-in-up rounded-xl bg-surface-card px-3 py-2.5 shadow-card">
            <div className="mb-1.5 flex items-center justify-between text-xs text-ink-muted">
              <span>{progress ? `执行中：${progress.title}` : "正在执行方案…"}</span>
              {progress && (
                <span className="font-mono">
                  {progress.step}/{progress.total}
                </span>
              )}
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-ink/8">
              <div
                className="h-full rounded-full bg-gradient-to-r from-primary to-primary-cyan transition-all duration-500"
                style={{
                  width: progress
                    ? `${Math.round(((progress.step - 1) / Math.max(progress.total, 1)) * 100)}%`
                    : "12%",
                }}
              />
            </div>
          </div>
        )}

        {phase === "interrupted" && (
          <div className="animate-fade-in-up flex flex-wrap items-center gap-2 rounded-xl border border-warn/30 bg-warn/5 px-3 py-2 text-sm text-ink">
            <span>已中断当前任务。</span>
            <button
              onClick={onResume}
              className="inline-flex cursor-pointer items-center gap-1 rounded-lg bg-primary px-2.5 py-1 text-xs font-medium text-white transition-all hover:bg-primary-dark"
            >
              <Play className="h-3 w-3" />
              继续
            </button>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="border-t border-ink/8 bg-surface-card px-4 py-3">
        <div className="flex gap-2">
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.nativeEvent.isComposing) submit();
            }}
            placeholder={
              uploaded
                ? "描述分析目标，或对方案提出修正意见…"
                : "请先上传数据…"
            }
            disabled={!uploaded || busy}
            className="min-w-0 flex-1 rounded-xl border border-ink/15 bg-surface-page px-4 py-2.5 text-sm outline-none transition-colors focus:border-primary disabled:cursor-not-allowed disabled:opacity-60"
          />
          {busy ? (
            <button
              onClick={onInterrupt}
              className="inline-flex cursor-pointer items-center gap-1.5 rounded-xl border border-danger/40 bg-danger/8 px-4 py-2.5 text-sm font-medium text-danger transition-all hover:bg-danger/15 active:scale-[0.98]"
            >
              <CircleStop className="h-4 w-4 animate-breathe" />
              中断
            </button>
          ) : (
            <button
              onClick={submit}
              disabled={!uploaded || !draft.trim()}
              className="inline-flex cursor-pointer items-center gap-1.5 rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-white transition-all hover:bg-primary-dark active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <SendHorizonal className="h-4 w-4" />
              发送
            </button>
          )}
        </div>
      </div>
    </div>
  );
}


function ThinkingCard({ content }: { content: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="animate-fade-in-up rounded-xl border border-primary/10 bg-surface-card px-3 py-2 text-sm shadow-card">
      <button
        onClick={() => setOpen((prev) => !prev)}
        className="flex w-full cursor-pointer items-center gap-2 text-xs text-ink-muted"
      >
        <span className="h-1.5 w-1.5 rounded-full bg-primary-cyan" />
        思考过程 · {content.length} 字
        <span className="ml-auto text-primary">{open ? "收起" : "展开"}</span>
      </button>
      {open && <p className="mt-2 whitespace-pre-wrap leading-relaxed text-ink">{content}</p>}
    </div>
  );
}
