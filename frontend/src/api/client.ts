import type { Capabilities, TableProfile, WorkspaceSnapshot, WsEvent } from "../types";

/** 044：登录令牌（localStorage）；所有请求与 WS 自动携带 */
export function authHeaders(): Record<string, string> {
  const token = localStorage.getItem("medsta_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(path, {
    ...init,
    headers: { ...authHeaders(), ...(init.headers ?? {}) },
  });
}

export async function fetchCapabilities(): Promise<Capabilities> {
  const response = await apiFetch("/capabilities");
  const contentType = response.headers.get("content-type") ?? "";
  if (!response.ok || !contentType.includes("application/json")) {
    throw new Error(`能力目录接口异常：HTTP ${response.status} (${contentType || "无 content-type"})`);
  }
  return response.json();
}

export async function createSession(): Promise<{ session_id: string; status: string }> {
  const resp = await apiFetch("/sessions", { method: "POST" });
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(String((detail as Record<string, string>).detail ?? "创建会话失败"));
  }
  return resp.json();
}

/** 批次12 删除会话：后端一并清理快照/事件流/图表产物。 */
export async function deleteSession(sessionId: string): Promise<void> {
  const resp = await apiFetch(`/sessions/${sessionId}`, { method: "DELETE" });
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(String((detail as Record<string, string>).detail ?? "删除会话失败"));
  }
}

/** 批次13 批量清理重复会话：按绑定文件名分组保留最新，其余删除（仅本人会话）。 */
export async function cleanupDuplicateSessions(): Promise<{
  deleted: string[];
  kept: string[];
  skipped: string[];
}> {
  const resp = await apiFetch("/sessions/cleanup_duplicates", { method: "POST" });
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(String((detail as Record<string, string>).detail ?? "清理重复会话失败"));
  }
  return resp.json();
}

export async function uploadData(
  sessionId: string,
  file: File
): Promise<{ type: string; dataset_id: string; name: string; profile: TableProfile }> {
  const form = new FormData();
  form.append("file", file);
  const resp = await apiFetch(`/sessions/${sessionId}/data`, {
    method: "POST",
    body: form,
  });
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(String((detail as Record<string, string>).detail ?? "上传失败"));
  }
  return resp.json();
}

export type SendFn = (event: Record<string, unknown>) => void;

export interface SessionConnection {
  send: SendFn;
  close: () => void;
}

export interface ConnectOptions {
  /** 断线重连时携带的客户端已收最大事件 seq（缺口补发） */
  getLastSeq?: () => number | null;
  /** 连接状态回调：connected（含重连成功）/ reconnecting */
  onStatus?: (status: "connected" | "reconnecting") => void;
  /** 首连是否也发 resume+last_seq（缺省仅在有已知 last_seq 时发）。
   *  刷新/重启后恢复的会话应为 true：last_seq 取 0 全量回放，重建聊天上下文。 */
  shouldResume?: () => boolean;
  /** 令牌失效（4401/4403）：停止重连并交给上层显示登录卡。
   *  令牌在服务端内存表中，后端重启后全部失效——无限退避重连没有意义。 */
  onAuthError?: () => void;
}

/**
 * 建立会话 WS 连接，非手动断线自动重连（指数退避 1s→2s→…上限 10s）。
 * 重连成功后发送 {type:"resume", last_seq}，服务端补发缺口帧（035）。
 * 手动 close() 不触发重连。
 */
export function connectSession(
  sessionId: string,
  onEvent: (event: WsEvent) => void,
  onOpen?: () => void,
  options: ConnectOptions = {}
): SessionConnection {
  const { getLastSeq, onStatus, shouldResume, onAuthError } = options;
  let manual = false;
  let attempt = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let socket: WebSocket | null = null;

  const connect = () => {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const stored = localStorage.getItem("medsta_token");
    const auth = stored ? `?token=${encodeURIComponent(stored)}` : "";
    socket = new WebSocket(`${proto}://${window.location.host}/ws/${sessionId}${auth}`);
    socket.onopen = () => {
      attempt = 0;
      onStatus?.("connected");
      const lastSeq = getLastSeq?.();
      const wantResume = shouldResume ? shouldResume() : lastSeq != null;
      if (wantResume) {
        // last_seq 缺省 0：首连回放全部历史帧（刷新/重启后重建聊天上下文）
        socket?.send(JSON.stringify({ type: "resume", last_seq: lastSeq ?? 0 }));
      }
      onOpen?.();
    };
    socket.onmessage = (raw) => {
      try {
        onEvent(JSON.parse(raw.data) as WsEvent);
      } catch (err) {
        console.error("无法解析服务端消息", err);
      }
    };
    socket.onerror = () => console.error("WebSocket 连接错误");
    socket.onclose = (event?: { code?: number }) => {
      if (manual) return;
      // 4401/4403 = 令牌缺失/失效（服务端 close code）：重连也不会成功
      if (event?.code === 4401 || event?.code === 4403) {
        manual = true;
        onStatus?.("reconnecting");
        onAuthError?.();
        return;
      }
      attempt += 1;
      onStatus?.("reconnecting");
      timer = setTimeout(connect, Math.min(10000, 1000 * 2 ** (attempt - 1)));
    };
  };
  connect();

  return {
    send: (event) => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(event));
      } else {
        console.error("WebSocket 未就绪，消息未发送");
      }
    },
    close: () => {
      manual = true;
      if (timer !== null) clearTimeout(timer);
      socket?.close();
    },
  };
}

/** 044：图片/下载直链无法携带 Authorization 头——与 WS 同口径追加 ?token= */
export function withToken(url: string): string {
  const stored = localStorage.getItem("medsta_token");
  if (!stored) return url;
  return `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(stored)}`;
}

export function artifactUrl(sessionId: string, filename: string): string {
  return withToken(`/data/${sessionId}/artifacts/${filename}`);
}


/** 切换会话的激活工作区：宿主持久化 active_dataset_id，后续分析与画像以它为准。
 *  用 REST（而非 WS）是为了与 WS 连接状态解耦——跨会话切标签时连接正在重连。 */
export async function fetchWorkspace(sessionId: string): Promise<WorkspaceSnapshot> {
  const resp = await apiFetch(`/sessions/${sessionId}/workspace`);
  if (!resp.ok) {
    throw new Error(`工作区快照加载失败（${resp.status}）`);
  }
  return resp.json();
}

/** 清空工作区既往产出：图表/统计表/执行报告删除，导入表格保留。 */
export async function clearWorkspaceOutputs(
  sessionId: string
): Promise<{ session_id: string; outputs_cleared_seq: number | null }> {
  const resp = await apiFetch(`/sessions/${sessionId}/workspace/outputs`, { method: "DELETE" });
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(String((detail as Record<string, string>).detail ?? "清空产出失败"));
  }
  return resp.json();
}

export async function activateWorkspace(
  sessionId: string,
  datasetId: string
): Promise<{ type: string; dataset_id: string; name: string; type_confirmed: boolean; profile: TableProfile }> {
  const resp = await apiFetch(`/sessions/${sessionId}/workspace/${datasetId}/activate`, {
    method: "POST",
  });
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(String((detail as Record<string, string>).detail ?? "切换工作区失败"));
  }
  return resp.json();
}

export function updateColumnType(
  sessionId: string,
  datasetId: string,
  column: string,
  type: string
): Promise<{ type: string; dataset_id: string; profile: TableProfile }> {
  return apiFetch(`/sessions/${sessionId}/workspace/${datasetId}/columns`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ column, type }),
  }).then((response) => {
    if (!response.ok) throw new Error(`type edit failed: ${response.status}`);
    return response.json();
  });
}

/** 批量列类型修改：一次请求多列，整体校验（非法列/类型整体拒绝） */
export function updateColumnTypes(
  sessionId: string,
  datasetId: string,
  types: Record<string, string>,
  /** 变更来源：ai=采纳模型建议（后端据此在会话区生成对应提示） */
  source: "manual" | "ai" = "manual"
): Promise<{ type: string; dataset_id: string; profile: TableProfile }> {
  return apiFetch(`/sessions/${sessionId}/workspace/${datasetId}/columns`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ types, source }),
  }).then(async (response) => {
    if (!response.ok) {
      const detail = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(String((detail as Record<string, string>).detail ?? "批量修改失败"));
    }
    return response.json();
  });
}

/** 044：多用户登录（MEDSTA_USERS 未配置时后端 404，前端走匿名模式） */
export async function login(
  username: string,
  password: string
): Promise<{ token: string; username: string }> {
  const resp = await fetch("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!resp.ok) throw new Error(resp.status === 401 ? "用户名或密码错误" : `登录失败：HTTP ${resp.status}`);
  return resp.json();
}

/** 044：当前用户的会话列表（后端重启恢复的会话由此发现） */
export async function listSessions(): Promise<
  { session_id: string; name: string | null; status: string; dataset_id: string | null }[]
> {
  const resp = await apiFetch("/sessions");
  if (resp.status === 401) throw new Error("AUTH_REQUIRED");
  if (!resp.ok) throw new Error(`会话列表接口异常：HTTP ${resp.status}`);
  const payload = (await resp.json()) as {
    sessions: { session_id: string; name: string | null; status: string; dataset_id: string | null }[];
  };
  return payload.sessions ?? [];
}

/** 内置推荐工作链模板（按统计 skills 预设，节点均为注册表工具） */
export interface BuiltinRecipe {
  id: string;
  title: string;
  description: string;
  skill: string;
  steps: {
    title: string;
    method: string;
    chart_type: string;
    targets: string[];
    params: Record<string, string>;
    fixed: Record<string, unknown>;
    rationale: string;
    method_available: boolean;
  }[];
  slots: { slot: string; label: string }[];
}

export async function fetchBuiltinRecipes(): Promise<BuiltinRecipe[]> {
  const resp = await apiFetch("/templates/builtin");
  if (!resp.ok) throw new Error(`推荐模板加载失败（${resp.status}）`);
  const payload = (await resp.json()) as { recipes: BuiltinRecipe[] };
  return payload.recipes ?? [];
}

/** AI 一键匹配：模板占位 → 当前数据的真实列（失败自动回退规则匹配） */
export async function matchChainRecipe(
  sessionId: string,
  recipeId: string,
  useAi = true
): Promise<{
  recipe_id: string;
  title: string;
  ai: boolean;
  steps: { title: string; method: string; target_columns: string[]; chart_type: string; params: Record<string, unknown>; rationale: string }[];
  matched: { step: number; slot: string; column: unknown; by: string }[];
  warnings: string[];
}> {
  const resp = await apiFetch(`/sessions/${sessionId}/chain/match`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ recipe_id: recipeId, use_ai: useAi }),
  });
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({}));
    throw new Error(String((detail as { detail?: string }).detail ?? `匹配失败（${resp.status}）`));
  }
  return resp.json();
}
