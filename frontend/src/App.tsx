import { useCallback, useEffect, useRef, useState } from "react";
import { BarChart3, Boxes, MessagesSquare } from "lucide-react";
import type {
  ChartConfigRequest, ChatMessage, ExecutionReport, Phase, PlotSuggestStep,
  TableProfile, TypeReviewRequest, WsEvent, WorkspaceTab,
} from "./types";
import { connectSession, createSession, updateColumnType, uploadData } from "./api/client";
import type { SessionConnection } from "./api/client";
import ChatPanel from "./chat/ChatPanel";
import CapabilityDrawer from "./chat/CapabilityDrawer";
import SessionTabs from "./chat/SessionTabs";
import type { ChatSessionEntry } from "./chat/SessionTabs";
import WorkspacePanel from "./workspace/WorkspacePanel";

function upsertReport(reports: ExecutionReport[], report: ExecutionReport, replaceLast: boolean) {
  const next = [...reports];
  if (replaceLast && next.length > 0) next[next.length - 1] = report;
  else next.push(report);
  return next;
}

export default function App() {
  const [chatSessions, setChatSessions] = useState<ChatSessionEntry[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const activeChat = chatSessions.find((c) => c.sessionId === activeChatId) ?? null;
  const activeChatIdResolved = activeChat?.sessionId ?? null;
  const [bindingBanner, setBindingBanner] = useState<string | null>(null);
  // 事件回调需读取「事件所属会话」的绑定表，不能用可能过期的闭包状态
  const chatSessionsRef = useRef<ChatSessionEntry[]>([]);
  chatSessionsRef.current = chatSessions;

  const [workspaces, setWorkspaces] = useState<WorkspaceTab[]>([]);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<string | null>(null);
  const activeWorkspace =
    workspaces.find((w) => w.datasetId === activeChat?.datasetId) ??
    workspaces.find((w) => w.datasetId === activeWorkspaceId) ?? null;

  const [messagesBySession, setMessagesBySession] = useState<Record<string, ChatMessage[]>>({});
  const [phaseBySession, setPhaseBySession] = useState<Record<string, Phase>>({});
  const [chartConfig, setChartConfig] = useState<ChartConfigRequest | null>(null);
  const [typeReview, setTypeReview] = useState<TypeReviewRequest | null>(null);
  const [plotSuggest, setPlotSuggest] = useState<PlotSuggestStep[] | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [capabilitiesOpen, setCapabilitiesOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<"chat" | "workspace">("chat");
  const [uploading, setUploading] = useState(false);

  const messages = activeChatIdResolved ? messagesBySession[activeChatIdResolved] ?? [] : [];
  const phase = activeChatIdResolved ? phaseBySession[activeChatIdResolved] ?? "idle" : "idle";

  const connectionRef = useRef<SessionConnection | null>(null);
  const connSessionRef = useRef<string | null>(null);
  const streamTextRef = useRef<Record<string, string>>({});
  const progressRef = useRef<Record<string, { step: number; total: number; title: string } | null>>({});
  const [, forceRender] = useState(0);

  const pushMessage = useCallback((sid: string, message: ChatMessage) => {
    setMessagesBySession((prev) => ({ ...prev, [sid]: [...(prev[sid] ?? []), message] }));
  }, []);

  const setPhaseFor = useCallback((sid: string, value: Phase) => {
    setPhaseBySession((prev) => ({ ...prev, [sid]: value }));
  }, []);

  const handleEvent = useCallback((ownerSid: string, event: WsEvent) => {
    const isActive = ownerSid === activeChatIdResolved;
    const emit = (message: ChatMessage) => pushMessage(ownerSid, message);
    switch (event.type) {
      case "data_profile": {
        const datasetId = event.dataset_id ?? `ds-${Date.now()}`;
        const name = event.name ?? datasetId;
        setWorkspaces((prev) => {
          const existing = prev.find((w) => w.datasetId === datasetId);
          if (existing) {
            return prev.map((w) =>
              w.datasetId === datasetId ? { ...w, profile: event.profile, name } : w
            );
          }
          return [...prev, { datasetId, name, profile: event.profile, reports: [] }];
        });
        setChatSessions((prev) =>
          prev.map((c) => (c.sessionId === ownerSid && c.datasetId === null ? { ...c, datasetId, name } : c))
        );
        setActiveWorkspaceId(datasetId);
        if (isActive) {
          emit({
            role: "system", kind: "notice",
            content: `数据「${name}」已绑定当前会话：${event.profile.row_count} 行 × ${event.profile.column_count} 列。`,
          });
        }
        break;
      }
      case "type_review":
        setTypeReview(event);
        if (isActive) setPhaseFor(ownerSid, "idle");
        break;
      case "type_confirmed":
        setTypeReview(null);
        setWorkspaces((prev) =>
          prev.map((w) => (w.datasetId === (event.dataset_id ?? "") ? { ...w, profile: event.profile } : w))
        );
        if (isActive) emit({ role: "system", kind: "notice", content: "变量类型已敲定，继续讨论。" });
        break;
      case "plot_suggest":
        if (isActive) setPlotSuggest(event.steps);
        break;
      case "stream":
        streamTextRef.current[ownerSid] = (streamTextRef.current[ownerSid] ?? "") + event.delta;
        if (isActive) forceRender((n) => n + 1);
        break;
      case "progress":
        if (event.stage === "executing") {
          progressRef.current[ownerSid] = {
            step: event.step ?? 1, total: event.total ?? 1, title: event.title ?? "",
          };
          if (isActive) setPhaseFor(ownerSid, "executing");
        } else if (isActive) {
          setPhaseFor(ownerSid, "thinking");
        }
        if (isActive) forceRender((n) => n + 1);
        break;
      case "plan": {
        const thinking = streamTextRef.current[ownerSid] ?? "";
        streamTextRef.current[ownerSid] = "";
        if (thinking) emit({ role: "system", kind: "thinking", content: thinking });
        emit({ role: "system", kind: "plan", type: "plan", message: event.message,
               steps: event.steps, options: event.options });
        if (isActive) { setPhaseFor(ownerSid, "idle"); setConfirming(false); }
        break;
      }
      case "review_request": {
        const boundDatasetId =
          chatSessionsRef.current.find((c) => c.sessionId === ownerSid)?.datasetId ?? "";
        setWorkspaces((prev) =>
          prev.map((w) =>
            w.datasetId === boundDatasetId
              ? { ...w, reports: upsertReport(w.reports, event.report, !!event.updated) }
              : w
          )
        );
        if (isActive) {
          setPhaseFor(ownerSid, "idle");
          if (event.updated) {
            emit({ role: "system", kind: "notice", content: "补绘图完成，报告已更新。" });
          } else {
            emit({ role: "system", kind: "review", report: event.report, delivered: false });
          }
          forceRender((n) => n + 1);
        }
        break;
      }
      case "delivered": {
        // 交付后同步把审阅卡标记为已交付，避免按钮仍停留在「确认交付」
        setMessagesBySession((prev) => {
          const list = prev[ownerSid] ?? [];
          const lastIndex = list.map((item) => item.kind).lastIndexOf("review");
          const last = list[lastIndex];
          if (lastIndex < 0 || last?.kind !== "review") return prev;
          const next = [...list];
          next[lastIndex] = { ...last, delivered: true };
          return { ...prev, [ownerSid]: next };
        });
        if (isActive) setPhaseFor(ownerSid, "delivered");
        break;
      }
      case "back_to_discussion":
        if (isActive) {
          setPhaseFor(ownerSid, "idle");
          emit({ role: "system", kind: "notice", content: event.message });
        }
        break;
      case "interrupted":
        if (isActive) {
          setPhaseFor(ownerSid, "interrupted");
          streamTextRef.current[ownerSid] = "";
          setConfirming(false);
          setChartConfig(null);
          setPlotSuggest(null);
          emit({ role: "system", kind: "notice", content: event.message });
        }
        break;
      case "resumed":
        if (isActive) {
          setPhaseFor(ownerSid, "idle");
          if (event.message) emit({ role: "system", kind: "notice", content: event.message });
        }
        break;
      case "chart_config":
        if (isActive) {
          setPhaseFor(ownerSid, "chart_config");
          setConfirming(false);
          streamTextRef.current[ownerSid] = "";
          setChartConfig({
            steps: event.steps, multi_chart: event.multi_chart,
            alpha: event.alpha, correction: event.correction, message: event.message,
          });
        }
        break;
      case "error":
        if (isActive) {
          setPhaseFor(ownerSid, "idle");
          streamTextRef.current[ownerSid] = "";
          setConfirming(false);
          setChartConfig(null);
          setPlotSuggest(null);
        }
        emit({ role: "system", kind: "error", code: event.code, message: event.message,
               hint: event.hint, detail: event.detail });
        break;
    }
  }, [activeChatIdResolved, pushMessage, setPhaseFor]);

  const handlerRef = useRef(handleEvent);
  handlerRef.current = handleEvent;

  useEffect(() => {
    if (!activeChatIdResolved) return;
    if (connSessionRef.current === activeChatIdResolved) return;
    connectionRef.current?.close();
    const sid = activeChatIdResolved;
    connSessionRef.current = sid;
    connectionRef.current = connectSession(sid, (event) => handlerRef.current(sid, event));
    return () => {
      if (connSessionRef.current === sid) {
        connectionRef.current?.close();
        connectionRef.current = null;
        connSessionRef.current = null;
      }
    };
  }, [activeChatIdResolved]);

  const createChatSession = useCallback(async (name = "未绑定") => {
    const { session_id } = await createSession();
    setChatSessions((prev) => [...prev, { sessionId: session_id, datasetId: null, name }]);
    setActiveChatId(session_id);
    setBindingBanner(`新会话已创建，当前绑定表格：${name}`);
    setTimeout(() => setBindingBanner(null), 4000);
    return session_id;
  }, []);

  const handleUpload = async (file: File, targetSessionId?: string) => {
    let sid = targetSessionId ?? activeChatIdResolved;
    if (!sid || chatSessions.find((c) => c.sessionId === sid)?.datasetId) {
      sid = await createChatSession(file.name);
    }
    setUploading(true);
    try {
      const result = await uploadData(sid, file);
      handleEvent(sid, {
        type: "data_profile",
        dataset_id: result.dataset_id,
        name: file.name,
        profile: result.profile as TableProfile,
      });
    } catch (error) {
      // 上传失败必须可见：走统一错误卡，避免只写 console 后界面无反馈
      const detail = error instanceof Error ? error.message : String(error);
      handleEvent(sid, {
        type: "error",
        code: "UPLOAD_FAILED",
        message: `上传失败：${detail}`,
        hint: "确认文件为 CSV / Excel（.csv/.xlsx/.xls），表头完整且非空",
      });
    } finally {
      setUploading(false);
    }
  };

  const handleSetColumnType = (column: string, type: string) => {
    const datasetId = activeChat?.datasetId;
    if (!datasetId || !activeChatIdResolved) return;
    updateColumnType(activeChatIdResolved, datasetId, column, type)
      .then((result: { profile: TableProfile }) => {
        setWorkspaces((prev) =>
          prev.map((w) => (w.datasetId === datasetId ? { ...w, profile: result.profile } : w))
        );
      })
      .catch((error: unknown) => console.error("type edit failed", error));
  };

  const sendWs = (event: Record<string, unknown>) => {
    if (connSessionRef.current === activeChatIdResolved) {
      connectionRef.current?.send(event);
    } else {
      console.error("连接与会话不匹配，消息未发送");
    }
  };

  const handleSend = (content: string) => {
    if (!activeChatIdResolved) return;
    pushMessage(activeChatIdResolved, { role: "user", kind: "text", content });
    setPhaseFor(activeChatIdResolved, "thinking");
    streamTextRef.current[activeChatIdResolved] = "";
    sendWs({ type: "chat", content });
  };

  const handleConfirm = () => {
    setConfirming(true);
    if (activeChatIdResolved) setPhaseFor(activeChatIdResolved, "executing");
    sendWs({ type: "confirm_plan" });
  };

  const handleChartChoice = (payload: {
    choices: { step_id: string; chart_type: string }[];
    layout: string;
    alpha: number;
    correction: string;
    use_default?: boolean;
  }) => {
    setConfirming(true);
    if (activeChatIdResolved) setPhaseFor(activeChatIdResolved, "executing");
    setChartConfig(null);
    sendWs({ type: "chart_choice", ...payload });
  };

  const handleOption = (optionId: string, content?: string) => {
    if (!activeChatIdResolved) return;
    const planMessages = messages.filter((m) => m.kind === "plan");
    const latestPlan = planMessages[planMessages.length - 1];
    const option = latestPlan?.options?.find((item) => item.id === optionId);
    if (content) {
      pushMessage(activeChatIdResolved, { role: "user", kind: "text", content });
    } else if (option) {
      pushMessage(activeChatIdResolved, { role: "user", kind: "text", content: option.label });
    }
    if (option?.action === "confirm") {
      setConfirming(true);
    } else {
      setPhaseFor(activeChatIdResolved, "thinking");
    }
    sendWs({ type: "option", option_id: optionId, content });
  };

  const handleAccept = () => sendWs({ type: "review", decision: "accept" });
  const handleRevise = (note: string) => {
    if (!activeChatIdResolved) return;
    pushMessage(activeChatIdResolved, { role: "user", kind: "text", content: `修正意见：${note}` });
    sendWs({ type: "review", decision: "revise", content: note });
  };
  const handleInterrupt = () => sendWs({ type: "interrupt" });
  const handleResume = () => sendWs({ type: "resume" });
  const handleTypeConfirm = (types: Record<string, string>) => {
    if (!activeChatIdResolved) return;
    setPhaseFor(activeChatIdResolved, "thinking");
    sendWs({ type: "type_confirm", types });
  };
  const handlePlotLater = (stepIndex: number, chartType: string) => {
    setPlotSuggest(null);
    if (activeChatIdResolved) setPhaseFor(activeChatIdResolved, "executing");
    sendWs({ type: "plot_later", step_index: stepIndex, chart_type: chartType });
  };
  const handleActivateWorkspace = (datasetId: string) => {
    const target = chatSessions.find((c) => c.datasetId === datasetId);
    if (target) {
      setActiveChatId(target.sessionId);
      return;
    }
    setActiveWorkspaceId(datasetId);
  };

  const streamText = activeChatIdResolved ? streamTextRef.current[activeChatIdResolved] ?? "" : "";
  const progress = activeChatIdResolved ? progressRef.current[activeChatIdResolved] ?? null : null;
  const artifactBase =
    activeChat && activeChat.datasetId
      ? `/data/${activeChat.sessionId}/${activeChat.datasetId}/artifacts`
      : "";

  return (
    <div className="flex h-full flex-col bg-surface-page">
      <header className="fixed inset-x-0 top-0 z-40 flex h-14 items-center gap-3 bg-primary-dark px-5 shadow-card">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-cyan/20">
            <BarChart3 className="h-5 w-5 text-primary-cyan" />
          </div>
          <span className="text-base font-semibold text-white">MedSta</span>
          <span className="text-xs text-white/60">AI 数据分析工作台</span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => setCapabilitiesOpen(true)}
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-white/20 px-3 py-1.5 text-xs font-medium text-white/85 transition-colors hover:bg-white/10 hover:text-white"
          >
            <Boxes className="h-3.5 w-3.5" />
            能力
          </button>
          <div className="flex items-center gap-1 rounded-lg bg-white/10 p-1">
            {[
              { key: "chat", label: `会话（${chatSessions.length}）`, icon: MessagesSquare },
              { key: "workspace", label: `工作区（${workspaces.length}）`, icon: BarChart3 },
            ].map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                onClick={() => setActiveTab(key as "chat" | "workspace")}
                className={`inline-flex cursor-pointer items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                  activeTab === key ? "bg-white text-primary-dark" : "text-white/80 hover:text-white"
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                {label}
              </button>
            ))}
          </div>
        </div>
      </header>

      <main className="flex min-h-0 flex-1 pt-14 max-md:flex-col">
        <section
          className={`min-h-0 flex-1 border-ink/8 bg-surface-page max-lg:border-r ${
            activeTab === "chat" ? "flex" : "hidden lg:flex"
          } flex-col`}
        >
          <SessionTabs
            sessions={chatSessions}
            activeId={activeChatIdResolved}
            onSelect={(sid) => {
              setActiveChatId(sid);
              const entry = chatSessions.find((c) => c.sessionId === sid);
              setBindingBanner(`当前会话绑定表格：${entry?.name ?? "未绑定"}`);
              setTimeout(() => setBindingBanner(null), 4000);
            }}
            onCreate={() => void createChatSession()}
          />
          {bindingBanner && (
            <div className="animate-fade-in-up border-b border-primary/15 bg-primary/5 px-4 py-1.5 text-xs text-primary">
              {bindingBanner}
            </div>
          )}
          {activeChat && (
            <ChatPanel
              messages={messages}
              uploaded={!!activeChat.datasetId}
              confirming={confirming}
              sessionId={activeChat.sessionId}
              phase={phase}
              streamText={streamText}
              progress={progress}
              chartConfig={chartConfig}
              typeReview={typeReview}
              plotSuggest={plotSuggest}
              bindingName={activeChat.name}
              onUpload={(file) => void handleUpload(file, activeChat.sessionId)}
              onSend={handleSend}
              onConfirm={handleConfirm}
              onAccept={handleAccept}
              onRevise={handleRevise}
              onOption={handleOption}
              onInterrupt={handleInterrupt}
              onResume={handleResume}
              onChartChoice={handleChartChoice}
              artifactBase={artifactBase}
              onTypeConfirm={handleTypeConfirm}
              onPlotLater={handlePlotLater}
            />
          )}
        </section>
        <section
          className={`min-h-0 flex-1 bg-surface-card/60 ${
            activeTab === "workspace" ? "flex" : "hidden lg:flex"
          } flex-col`}
        >
          <WorkspacePanel
            sessionId={activeChat?.sessionId ?? ""}
            workspaces={workspaces}
            activeId={activeWorkspace?.datasetId ?? null}
            uploading={uploading}
            onActivate={handleActivateWorkspace}
            onUpload={(file) => void handleUpload(file)}
            onSetColumnType={handleSetColumnType}
          />
        </section>
      </main>

      <CapabilityDrawer open={capabilitiesOpen} onClose={() => setCapabilitiesOpen(false)} />
    </div>
  );
}
