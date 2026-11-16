import type { Capabilities, TableProfile, WsEvent } from "../types";

export async function fetchCapabilities(): Promise<Capabilities> {
  const response = await fetch("/capabilities");
  const contentType = response.headers.get("content-type") ?? "";
  if (!response.ok || !contentType.includes("application/json")) {
    throw new Error(`能力目录接口异常：HTTP ${response.status} (${contentType || "无 content-type"})`);
  }
  return response.json();
}

export function createSession(): Promise<{ session_id: string; status: string }> {
  return fetch("/sessions", { method: "POST" }).then((r) => r.json());
}

export async function uploadData(
  sessionId: string,
  file: File
): Promise<{ type: string; dataset_id: string; name: string; profile: TableProfile }> {
  const form = new FormData();
  form.append("file", file);
  const resp = await fetch(`/sessions/${sessionId}/data`, {
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
  const { getLastSeq, onStatus } = options;
  let manual = false;
  let attempt = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let socket: WebSocket | null = null;

  const connect = () => {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${proto}://${window.location.host}/ws/${sessionId}`);
    socket.onopen = () => {
      attempt = 0;
      onStatus?.("connected");
      const lastSeq = getLastSeq?.();
      if (lastSeq != null) {
        socket?.send(JSON.stringify({ type: "resume", last_seq: lastSeq }));
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
    socket.onclose = () => {
      if (manual) return;
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

export function artifactUrl(sessionId: string, filename: string): string {
  return `/data/${sessionId}/artifacts/${filename}`;
}


export function updateColumnType(
  sessionId: string,
  datasetId: string,
  column: string,
  type: string
): Promise<{ type: string; dataset_id: string; profile: TableProfile }> {
  return fetch(`/sessions/${sessionId}/workspace/${datasetId}/columns`, {
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
  types: Record<string, string>
): Promise<{ type: string; dataset_id: string; profile: TableProfile }> {
  return fetch(`/sessions/${sessionId}/workspace/${datasetId}/columns`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ types }),
  }).then(async (response) => {
    if (!response.ok) {
      const detail = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(String((detail as Record<string, string>).detail ?? "批量修改失败"));
    }
    return response.json();
  });
}
