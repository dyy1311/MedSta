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

export function connectSession(
  sessionId: string,
  onEvent: (event: WsEvent) => void,
  onOpen?: () => void
): SessionConnection {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${proto}://${window.location.host}/ws/${sessionId}`);
  socket.onopen = () => onOpen?.();
  socket.onmessage = (raw) => {
    try {
      onEvent(JSON.parse(raw.data) as WsEvent);
    } catch (err) {
      console.error("无法解析服务端消息", err);
    }
  };
  socket.onerror = () => console.error("WebSocket 连接错误");
  return {
    send: (event) => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(event));
      } else {
        console.error("WebSocket 未就绪，消息未发送");
      }
    },
    close: () => socket.close(),
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
