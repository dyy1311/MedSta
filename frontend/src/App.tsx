import { useCallback, useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { BarChart3, Boxes, CloudUpload, MessagesSquare, Wrench } from "lucide-react";
import { COLUMN_TYPE_LABELS } from "./types";
import type {
  ChartConfigRequest, ChatMessage, ExecutionReport, Phase, PlotStyle, PlotSuggestStep,
  StepDelivery, TableProfile, TypeReviewRequest, WorkspaceSnapshot, WsEvent, WorkspaceTab,
} from "./types";
import { activateWorkspace, cleanupDuplicateSessions, clearWorkspaceOutputs, connectSession, createSession, deleteSession, fetchWorkspace, updateColumnTypes, uploadData, withToken } from "./api/client";
import type { SessionConnection } from "./api/client";
import ChatPanel from "./chat/ChatPanel";
import CapabilityDrawer from "./chat/CapabilityDrawer";
import SessionTabs from "./chat/SessionTabs";
import type { ChatSessionEntry } from "./chat/SessionTabs";
import WorkspacePanel from "./workspace/WorkspacePanel";
import ChainBuilder from "./builder/ChainBuilder";
import type { ChainStep } from "./builder/ChainBuilder";
import ErrorBoundary from "./components/ErrorBoundary";
import UploadChoiceDialog from "./components/UploadChoiceDialog";
import { useFileDrop } from "./hooks/useFileDrop";
import { listSessions, login } from "./api/client";

function upsertReport(reports: ExecutionReport[], report: ExecutionReport, replaceLast: boolean) {
  // 按 report_id 去重：刷新回放会重放历史 review_request 帧，快照里的同一份报告也会到，
  // 不去重就会在右栏堆出重复的统计表/图表
  if (report.report_id) {
    const index = reports.findIndex((item) => item.report_id === report.report_id);
    if (index >= 0) {
      const next = [...reports];
      next[index] = report;
      return next;
    }
  }
  const next = [...reports];
  if (replaceLast && next.length > 0) next[next.length - 1] = report;
  else next.push(report);
  return next;
}

/** 用户动作回放文案：必须与发送时的本地气泡逐字一致，重连才能对上同一条。 */
function replayUserText(replayed: {
  type: string;
  content?: string;
  decision?: string;
  index?: number;
}): string {
  if (replayed.type === "review_user" && replayed.decision === "revise") {
    return `修正意见：${replayed.content ?? ""}`;
  }
  if (replayed.type === "retry_step_user") {
    return `重跑节点 ${Number(replayed.content ?? 0) + 1}`;
  }
  if (replayed.type === "amend_step_user") {
    if (typeof replayed.index === "number") {
      return `补充（节点 ${replayed.index + 1}）：${replayed.content ?? ""}`;
    }
    return `补充说明：${replayed.content ?? ""}`;
  }
  return replayed.content ?? "";
}

/** 一次分析的五步，顺序与后端心跳一致：数据 → 类型 → 方案 → 执行 → 审阅。 */
const ANALYSIS_STAGES = ["接入数据", "确认类型", "确认方案", "逐节点执行", "审阅交付"] as const;

function analysisStageIndex(input: {
  hasData: boolean;
  phase: Phase;
  hasTypeReview: boolean;
  hasPlan: boolean;
}): number {
  if (!input.hasData) return 0;
  if (input.hasTypeReview) return 1;
  if (input.phase === "delivered") return 4;
  if (input.phase === "executing" || input.phase === "interrupted") return 3;
  if (input.phase === "chart_config" || input.hasPlan || input.phase === "thinking") return 2;
  return 1;
}

function AnalysisStageRail({ current }: { current: number }) {
  return (
    <ol aria-label="分析进度" className="flex items-center gap-1 overflow-x-auto px-4 pb-2.5">
      {ANALYSIS_STAGES.map((label, index) => {
        const state = index < current ? "done" : index === current ? "current" : "todo";
        return (
          <li key={label} className="flex shrink-0 items-center gap-1">
            <span
              aria-current={state === "current" ? "step" : undefined}
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
                state === "current"
                  ? "bg-primary text-white"
                  : state === "done"
                    ? "bg-primary/10 text-primary-dark"
                    : "text-ink-muted"
              }`}
            >
              <span className="num text-[11px]">{index + 1}</span>
              {label}
            </span>
            {index < ANALYSIS_STAGES.length - 1 && (
              <span aria-hidden="true" className="h-px w-3 bg-ink/15" />
            )}
          </li>
        );
      })}
    </ol>
  );
}

/** 占位工作区（报告先到、画像后到）：hydrate 时把报告迁移到真实数据集并删除占位 */
const PENDING_DATASET_PREFIX = "pending-";
const EMPTY_PROFILE: TableProfile = {
  row_count: 0,
  column_count: 0,
  columns: {},
  type_confirmed: false,
};

/** 桌面（lg+）三栏并排可拖拽；窄屏由顶部 Tab 切换单栏 */
function useIsDesktop() {
  const [isDesktop, setIsDesktop] = useState(
    () => typeof window !== "undefined" && !!window.matchMedia?.("(min-width: 1024px)")?.matches
  );
  useEffect(() => {
    const query = window.matchMedia("(min-width: 1024px)");
    const handler = (event: MediaQueryListEvent) => setIsDesktop(event.matches);
    query.addEventListener("change", handler);
    return () => query.removeEventListener("change", handler);
  }, []);
  return isDesktop;
}

function ResizeHandle({
  onPointerDown,
  label,
}: {
  onPointerDown: (event: ReactPointerEvent) => void;
  label: string;
}) {
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      onPointerDown={onPointerDown}
      className="group hidden w-1.5 shrink-0 cursor-col-resize items-center justify-center bg-surface-page lg:flex"
      title="拖拽调整宽度"
    >
      <div className="h-14 w-0.5 rounded-full bg-ink/10 transition-colors group-hover:bg-primary/60" />
    </div>
  );
}

/** 最新一条模型方案的步骤（作为装配起点导入） */
function latestPlanSteps(messages: ChatMessage[]): ChainStep[] | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.kind === "plan" && Array.isArray(message.steps) && message.steps.length > 0) {
      return message.steps.map((step) => ({
        method: step.method,
        title: step.title,
        target_columns: [...step.target_columns],
        chart_type: step.chart_type,
        params: { ...step.params },
      }));
    }
  }
  return null;
}

export default function App() {
  const [chatSessions, setChatSessions] = useState<ChatSessionEntry[]>([]);
  // 044 多用户：后端启用 MEDSTA_USERS 时 401 → 登录卡；登录后加载会话列表（含恢复会话）
  const [authNeeded, setAuthNeeded] = useState(false);
  const [loginError, setLoginError] = useState("");
  // 「从后端恢复」的会话集合：这些会话首连 WS 发 resume（last_seq=0）全量回放重建历史
  const restoredSessionsRef = useRef<Set<string>>(new Set());

  const loadSessionList = useCallback(async () => {
    try {
      const items = await listSessions();
      setAuthNeeded(false);
      // 标记恢复会话：首连即回放（本地新建会话没有历史，不回放避免噪音）
      items.forEach((item) => restoredSessionsRef.current.add(item.session_id));
      setChatSessions((prev) => {
        const known = new Set(prev.map((entry) => entry.sessionId));
        const restored = items
          .filter((item) => !known.has(item.session_id))
          .map((item) => ({
            sessionId: item.session_id,
            datasetId: item.dataset_id,
            name: item.name ?? "未绑定",
          }));
        return [...restored, ...prev];
      });
      // 刷新后必须自动回到某个会话：否则左右两栏都是空态（工作区与会话区「断开」）。
      // 优先上次停留的会话，其次后端列表首个（按快照 mtime 最新在前）。
      if (items.length > 0) {
        const remembered = localStorage.getItem("medsta_active_session");
        const pick =
          items.find((item) => item.session_id === remembered)?.session_id ??
          items[0]?.session_id ??
          null;
        setActiveChatId((prev) => prev ?? pick);
      }
    } catch (error) {
      if ((error as Error).message === "AUTH_REQUIRED") setAuthNeeded(true);
    }
  }, []);

  useEffect(() => {
    void loadSessionList();
  }, [loadSessionList]);

  const handleLogin = async (username: string, password: string) => {
    try {
      const result = await login(username, password);
      localStorage.setItem("medsta_token", result.token);
      setLoginError("");
      await loadSessionList();
    } catch (error) {
      setLoginError((error as Error).message);
    }
  };
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const activeChat = chatSessions.find((c) => c.sessionId === activeChatId) ?? null;
  const activeChatIdResolved = activeChat?.sessionId ?? null;
  const [bindingBanner, setBindingBanner] = useState<string | null>(null);
  // 事件回调需读取「事件所属会话」的绑定表，不能用可能过期的闭包状态
  const chatSessionsRef = useRef<ChatSessionEntry[]>([]);
  chatSessionsRef.current = chatSessions;
  const activeChatIdRef = useRef<string | null>(null);
  activeChatIdRef.current = activeChatId;

  const [workspaces, setWorkspaces] = useState<WorkspaceTab[]>([]);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<string | null>(null);
  // 工作区按会话过滤：多个会话的数据集原先共用一个平面数组，切会话时右栏会停在其他
  // 会话的表/图上（「工作区与会话区断开」）。现在只有当前会话的数据集参与展示与选择。
  const sessionWorkspaces = activeChatIdResolved
    ? workspaces.filter((w) => w.sessionId === activeChatIdResolved)
    : [];
  // 显式选择的工作区优先；会话默认绑定由「切换会话同步」useEffect 维护。
  const activeWorkspace =
    sessionWorkspaces.find((w) => w.datasetId === activeWorkspaceId) ??
    sessionWorkspaces.find((w) => w.datasetId === activeChat?.datasetId) ??
    sessionWorkspaces[0] ??
    null;

  const [messagesBySession, setMessagesBySession] = useState<Record<string, ChatMessage[]>>({});
  const [phaseBySession, setPhaseBySession] = useState<Record<string, Phase>>({});
  // 交互卡按会话落地：切走再切回必须还在（全局单份时切回后卡消失，
  // 而 phase 仍是 chart_config → 输入只读又无卡可确认，会话彻底卡死）
  const [chartConfigBySession, setChartConfigBySession] = useState<
    Record<string, ChartConfigRequest | null>
  >({});
  const [typeReviewBySession, setTypeReviewBySession] = useState<
    Record<string, TypeReviewRequest | null>
  >({});
  const [plotSuggestBySession, setPlotSuggestBySession] = useState<
    Record<string, PlotSuggestStep[] | null>
  >({});
  const [confirming, setConfirming] = useState(false);
  // 041 AI 确认类型：模型建议列表（用户采纳后经宿主校验落库）
  type ColumnSuggestion = { name: string; suggested_type: string; confidence: number; reason: string };
  const [columnSuggestionsBySession, setColumnSuggestionsBySession] = useState<
    Record<string, ColumnSuggestion[] | null>
  >({});
  // 模型正在生成列类型建议：按钮加载态 + 「正在分析」说明（此前点了没有任何反馈）
  const [suggestingBySession, setSuggestingBySession] = useState<Record<string, boolean>>({});
  // 047 节点级交付：每个工作节点完成即入列（失败节点带 error，可重跑/修正）
  const [stepDeliveriesBySession, setStepDeliveriesBySession] = useState<
    Record<string, StepDelivery[]>
  >({});
  const suggestTimerRef = useRef<Record<string, number>>({});
  const setSuggestingFor = useCallback((sid: string, value: boolean) => {
    setSuggestingBySession((prev) => ({ ...prev, [sid]: value }));
    const timer = suggestTimerRef.current[sid];
    if (timer) {
      window.clearTimeout(timer);
      delete suggestTimerRef.current[sid];
    }
    if (value) {
      // 兜底：模型侧无响应（网关超时/未配置）时不能永久卡在加载态
      suggestTimerRef.current[sid] = window.setTimeout(() => {
        delete suggestTimerRef.current[sid];
        setSuggestingBySession((prev) => ({ ...prev, [sid]: false }));
      }, 90_000);
    }
  }, []);
  const setConfirmingFor = (sid: string, value: boolean) => setConfirming(value);
  const chartConfig = activeChatIdResolved
    ? chartConfigBySession[activeChatIdResolved] ?? null
    : null;
  const typeReview = activeChatIdResolved
    ? typeReviewBySession[activeChatIdResolved] ?? null
    : null;
  const plotSuggest = activeChatIdResolved
    ? plotSuggestBySession[activeChatIdResolved] ?? null
    : null;
  const columnSuggestions = activeChatIdResolved
    ? columnSuggestionsBySession[activeChatIdResolved] ?? null
    : null;
  const suggesting = activeChatIdResolved
    ? suggestingBySession[activeChatIdResolved] ?? false
    : false;
  const stepDeliveries = activeChatIdResolved
    ? stepDeliveriesBySession[activeChatIdResolved] ?? []
    : [];
  // 切会话只重置「提交中」这种瞬时态；卡片本身随会话保留
  useEffect(() => {
    setConfirming(false);
  }, [activeChatIdResolved]);
  // 卸载时清掉建议超时定时器（否则组件销毁后仍会触发一次 setState）
  useEffect(() => {
    const timers = suggestTimerRef;
    return () => {
      Object.values(timers.current).forEach((timer) => window.clearTimeout(timer));
      timers.current = {};
    };
  }, []);
  // 记住当前会话：刷新后优先回到它（否则回到列表首个）
  useEffect(() => {
    if (activeChatIdResolved) localStorage.setItem("medsta_active_session", activeChatIdResolved);
  }, [activeChatIdResolved]);
  // 切换会话时，默认工作区跟随该会话绑定的数据集；
  // 该会话没有任何数据集时必须清空选择——否则右栏会继续显示上一个会话的表/图。
  useEffect(() => {
    const bound = chatSessionsRef.current.find(
      (c) => c.sessionId === activeChatIdResolved
    )?.datasetId;
    setActiveWorkspaceId(bound ?? null);
  }, [activeChatIdResolved]);
  const [capabilitiesOpen, setCapabilitiesOpen] = useState(false);
  const [connStatus, setConnStatus] = useState<"connected" | "reconnecting">("connected");
  // 桌面聚焦模式：点击顶部 Tab 将该栏最大化（再次点击同 Tab 恢复三栏并排）
  const [focusedPane, setFocusedPane] = useState<null | "chat" | "workspace" | "builder">(null);
  const lastSeqRef = useRef<Record<string, number>>({});
  const outputsClearedSeqRef = useRef<Record<string, number>>({});
  const [activeTab, setActiveTab] = useState<"chat" | "workspace" | "builder">("chat");
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
    // 实时读取当前会话：闭包里的 activeChatIdResolved 在事件到达瞬间可能已过期
    const isActive = ownerSid === activeChatIdRef.current;
    const emit = (message: ChatMessage) => pushMessage(ownerSid, message);
    // 036 回放：用户动作帧重建用户气泡（刷新/重启后聊天上下文完整）
    if ((event as unknown as { type: string }).type?.endsWith("_user")) {
      const replayed = event as unknown as {
        type: string;
        content?: string;
        decision?: string;
        index?: number;
        seq?: number;
      };
      const content = replayUserText(replayed);
      if (content) {
        // 本地 echo 没有 seq；重连把同一句补回来时只盖章，不再堆第二条
        setMessagesBySession((prev) => {
          const list = prev[ownerSid] ?? [];
          const seq = replayed.seq;
          if (
            typeof seq === "number" &&
            list.some((item) => item.role === "user" && item.kind === "text" && item.seq === seq)
          ) {
            return prev;
          }
          const pending = list.findIndex(
            (item) =>
              item.role === "user" &&
              item.kind === "text" &&
              item.seq == null &&
              item.content === content
          );
          if (pending >= 0) {
            const target = list[pending];
            if (target.role !== "user" || target.kind !== "text") return prev;
            const next = list.slice();
            next[pending] = { ...target, seq };
            return { ...prev, [ownerSid]: next };
          }
          return {
            ...prev,
            [ownerSid]: [...list, { role: "user", kind: "text", content, seq }],
          };
        });
      }
      return;
    }
    switch (event.type) {
      case "dataset_added": {
        // 插补数据集：追加工作区但不切换 active，避免打断用户当前查看的数据
        const datasetId = event.dataset_id;
        setWorkspaces((prev) => {
          if (prev.some((item) => item.datasetId === datasetId)) return prev;
          return [
            ...prev,
            {
              datasetId,
              name: event.name,
              profile: event.profile,
              reports: [],
              imputed: event.imputed,
              sessionId: ownerSid,
            },
          ];
        });
        if (isActive) {
          emit({
            role: "system",
            kind: "notice",
            content: `已生成${event.imputed ? "插补" : "清洗"}数据集「${event.name}」，可在工作区标签页切换查看（当前未切换）。`,
          });
        }
        break;
      }
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
          return [
            ...prev,
            { datasetId, name, profile: event.profile, reports: [], sessionId: ownerSid },
          ];
        });
        // 激活语义必须与后端 active_dataset_id 一致：首次绑定与显式切换才改激活，
        // 已绑定会话再次上传只是「新增标签」（046）——若此刻把显示切过去，
        // 就会出现「看到的是新表、分析用的还是旧表」的静默错分析。
        const boundDatasetId = chatSessionsRef.current.find(
          (c) => c.sessionId === ownerSid
        )?.datasetId;
        const becomesActive = Boolean(event.dataset_id) && (Boolean(event.active) || !boundDatasetId);
        if (becomesActive) {
          setChatSessions((prev) =>
            prev.map((c) => (c.sessionId === ownerSid ? { ...c, datasetId, name } : c))
          );
          if (isActive) setActiveWorkspaceId(datasetId);
        }
        if (isActive) {
          emit({
            role: "system", kind: "notice",
            content: becomesActive
              ? `数据「${name}」已绑定当前会话：${event.profile.row_count} 行 × ${event.profile.column_count} 列。`
              : `已添加数据集「${name}」（${event.profile.row_count} 行 × ${event.profile.column_count} 列），可在工作区标签切换使用。`,
          });
        }
        break;
      }
      case "type_review":
        setTypeReviewBySession((prev) => ({ ...prev, [ownerSid]: event }));
        setPhaseFor(ownerSid, "idle");
        break;
      case "type_confirmed": {
        setTypeReviewBySession((prev) => ({ ...prev, [ownerSid]: null }));
        setWorkspaces((prev) =>
          prev.map((w) => (w.datasetId === (event.dataset_id ?? "") ? { ...w, profile: event.profile } : w))
        );
        // 建议已被消费：清掉，避免用户对着同一批建议二次采纳
        setColumnSuggestionsBySession((prev) => ({ ...prev, [ownerSid]: null }));
        setSuggestingFor(ownerSid, false);
        // 会话区同步一条可核对的提示：谁把哪几列改成了什么（工作台已同步更新）
        const updated = (event as unknown as { updated?: string[] }).updated ?? [];
        const source = (event as unknown as { source?: string }).source;
        const columnTypes =
          (event as unknown as { profile?: { columns?: Record<string, { type: string }> } })
            .profile?.columns ?? {};
        const label =
          updated.length === 1
            ? `「${updated[0]}」→ ${
                COLUMN_TYPE_LABELS[columnTypes[updated[0]]?.type ?? ""] ?? "已更新"
              }`
            : `${updated.length} 列`;
        if (source === "type_review") {
          emit({ role: "system", kind: "notice", content: "变量类型已敲定，继续讨论。" });
        } else if (source === "ai") {
          emit({
            role: "system",
            kind: "notice",
            content: `已采纳 AI 建议，更新 ${label}；工作区画像已同步。`,
          });
        } else {
          emit({ role: "system", kind: "notice", content: `列类型已更新：${label}。` });
        }
        break;
      }
      case "step_result": {
        const step = (event as { step: StepDelivery; index: number; total: number }).step;
        setStepDeliveriesBySession((prev) => {
          const list = [...(prev[ownerSid] ?? [])];
          const at = list.findIndex((item) => item.index === step.index);
          if (at >= 0) list[at] = step;
          else list.push(step);
          list.sort((a, b) => a.index - b.index);
          return { ...prev, [ownerSid]: list };
        });
        setPhaseFor(ownerSid, "executing");
        break;
      }
      case "plot_suggest":
        setPlotSuggestBySession((prev) => ({ ...prev, [ownerSid]: event.steps }));
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
          setPhaseFor(ownerSid, "executing");
        } else {
          setPhaseFor(ownerSid, "thinking");
        }
        if (isActive) forceRender((n) => n + 1);
        break;
      case "plan": {
        const thinking = streamTextRef.current[ownerSid] ?? "";
        streamTextRef.current[ownerSid] = "";
        if (thinking) emit({ role: "system", kind: "thinking", content: thinking });
        emit({ role: "system", kind: "plan", type: "plan", message: event.message,
               steps: event.steps, options: event.options, flow: event.flow,
               estimand: event.estimand ?? null, sap_status: event.sap_status });
        // 新工作流：上一轮的节点交付作废（避免与本次执行混淆）
        setStepDeliveriesBySession((prev) => ({ ...prev, [ownerSid]: [] }));
        setPhaseFor(ownerSid, "idle");
        setConfirmingFor(ownerSid, false);
        // 新方案出现：上一轮的执行补图建议与出图配置都已过期
        setChartConfigBySession((prev) => ({ ...prev, [ownerSid]: null }));
        setPlotSuggestBySession((prev) => ({ ...prev, [ownerSid]: null }));
        break;
      }
      case "workspace_outputs_cleared": {
        const clearedSeq = (event as unknown as { seq?: number }).seq;
        if (typeof clearedSeq === "number") {
          outputsClearedSeqRef.current[ownerSid] = Math.max(
            outputsClearedSeqRef.current[ownerSid] ?? 0,
            clearedSeq
          );
        }
        setWorkspaces((prev) =>
          prev.map((workspace) =>
            workspace.sessionId === ownerSid ? { ...workspace, reports: [] } : workspace
          )
        );
        emit({
          role: "system",
          kind: "notice",
          content: "已清空工作台既往产出，导入表格仍保留。",
        });
        break;
      }
      case "review_request": {
        const replaySeq = (event as unknown as { seq?: number }).seq;
        const clearedAt = outputsClearedSeqRef.current[ownerSid] ?? 0;
        const skipWorkspace =
          typeof replaySeq === "number" && replaySeq <= clearedAt;
        const boundDatasetId =
          chatSessionsRef.current.find((c) => c.sessionId === ownerSid)?.datasetId ?? "";
        setWorkspaces((prev) => {
          if (skipWorkspace) return prev;
          const target =
            prev.find((w) => w.sessionId === ownerSid && w.datasetId === boundDatasetId) ??
            prev.find((w) => w.sessionId === ownerSid);
          if (target) {
            return prev.map((w) =>
              w === target
                ? { ...w, reports: upsertReport(w.reports, event.report, !!event.updated) }
                : w
            );
          }
          // 报告比画像先到（刷新回放 / 快照未达）：先建占位工作区挂上报告，
          // hydrate 拿到真实数据集后迁移并删除占位——否则右栏永远看不到报告。
          return [
            ...prev,
            {
              sessionId: ownerSid,
              datasetId: boundDatasetId || `${PENDING_DATASET_PREFIX}${ownerSid}`,
              name: "分析结果",
              profile: EMPTY_PROFILE,
              reports: [event.report],
            },
          ];
        });
        // 终结事件按 ownerSid 落状态与消息：切走再切回不得卡在 executing/thinking（审查修复）
        setPhaseFor(ownerSid, "idle");
        if (event.updated) {
          emit({ role: "system", kind: "notice", content: "补绘图完成，报告已更新。" });
        } else {
          emit({ role: "system", kind: "review", report: event.report, delivered: false });
        }
        if (isActive) forceRender((n) => n + 1);
        break;
      }
      case "interpretation": {
        // 解读补进最后一条审阅卡：不新增消息，不污染历史卡片
        setMessagesBySession((prev) => {
          const list = prev[ownerSid] ?? [];
          const lastIndex = list.map((item) => item.kind).lastIndexOf("review");
          const last = list[lastIndex];
          if (lastIndex < 0 || last?.kind !== "review") return prev;
          const next = [...list];
          next[lastIndex] = {
            ...last,
            report: {
              ...last.report,
              interpretation: {
                summary: event.summary,
                steps: event.steps,
                caveats: event.caveats,
                unverified_numbers: event.unverified_numbers,
              },
            },
          };
          return { ...prev, [ownerSid]: next };
        });
        break;
      }
      case "answer": {
        emit({
          role: "system",
          kind: "answer",
          content: event.answer,
          caveats: event.caveats,
          unverified: event.unverified_numbers,
        });
        setPhaseFor(ownerSid, "delivered");
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
        setPhaseFor(ownerSid, "delivered");
        break;
      }
      case "back_to_discussion":
        setPhaseFor(ownerSid, "idle");
        emit({ role: "system", kind: "notice", content: event.message });
        break;
      case "interrupted":
        setPhaseFor(ownerSid, "interrupted");
        streamTextRef.current[ownerSid] = "";
        if (isActive) setConfirming(false);
        setChartConfigBySession((prev) => ({ ...prev, [ownerSid]: null }));
        setPlotSuggestBySession((prev) => ({ ...prev, [ownerSid]: null }));
        emit({ role: "system", kind: "notice", content: event.message });
        break;
      case "resumed": {
        // 回放会重放历史 progress 帧（phase 被推到 executing），但进程可能已重启、
        // 任务早已结束——以服务端当前阶段为准纠正，否则刷新后永久停在「执行中」。
        const stage = (event as unknown as { stage?: string }).stage;
        const restoredPhase: Phase =
          stage === "delivered" ? "delivered" : stage === "executing" ? "executing" : "idle";
        setPhaseFor(ownerSid, restoredPhase);
        if (event.message) emit({ role: "system", kind: "notice", content: event.message });
        break;
      }
      case "chart_config":
        setPhaseFor(ownerSid, "chart_config");
        streamTextRef.current[ownerSid] = "";
        if (isActive) setConfirming(false);
        setChartConfigBySession((prev) => ({
          ...prev,
          [ownerSid]: {
            steps: event.steps, multi_chart: event.multi_chart,
            alpha: event.alpha, correction: event.correction, message: event.message,
          },
        }));
        break;
      case "column_type_suggestions": {
        const suggestions =
          (event as unknown as { suggestions?: ColumnSuggestion[] }).suggestions ?? [];
        setColumnSuggestionsBySession((prev) => ({ ...prev, [ownerSid]: suggestions }));
        setSuggestingFor(ownerSid, false);
        emit({
          role: "system",
          kind: "notice",
          content: suggestions.length
            ? `AI 已给出 ${suggestions.length} 列的类型建议，可在工作区「数据画像」里逐列或一键采纳。`
            : "AI 未给出可采纳的类型建议（可能已全部符合当前类型）。",
        });
        break;
      }
      case "chat_rejected":
        // 043 输入守卫：闲聊/无关请求被拒——notice 气泡引导用户描述统计需求
        setPhaseFor(ownerSid, "idle");
        streamTextRef.current[ownerSid] = "";
        emit({
          role: "system",
          kind: "notice",
          content: (event as unknown as { reason: string }).reason,
        });
        break;
      case "error":
        setPhaseFor(ownerSid, "idle");
        streamTextRef.current[ownerSid] = "";
        if (isActive) setConfirming(false);
        setChartConfigBySession((prev) => ({ ...prev, [ownerSid]: null }));
        setPlotSuggestBySession((prev) => ({ ...prev, [ownerSid]: null }));
        setSuggestingFor(ownerSid, false);
        emit({ role: "system", kind: "error", code: event.code, message: event.message,
               hint: event.hint, detail: event.detail });
        break;
    }
  }, [pushMessage, setPhaseFor, setSuggestingFor]);

  const handlerRef = useRef(handleEvent);
  handlerRef.current = handleEvent;

  // 工作区快照：刷新/重启后右栏不能只靠事件流重建（事件流会轮转，data_profile 可能
  // 已被裁掉 → 左栏有执行变动、右栏空白）。进入会话时先取快照，回放只做增量。
  const hydrateWorkspace = useCallback(async (sid: string) => {
    let snapshot: WorkspaceSnapshot;
    try {
      snapshot = await fetchWorkspace(sid);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      console.error("工作区快照加载失败", message);
      // 404 = 后端还是旧进程（dev 的 uvicorn 没有 --reload）：直接告诉用户怎么修
      if (message.includes("404")) {
        setBindingBanner("后端未提供工作区快照接口（404）：代码已更新但服务未重启，请重启 dev 栈");
        setTimeout(() => setBindingBanner(null), 10000);
      }
      return;
    }
    if (typeof snapshot.outputs_cleared_seq === "number") {
      outputsClearedSeqRef.current[sid] = Math.max(
        outputsClearedSeqRef.current[sid] ?? 0,
        snapshot.outputs_cleared_seq
      );
    }
    setWorkspaces((prev) => {
      const next = prev
        .filter((w) => !(w.sessionId === sid && w.datasetId.startsWith(PENDING_DATASET_PREFIX)))
        .map((w) => ({ ...w }));
      const pendingReports = prev
        .filter((w) => w.sessionId === sid && w.datasetId.startsWith(PENDING_DATASET_PREFIX))
        .flatMap((w) => w.reports);

      for (const dataset of snapshot.datasets) {
        const index = next.findIndex(
          (w) => w.sessionId === sid && w.datasetId === dataset.dataset_id
        );
        if (index >= 0) {
          next[index] = {
            ...next[index],
            name: dataset.name || next[index].name,
            profile: dataset.profile,
          };
        } else {
          next.push({
            sessionId: sid,
            datasetId: dataset.dataset_id,
            name: dataset.name || dataset.dataset_id,
            profile: dataset.profile,
            reports: [],
          });
        }
      }

      const targetId = snapshot.active_dataset_id ?? snapshot.datasets[0]?.dataset_id ?? null;
      const target = next.find((w) => w.sessionId === sid && w.datasetId === targetId);
      const clearedAt = outputsClearedSeqRef.current[sid] ?? 0;
      if (clearedAt > 0 && !snapshot.report) {
        for (const workspace of next) {
          if (workspace.sessionId === sid) workspace.reports = [];
        }
      }
      if (target) {
        let reports = clearedAt > 0 && !snapshot.report ? [] : target.reports;
        for (const report of pendingReports) {
          if (clearedAt > 0 && !snapshot.report) break;
          reports = upsertReport(reports, report, false);
        }
        if (snapshot.report) reports = upsertReport(reports, snapshot.report, false);
        target.reports = reports;
      } else if (pendingReports.length > 0) {
        // 快照里没有任何数据集（异常/被清理）：报告不能随占位一起消失
        next.push({
          sessionId: sid,
          datasetId: `${PENDING_DATASET_PREFIX}${sid}`,
          name: "分析结果",
          profile: EMPTY_PROFILE,
          reports: pendingReports,
        });
      }
      return next;
    });
    if (activeChatIdRef.current === sid) {
      setActiveWorkspaceId(snapshot.active_dataset_id ?? null);
    }
  }, []);

  useEffect(() => {
    if (!activeChatIdResolved) return;
    if (connSessionRef.current === activeChatIdResolved) return;
    connectionRef.current?.close();
    const sid = activeChatIdResolved;
    connSessionRef.current = sid;
    // 与 WS 连接并行：快照负责「补齐」，回放负责「增量」，两者按 report_id/dataset_id 去重
    void hydrateWorkspace(sid);
    connectionRef.current = connectSession(
      sid,
      (event) => {
        const seq = (event as unknown as { seq?: number }).seq;
        if (typeof seq === "number") lastSeqRef.current[sid] = seq;
        handlerRef.current(sid, event);
      },
      undefined,
      {
        getLastSeq: () => lastSeqRef.current[sid] ?? null,
        // 有已知 seq（重连/切回）或恢复的会话（刷新后）都回放；本地新建不回放
        shouldResume: () =>
          Boolean(lastSeqRef.current[sid]) || restoredSessionsRef.current.has(sid),
        onStatus: (status) => {
          if (connSessionRef.current === sid) setConnStatus(status);
        },
        // 令牌失效（后端重启后内存令牌表清空）：停止无限重连，回到登录卡
        onAuthError: () => {
          localStorage.removeItem("medsta_token");
          setAuthNeeded(true);
        },
      }
    );
    return () => {
      if (connSessionRef.current === sid) {
        connectionRef.current?.close();
        connectionRef.current = null;
        connSessionRef.current = null;
      }
    };
  }, [activeChatIdResolved, hydrateWorkspace]);

  const createChatSession = useCallback(async (name = "未绑定"): Promise<string | null> => {
    let session_id: string;
    try {
      ({ session_id } = await createSession());
    } catch (error) {
      // 创建失败必须可见（401/500 时不再产生 undefined 会话 Tab）
      const detail = error instanceof Error ? error.message : String(error);
      setBindingBanner(`创建会话失败：${detail}`);
      setTimeout(() => setBindingBanner(null), 6000);
      return null;
    }
    setChatSessions((prev) => [...prev, { sessionId: session_id, datasetId: null, name }]);
    setActiveChatId(session_id);
    setBindingBanner(`新会话已创建，当前绑定表格：${name}`);
    setTimeout(() => setBindingBanner(null), 4000);
    return session_id;
  }, []);

  // 批次12 会话删除：确认后调 DELETE，清理本地状态并切换活跃会话
  const handleDeleteSession = async (sessionId: string) => {
    const target = chatSessions.find((c) => c.sessionId === sessionId);
    const label = target?.name ?? "会话";
    if (
      !window.confirm(`删除「${label}」？会话的快照、消息与图表产物将一并清除，不可恢复。`)
    ) {
      return;
    }
    try {
      await deleteSession(sessionId);
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      setBindingBanner(`删除会话失败：${detail}`);
      setTimeout(() => setBindingBanner(null), 6000);
      return;
    }
    setChatSessions((prev) => prev.filter((c) => c.sessionId !== sessionId));
    delete lastSeqRef.current[sessionId];
    delete outputsClearedSeqRef.current[sessionId];
    // 清掉该会话的全部 per-session 状态（消息 / 阶段 / 交互卡 / 流式缓冲）
    setMessagesBySession((prev) => {
      const next = { ...prev };
      delete next[sessionId];
      return next;
    });
    setPhaseBySession((prev) => {
      const next = { ...prev };
      delete next[sessionId];
      return next;
    });
    setChartConfigBySession((prev) => {
      const next = { ...prev };
      delete next[sessionId];
      return next;
    });
    setTypeReviewBySession((prev) => {
      const next = { ...prev };
      delete next[sessionId];
      return next;
    });
    setPlotSuggestBySession((prev) => {
      const next = { ...prev };
      delete next[sessionId];
      return next;
    });
    setStepDeliveriesBySession((prev) => {
      const next = { ...prev };
      delete next[sessionId];
      return next;
    });
    const suggestTimer = suggestTimerRef.current[sessionId];
    if (suggestTimer) {
      window.clearTimeout(suggestTimer);
      delete suggestTimerRef.current[sessionId];
    }
    delete streamTextRef.current[sessionId];
    delete progressRef.current[sessionId];
    // 工作区标签同步清理：否则已删会话的数据集仍留在数组里（刷新后还会被快照去重掉）
    setWorkspaces((prev) => prev.filter((w) => w.sessionId !== sessionId));
    if (activeChatIdResolved === sessionId) {
      const remaining = chatSessions.filter((c) => c.sessionId !== sessionId);
      setActiveChatId(remaining[0]?.sessionId ?? null);
    }
    setBindingBanner(`会话「${label}」已删除`);
    setTimeout(() => setBindingBanner(null), 4000);
  };

  // 批次13 批量清理重复会话：按绑定文件名分组保留最新，其余删除
  const handleCleanupDuplicates = async () => {
    if (
      !window.confirm(
        "按绑定文件名分组，保留每组最新的 1 个会话，其余重复会话（含快照与图表）将删除。是否继续？"
      )
    ) {
      return;
    }
    try {
      const result = await cleanupDuplicateSessions();
      const removed = new Set(result.deleted);
      result.deleted.forEach((sid) => {
        delete lastSeqRef.current[sid];
        delete outputsClearedSeqRef.current[sid];
      });
      setChatSessions((prev) => prev.filter((c) => !removed.has(c.sessionId)));
      setMessagesBySession((prev) => {
        const next = { ...prev };
        removed.forEach((sid) => delete next[sid]);
        return next;
      });
      setWorkspaces((prev) => prev.filter((w) => !removed.has(w.sessionId)));
      if (activeChatIdResolved && removed.has(activeChatIdResolved)) {
        const remaining = chatSessions.filter((c) => !removed.has(c.sessionId));
        setActiveChatId(remaining[0]?.sessionId ?? null);
      }
      setBindingBanner(
        `已清理 ${result.deleted.length} 个重复会话，保留 ${result.kept.length} 个` +
          (result.skipped.length ? `（${result.skipped.length} 个执行中已跳过）` : "")
      );
      setTimeout(() => setBindingBanner(null), 6000);
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      setBindingBanner(`清理失败：${detail}`);
      setTimeout(() => setBindingBanner(null), 6000);
    }
  };

  // 046 数据去向选择：已绑定数据的会话再上传时先弹选择，不直接执行。
  // 队列化：多文件拖拽时逐个弹窗（单槽位会让后来的文件覆盖前一个而静默丢失）。
  const [pendingUpload, setPendingUpload] = useState<File | null>(null);
  const pendingQueueRef = useRef<{ file: File; resolve: () => void }[]>([]);

  const requestUpload = (file: File): Promise<void> => {
    const current = chatSessionsRef.current.find((c) => c.sessionId === activeChatIdResolved);
    if (!current?.datasetId) return handleUpload(file);
    // 已绑定：挂起等待用户选择，Promise 让 useFileDrop 的顺序处理真正生效
    return new Promise<void>((resolve) => {
      pendingQueueRef.current.push({ file, resolve });
      setPendingUpload((prev) => prev ?? file);
    });
  };

  const releasePendingUpload = (choice: "current" | "new" | "cancel") => {
    const head = pendingQueueRef.current.shift();
    setPendingUpload(null);
    if (!head) return;
    const targetSession = activeChatIdResolved;
    void (async () => {
      try {
        if (choice === "current") {
          await handleUpload(head.file, { sessionId: targetSession ?? undefined });
        } else if (choice === "new") {
          await handleUpload(head.file, { forceNew: true });
        }
      } finally {
        // 上传完成后再问下一个：避免同一会话并发上传互踩 uploading / 绑定状态
        head.resolve();
        setPendingUpload(pendingQueueRef.current[0]?.file ?? null);
      }
    })();
  };

  const handleUpload = async (
    file: File,
    target?: { sessionId?: string; forceNew?: boolean },
  ): Promise<void> => {
    setUploading(true);
    try {
      let sid = target?.sessionId ?? activeChatIdResolved;
      const occupied = Boolean(
        chatSessions.find((c) => c.sessionId === sid)?.datasetId
      );
      // 显式指定目标（加入当前工作区）不再强制新建；未指定时保持旧行为
      if (target?.forceNew || (!target?.sessionId && (!sid || occupied))) {
        const created = await createChatSession(file.name);
        if (!created) return;
        sid = created;
      }
      if (!sid) return; // 类型收窄：上述分支已保证 sid 必有值
      const becameActive = !occupied; // 后端只为「首个数据集」自动激活
      const result = await uploadData(sid, file);
      handleEvent(sid, {
        type: "data_profile",
        dataset_id: result.dataset_id,
        name: file.name,
        profile: result.profile as TableProfile,
        active: becameActive,
      });
    } catch (error) {
      // 上传失败必须可见：走统一错误卡，避免只写 console 后界面无反馈
      const detail = error instanceof Error ? error.message : String(error);
      const sid = target?.sessionId ?? activeChatIdResolved;
      if (sid) {
        handleEvent(sid, {
          type: "error",
          code: "UPLOAD_FAILED",
          message: `上传失败：${detail}`,
          hint: "确认文件为 CSV / Excel（.csv/.xlsx/.xls），表头完整且非空",
        });
      } else {
        setBindingBanner(`上传失败：${detail}`);
        setTimeout(() => setBindingBanner(null), 6000);
      }
    } finally {
      setUploading(false);
    }
  };

  const handleSetColumnType = (
    datasetId: string,
    column: string,
    type: string,
    source: "manual" | "ai" = "manual"
  ) => {
    if (!datasetId || !activeChatIdResolved) return;
    // 单列修改也走批量端点（带 source）：会话区靠 type_confirmed 广播同步，
    // 单列端点不广播会让「工作台改了一列，左栏毫无记录」
    updateColumnTypes(activeChatIdResolved, datasetId, { [column]: type }, source)
      .then((result: { profile: TableProfile }) => {
        setWorkspaces((prev) =>
          prev.map((w) => (w.datasetId === datasetId ? { ...w, profile: result.profile } : w))
        );
        if (source === "ai") {
          setColumnSuggestionsBySession((prev) => {
            const list = prev[activeChatIdResolved] ?? null;
            if (!list) return prev;
            const rest = list.filter((item) => item.name !== column);
            return { ...prev, [activeChatIdResolved]: rest.length ? rest : null };
          });
        }
      })
      .catch((error: unknown) => console.error("type edit failed", error));
  };

  /** 批量列类型修改：一次请求多列，返回画像后更新对应工作区 */
  const handleSetColumnTypes = (
    datasetId: string,
    types: Record<string, string>,
    source: "manual" | "ai" = "manual"
  ) => {
    if (!activeChatIdResolved || Object.keys(types).length === 0) return;
    updateColumnTypes(activeChatIdResolved, datasetId, types, source)
      .then((result: { profile: TableProfile }) => {
        setWorkspaces((prev) =>
          prev.map((w) => (w.datasetId === datasetId ? { ...w, profile: result.profile } : w))
        );
        // 建议已消费：整批或逐列清掉，服务端 type_confirmed 也会再清一次（幂等）
        setColumnSuggestionsBySession((prev) => {
          const list = prev[activeChatIdResolved] ?? null;
          if (!list) return prev;
          if (source === "ai") {
            const rest = list.filter((item) => !(item.name in types));
            return { ...prev, [activeChatIdResolved]: rest.length ? rest : null };
          }
          return prev;
        });
      })
      .catch((error: unknown) => {
        console.error("batch type edit failed", error);
        setBindingBanner(`批量修改失败：${error instanceof Error ? error.message : "未知错误"}`);
        setTimeout(() => setBindingBanner(null), 4000);
      });
  };

  const handleSuggestTypes = () => {
    if (!activeChatIdResolved) return;
    setSuggestingFor(activeChatIdResolved, true);
    sendWs({ type: "suggest_column_types" });
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
    choices: ({ step_id: string; chart_type: string } & PlotStyle)[];
    layout: string;
    alpha: number;
    correction: string;
    use_default?: boolean;
  }) => {
    setConfirming(true);
    if (activeChatIdResolved) {
      setPhaseFor(activeChatIdResolved, "executing");
      setChartConfigBySession((prev) => ({ ...prev, [activeChatIdResolved]: null }));
    }
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
  /** 把该会话最近一张审阅卡标记为「已提交」：重复点击不再发帧（此前必撞 NO_ACTIVE_RUN） */
  const markReviewSubmitted = (sessionId: string) => {
    setMessagesBySession((prev) => {
      const list = prev[sessionId] ?? [];
      const reversed = [...list].reverse();
      const hit = reversed.findIndex((item) => item.kind === "review");
      if (hit < 0) return prev;
      const index = list.length - 1 - hit;
      const target = list[index];
      if (target.kind !== "review") return prev;
      const next = [...list];
      next[index] = { ...target, submitted: true };
      return { ...prev, [sessionId]: next };
    });
  };

  const handleRevise = (note: string) => {
    if (!activeChatIdResolved) return;
    if (note) {
      pushMessage(activeChatIdResolved, { role: "user", kind: "text", content: `修正意见：${note}` });
      // 后端会带着修正意见自动重出方案：先锁卡并进入思考态
      markReviewSubmitted(activeChatIdResolved);
      setPhaseFor(activeChatIdResolved, "thinking");
    } else {
      // 交付态「调整分析方案」：只请求回到讨论，不产生空修正意见
      setPhaseFor(activeChatIdResolved, "idle");
    }
    sendWs({ type: "review", decision: "revise", content: note });
  };
  const handleInterrupt = () => sendWs({ type: "interrupt" });
  const handleResume = () => sendWs({ type: "resume" });
  const handleTypeConfirm = (types: Record<string, string>) => {
    if (!activeChatIdResolved) return;
    setPhaseFor(activeChatIdResolved, "thinking");
    sendWs({ type: "type_confirm", types });
  };
  const handlePlotLater = (stepIndex: number, chartType: string, style?: PlotStyle, method?: string) => {
    if (activeChatIdResolved) {
      setPhaseFor(activeChatIdResolved, "executing");
      setPlotSuggestBySession((prev) => ({ ...prev, [activeChatIdResolved]: null }));
    }
    sendWs({
      type: "plot_later",
      step_index: stepIndex,
      chart_type: chartType,
      ...(method ? { method } : {}),
      ...(style ?? {}),
    });
  };
  /** 047 节点重试：只重跑失败节点及其下游（不必整条链重来） */
  const handleRetryStep = (index: number) => {
    if (!activeChatIdResolved) return;
    setPhaseFor(activeChatIdResolved, "executing");
    sendWs({ type: "retry_step", index });
  };

  /** 047 定点修正：补充信息后让模型只重写该节点，再重跑该节点及下游 */
  const handleAmendStep = (index: number, note: string) => {
    if (!activeChatIdResolved) return;
    const trimmed = note.trim();
    if (trimmed) {
      pushMessage(activeChatIdResolved, {
        role: "user",
        kind: "text",
        content: `补充（节点 ${index + 1}）：${trimmed}`,
      });
    }
    setPhaseFor(activeChatIdResolved, "executing");
    sendWs({ type: "amend_step", index, note: trimmed });
  };

  const handleClearOutputs = async () => {
    if (!activeChatIdResolved) return;
    const sid = activeChatIdResolved;
    try {
      const result = await clearWorkspaceOutputs(sid);
      if (typeof result.outputs_cleared_seq === "number") {
        outputsClearedSeqRef.current[sid] = Math.max(
          outputsClearedSeqRef.current[sid] ?? 0,
          result.outputs_cleared_seq
        );
      }
      setWorkspaces((prev) =>
        prev.map((workspace) =>
          workspace.sessionId === sid ? { ...workspace, reports: [] } : workspace
        )
      );
      setBindingBanner("已清空工作台既往产出，导入表格仍保留");
      setTimeout(() => setBindingBanner(null), 4000);
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      setBindingBanner(`清空产出失败：${detail}`);
      setTimeout(() => setBindingBanner(null), 6000);
    }
  };

  const handleActivateWorkspace = (datasetId: string) => {
    // 显式选择立即生效（无论该数据集是否绑定会话）；绑定会话的标签同时切换会话
    setActiveWorkspaceId(datasetId);
    const target = chatSessions.find((c) => c.datasetId === datasetId);
    if (target && target.sessionId !== activeChatIdResolved) {
      setActiveChatId(target.sessionId);
    }
    // 必须同步后端 active_dataset_id：否则画像/方案/执行仍用旧数据集（静默错分析）。
    // 走 REST 而非 WS：跨会话切标签时 WS 正在重连，消息可能发不出去。
    const sid = target?.sessionId ?? activeChatIdResolved;
    if (!sid) return;
    void activateWorkspace(sid, datasetId)
      .then((result) => {
        handleEvent(sid, { ...result, type: "data_profile", active: true });
      })
      .catch((error: unknown) => {
        setBindingBanner(
          `切换工作区失败：${error instanceof Error ? error.message : String(error)}`
        );
        setTimeout(() => setBindingBanner(null), 5000);
      });
  };

  // 042 全局拖拽导入：拖数据文件到窗口任意位置即可上传（复用现有上传管道）
  const { dragOver } = useFileDrop((file) => requestUpload(file));

  const streamText = activeChatIdResolved ? streamTextRef.current[activeChatIdResolved] ?? "" : "";
  const progress = activeChatIdResolved ? progressRef.current[activeChatIdResolved] ?? null : null;
  // 直链无法带请求头：多用户模式必须拼 ?token=（否则审阅卡「查看图表」401）
  const artifactBase =
    activeChat && activeChat.datasetId
      ? withToken(`/data/${activeChat.sessionId}/${activeChat.datasetId}/artifacts`)
      : "";

  // ---- 三区布局：桌面（lg+）三栏并排可拖拽调宽；窄屏由顶部 Tab 切换单栏 ----
  const isDesktop = useIsDesktop();
  const [chatWidth, setChatWidth] = useState(380);
  const [builderWidth, setBuilderWidth] = useState(360);
  const dragRef = useRef<{ handle: "chat" | "builder"; startX: number; startW: number } | null>(
    null
  );

  useEffect(() => {
    const clamp = (value: number, min: number, max: number) =>
      Math.min(Math.max(value, min), max);
    const onMove = (event: PointerEvent) => {
      const drag = dragRef.current;
      if (!drag) return;
      const delta = event.clientX - drag.startX;
      if (drag.handle === "chat") {
        setChatWidth(clamp(drag.startW + delta, 280, 640));
      } else {
        // builder 在最右侧：拖其左边缘，宽度与位移反向
        setBuilderWidth(clamp(drag.startW - delta, 260, 560));
      }
    };
    const onUp = () => {
      dragRef.current = null;
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, []);

  const startDrag = (handle: "chat" | "builder") => (event: ReactPointerEvent) => {
    dragRef.current = {
      handle,
      startX: event.clientX,
      startW: handle === "chat" ? chatWidth : builderWidth,
    };
    event.preventDefault();
  };

  const chatPane = (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
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
        onDelete={(sid) => void handleDeleteSession(sid)}
        onCleanupDuplicates={() => void handleCleanupDuplicates()}
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
          stepDeliveries={stepDeliveries}
          datasetId={activeWorkspace?.datasetId ?? null}
          onRetryStep={handleRetryStep}
          onAmendStep={handleAmendStep}
          chartConfig={chartConfig}
          typeReview={typeReview}
          plotSuggest={plotSuggest}
          bindingName={activeChat.name}
          onUpload={(file) => requestUpload(file)}
          onSend={handleSend}
          onConfirm={handleConfirm}
          onAccept={handleAccept}
          onRevise={handleRevise}
          onOption={handleOption}
          onInterrupt={handleInterrupt}
          onResume={handleResume}
          onGoWorkspace={() => {
            setActiveTab("workspace");
            setFocusedPane("workspace");
          }}
          onChartChoice={handleChartChoice}
          artifactBase={artifactBase}
          onTypeConfirm={handleTypeConfirm}
          onPlotLater={handlePlotLater}
        />
      )}
    </div>
  );

  const workspacePane = (
    <WorkspacePanel
      sessionId={activeChat?.sessionId ?? ""}
      workspaces={sessionWorkspaces}
      activeId={activeWorkspace?.datasetId ?? null}
      uploading={uploading}
      onActivate={handleActivateWorkspace}
      onUpload={(file) => requestUpload(file)}
      onSetColumnType={handleSetColumnType}
      onSetColumnTypes={handleSetColumnTypes}
      onSuggestTypes={handleSuggestTypes}
      suggesting={suggesting}
      columnSuggestions={columnSuggestions ?? undefined}
      onClearOutputs={activeChat ? () => void handleClearOutputs() : undefined}
      clearDisabled={phase === "executing"}
      onRestyleChart={(stepIndex, chartType, style, method) =>
        handlePlotLater(stepIndex, chartType, style, method)
      }
    />
  );

  const builderPane = (
    <ChainBuilder
      sessionId={activeChat?.sessionId ?? ""}
      columns={Object.keys(activeWorkspace?.profile.columns ?? {})}
      columnTypes={Object.fromEntries(
        Object.entries(activeWorkspace?.profile.columns ?? {}).map(([name, col]) => [name, col.type])
      )}
      busy={phase === "thinking" || phase === "executing"}
      importSteps={activeChat ? latestPlanSteps(messages) : null}
      onRun={(steps) => {
        sendWs({ type: "run_chain", steps });
        setActiveTab("workspace");
      }}
    />
  );

  if (authNeeded) {
    return (
      <div className="flex h-full items-center justify-center bg-surface-page bg-grid-page p-6">
        <form
          data-testid="login-card"
          className="w-full max-w-sm space-y-3 rounded-2xl bg-surface-card p-6 shadow-card"
          onSubmit={(event) => {
            event.preventDefault();
            void handleLogin(
              (event.currentTarget.elements.namedItem("username") as HTMLInputElement).value,
              (event.currentTarget.elements.namedItem("password") as HTMLInputElement).value
            );
          }}
        >
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-cyan/15 ring-1 ring-primary-cyan/30">
              <BarChart3 className="h-5 w-5 text-primary-cyan" />
            </div>
            <h1 className="font-display text-base font-bold text-ink">MedSta 课题组工作台</h1>
          </div>
          <p className="text-xs leading-relaxed text-ink-muted">本服务已启用多用户模式，请使用课题组账号登录。</p>
          <label htmlFor="login-username" className="sr-only">用户名</label>
          <input
            id="login-username"
            name="username"
            placeholder="用户名"
            autoComplete="username"
            className="min-h-11 w-full rounded-lg border border-ink/15 bg-white px-3 py-2 text-base"
          />
          <label htmlFor="login-password" className="sr-only">密码</label>
          <input
            id="login-password"
            name="password"
            type="password"
            placeholder="密码"
            autoComplete="current-password"
            className="min-h-11 w-full rounded-lg border border-ink/15 bg-white px-3 py-2 text-base"
          />
          {loginError && <p className="text-xs text-danger">{loginError}</p>}
          <button
            type="submit"
            className="min-h-11 w-full cursor-pointer rounded-xl bg-primary px-4 py-2 text-sm font-medium text-white transition-colors duration-200 hover:bg-primary-hover"
          >
            登录
          </button>
        </form>
      </div>
    );
  }

  const stageIndex = analysisStageIndex({
    hasData: Boolean(activeChat?.datasetId),
    phase,
    hasTypeReview: typeReview != null,
    hasPlan: messages.some((item) => item.kind === "plan"),
  });

  return (
    <div className="flex h-full flex-col bg-surface-page bg-grid-page">
      <a
        href="#workbench"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-white focus:px-3 focus:py-2 focus:text-sm focus:text-primary-dark"
      >
        跳到工作台
      </a>
      <header className="z-40 shrink-0 border-b border-ink/10 bg-white/95">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2">
          <div className="flex shrink-0 items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-white">
              <BarChart3 className="h-5 w-5" aria-hidden="true" />
            </div>
            <div className="leading-tight">
              <span className="font-display block whitespace-nowrap text-base font-bold tracking-tightest text-primary-dark">
                MedSta
              </span>
              <span className="whitespace-nowrap text-[11px] text-ink-muted">临床统计分析</span>
            </div>
          </div>
          {activeChat && (
            <span
              className={`inline-flex min-h-11 items-center gap-1.5 rounded-lg px-2 text-xs font-medium ${
                connStatus === "connected"
                  ? "text-ink-muted"
                  : "animate-breathe bg-warn/10 text-warn"
              }`}
              title={connStatus === "connected" ? "WebSocket 已连接" : "连接断开，正在自动重连"}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  connStatus === "connected" ? "bg-ok" : "bg-warn"
                }`}
              />
              {connStatus === "connected" ? "已连接" : "重连中…"}
            </span>
          )}
          <button
            onClick={() => setCapabilitiesOpen(true)}
            className="ml-auto inline-flex min-h-11 cursor-pointer items-center gap-1.5 rounded-lg border border-ink/15 px-3 text-xs font-medium text-primary-dark transition-colors duration-200 hover:bg-primary-soft"
          >
            <Boxes className="h-3.5 w-3.5" aria-hidden="true" />
            能力
          </button>
          <div className="flex w-full min-w-0 basis-full items-center gap-1 overflow-x-auto rounded-lg bg-surface-page p-1 lg:ml-auto lg:w-auto lg:basis-auto">
            {[
              { key: "chat", label: `会话（${chatSessions.length}）`, icon: MessagesSquare },
              { key: "workspace", label: `工作区（${sessionWorkspaces.length}）`, icon: BarChart3 },
              { key: "builder", label: "工具装配", icon: Wrench },
            ].map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                onClick={() => {
                  const next = key as "chat" | "workspace" | "builder";
                  setActiveTab(next);
                  setFocusedPane((prev) => (prev === next ? null : next));
                }}
                className={`inline-flex min-h-11 shrink-0 cursor-pointer items-center gap-1.5 rounded-md px-3 text-xs font-medium transition-colors duration-200 ${
                  activeTab === key
                    ? "bg-primary text-white"
                    : "text-ink-muted hover:bg-white hover:text-primary-dark"
                }`}
              >
                <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                {label}
              </button>
            ))}
          </div>
        </div>
        <AnalysisStageRail current={stageIndex} />
      </header>

      {isDesktop && focusedPane === null ? (
        <main id="workbench" className="flex min-h-0 flex-1">
          <section
            style={{ width: chatWidth }}
            className="flex min-h-0 shrink-0 flex-col border-ink/8 bg-surface-page lg:border-r"
          >
            {chatPane}
          </section>
          <ResizeHandle onPointerDown={startDrag("chat")} label="调整会话区宽度" />
          <section className="flex min-h-0 flex-1 flex-col bg-surface-card/60">
            {workspacePane}
          </section>
          <ResizeHandle onPointerDown={startDrag("builder")} label="调整工具装配区宽度" />
          <section
            style={{ width: builderWidth }}
            className="flex min-h-0 shrink-0 flex-col bg-surface-card/60"
          >
            {builderPane}
          </section>
        </main>
      ) : isDesktop ? (
        <main id="workbench" className="flex min-h-0 flex-1">
          <section
            className={`flex min-h-0 w-full flex-col bg-surface-card/60 ${
              activeTab === "chat" ? "flex" : "hidden"
            }`}
          >
            {chatPane}
          </section>
          <section
            className={`flex min-h-0 w-full flex-col bg-surface-card/60 ${
              activeTab === "workspace" ? "flex" : "hidden"
            }`}
          >
            {workspacePane}
          </section>
          <section
            className={`flex min-h-0 w-full flex-col bg-surface-card/60 ${
              activeTab === "builder" ? "flex" : "hidden"
            }`}
          >
            {builderPane}
          </section>
        </main>
      ) : (
        <main id="workbench" className="flex min-h-0 flex-1 flex-col">
          <section
            className={`flex min-h-0 flex-1 flex-col border-ink/8 bg-surface-page ${
              activeTab === "chat" ? "flex" : "hidden"
            }`}
          >
            {chatPane}
          </section>
          <section
            className={`flex min-h-0 flex-1 flex-col bg-surface-card/60 ${
              activeTab === "workspace" ? "flex" : "hidden"
            }`}
          >
            {workspacePane}
          </section>
          <section
            className={`flex min-h-0 flex-1 flex-col bg-surface-card/60 ${
              activeTab === "builder" ? "flex" : "hidden"
            }`}
          >
            {builderPane}
          </section>
        </main>
      )}

      <CapabilityDrawer open={capabilitiesOpen} onClose={() => setCapabilitiesOpen(false)} />

      {pendingUpload && activeChat && (
        <UploadChoiceDialog
          filename={pendingUpload.name}
          sessionName={activeChat.name}
          onChoose={releasePendingUpload}
          onCancel={() => releasePendingUpload("cancel")}
        />
      )}
      {dragOver && (
        <div
          data-testid="drop-overlay"
          className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center bg-primary-dark/55 backdrop-blur-[2px]"
        >
          <div className="animate-fade-in-up rounded-2xl border-2 border-dashed border-primary bg-white px-10 py-8 text-center shadow-pop">
            <CloudUpload className="mx-auto h-10 w-10 text-primary" aria-hidden="true" />
            <p className="mt-2 text-base font-semibold text-primary-dark">松开鼠标导入数据文件</p>
            <p className="mt-1 text-xs text-ink-muted">支持 CSV / Excel（.csv / .xlsx / .xls），可一次多个</p>
          </div>
        </div>
      )}
    </div>
  );
}

/** 入口包装：渲染异常时显示可恢复错误卡而非白屏（039） */
export function AppWithBoundary() {
  return (
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  );
}
