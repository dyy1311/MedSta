import { vi } from "vitest";
import type {
  Capabilities,
  ExecutionReport,
  PlanEvent,
  TableProfile,
} from "../types";

/**
 * 只在网络边界替换 fetch/WebSocket；组件、状态机与事件映射均走真实实现。
 */

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export interface FetchRoute {
  path: string;
  method?: string;
  respond: (body: RequestInit["body"], url: string) => Response | Promise<Response>;
}

export function mockFetch(routes: FetchRoute[]) {
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url =
      typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    const method = (init?.method ?? "GET").toUpperCase();
    const path = url.split("?")[0];
    const route = routes.find(
      (candidate) =>
        candidate.path === path && (!candidate.method || candidate.method.toUpperCase() === method)
    );
    if (!route) throw new Error(`未桩接的请求：${method} ${url}`);
    return route.respond(init?.body, url);
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

export class FakeWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  static instances: FakeWebSocket[] = [];

  static reset() {
    FakeWebSocket.instances = [];
  }

  static latest(): FakeWebSocket {
    const socket = FakeWebSocket.instances.at(-1);
    if (!socket) throw new Error("尚未创建 WebSocket");
    return socket;
  }

  url: string;
  readyState = FakeWebSocket.OPEN;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  sent: Record<string, unknown>[] = [];

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
    queueMicrotask(() => this.onopen?.());
  }

  send(payload: string) {
    if (this.readyState !== FakeWebSocket.OPEN) throw new Error("socket 未就绪");
    this.sent.push(JSON.parse(payload) as Record<string, unknown>);
  }

  close() {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.();
  }

  emit(event: unknown) {
    this.onmessage?.({ data: JSON.stringify(event) });
  }

  emitRaw(data: string) {
    this.onmessage?.({ data });
  }
}

export function installFakeWebSocket() {
  FakeWebSocket.reset();
  vi.stubGlobal("WebSocket", FakeWebSocket);
}

export const PROFILE: TableProfile = {
  row_count: 6,
  column_count: 2,
  type_confirmed: false,
  columns: {
    group: {
      name: "group",
      type: "categorical",
      missing: 0,
      stats: { count: 6, distinct: 2, top: "A" },
    },
    value: {
      name: "value",
      type: "continuous",
      missing: 0,
      stats: {
        count: 6,
        mean: 4,
        median: 4,
        q25: 2.75,
        q75: 5.25,
        min: 1.5,
        max: 6.5,
      },
    },
  },
};

export const PLAN_EVENT: PlanEvent = {
  type: "plan",
  message: "先描述 value 的分布，再出直方图。",
  steps: [
    {
      step_id: "step_1",
      title: "分布统计",
      method: "describe",
      target_columns: ["value"],
      chart_type: "histogram",
      params: {},
      rationale: "连续变量先看分布",
    },
  ],
  options: [
    { id: "go", label: "按此执行", action: "confirm" },
    { id: "explain", label: "解释依据", action: "explain" },
  ],
};

export const REPORT: ExecutionReport = {
  steps: [
    {
      title: "分布统计",
      method: "describe",
      status: "success",
      artifact: "step_0_describe_histogram.png",
      table: {
        columns: ["column", "count", "mean", "median", "q25", "q75", "min", "max"],
        rows: [
          {
            column: "value",
            count: 6,
            mean: 4,
            median: 4,
            q25: 2.75,
            q75: 5.25,
            min: 1.5,
            max: 6.5,
          },
        ],
      },
      result: {
        strategy: {
          steps: ["正态性（Shapiro-Wilk）：p=0.5 → 正态"],
          final_method: "t",
          alternative: "次优：Mann-Whitney",
        },
      },
    },
  ],
};

export const CAPABILITIES: Capabilities = {
  tools: [
    {
      name: "describe",
      title: "描述性统计",
      category: "描述与质检",
      description: "数值列分布概览",
      task: "描述",
      applicability: "任何分析第一步",
      slots: [],
      params: [],
      charts: ["histogram", "boxplot"],
    },
  ],
  charts: [{ name: "histogram", label: "histogram" }],
  planned: [{ name: "survival_analysis", title: "生存分析", description: "Cox 与 RMST" }],
  methodology: "依据方法学流程图落地",
};
