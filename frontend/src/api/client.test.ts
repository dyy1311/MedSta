import { describe, expect, it, vi } from "vitest";
import {
  artifactUrl,
  connectSession,
  createSession,
  fetchCapabilities,
  updateColumnType,
  uploadData,
} from "./client";
import type { WsEvent } from "../types";
import {
  CAPABILITIES,
  FakeWebSocket,
  PROFILE,
  installFakeWebSocket,
  jsonResponse,
  mockFetch,
} from "../test/mocks";

describe("client REST 契约", () => {
  it("fetchCapabilities 读取 /capabilities 的 JSON", async () => {
    const fetchSpy = mockFetch([
      { path: "/capabilities", method: "GET", respond: () => jsonResponse(CAPABILITIES) },
    ]);

    const data = await fetchCapabilities();

    expect(data.tools[0].name).toBe("describe");
    // 044：apiFetch 统一携带认证头（匿名时为空对象）
    expect(fetchSpy).toHaveBeenCalledWith("/capabilities", { headers: {} });
  });

  it("fetchCapabilities 在非 JSON 响应时给出可诊断错误", async () => {
    mockFetch([
      {
        path: "/capabilities",
        method: "GET",
        respond: () =>
          new Response("<html>proxy error</html>", {
            status: 502,
            headers: { "Content-Type": "text/html" },
          }),
      },
    ]);

    await expect(fetchCapabilities()).rejects.toThrow(/HTTP 502/);
  });

  it("createSession 使用 POST /sessions", async () => {
    const fetchSpy = mockFetch([
      {
        path: "/sessions",
        method: "POST",
        respond: () => jsonResponse({ session_id: "s1", status: "discussing" }),
      },
    ]);

    await expect(createSession()).resolves.toEqual({ session_id: "s1", status: "discussing" });
    expect(fetchSpy).toHaveBeenCalledWith("/sessions", {
      method: "POST",
      headers: {},
    });
  });

  it("uploadData 以 multipart 提交文件并返回画像", async () => {
    let received: FormData | null = null;
    mockFetch([
      {
        path: "/sessions/s1/data",
        method: "POST",
        respond: (body) => {
          received = body as FormData;
          return jsonResponse({ type: "data_profile", dataset_id: "d1", name: "d.csv", profile: PROFILE });
        },
      },
    ]);
    const file = new File(["a,b\n1,2\n"], "d.csv", { type: "text/csv" });

    const result = await uploadData("s1", file);

    expect(result.dataset_id).toBe("d1");
    expect(received).toBeInstanceOf(FormData);
    expect((received as unknown as FormData).get("file")).toBe(file);
  });

  it("uploadData 把后端 detail 透出为错误文案", async () => {
    mockFetch([
      {
        path: "/sessions/s1/data",
        method: "POST",
        respond: () => jsonResponse({ detail: "不支持的文件类型：.txt" }, 400),
      },
    ]);

    await expect(uploadData("s1", new File(["x"], "a.txt"))).rejects.toThrow("不支持的文件类型：.txt");
  });

  it("updateColumnType 用 PATCH 提交列与类型", async () => {
    let payload: unknown = null;
    mockFetch([
      {
        path: "/sessions/s1/workspace/d1/columns",
        method: "PATCH",
        respond: (body) => {
          payload = JSON.parse(String(body));
          return jsonResponse({ type: "data_profile", dataset_id: "d1", profile: PROFILE });
        },
      },
    ]);

    const result = await updateColumnType("s1", "d1", "value", "ordinal");

    expect(payload).toEqual({ column: "value", type: "ordinal" });
    expect(result.profile.row_count).toBe(6);
  });

  it("updateColumnType 失败时抛错（不静默吞掉）", async () => {
    mockFetch([
      {
        path: "/sessions/s1/workspace/d1/columns",
        method: "PATCH",
        respond: () => jsonResponse({ detail: "非法列类型" }, 400),
      },
    ]);

    await expect(updateColumnType("s1", "d1", "value", "banana")).rejects.toThrow("400");
  });

  it("artifactUrl 指向 /data 静态目录", () => {
    expect(artifactUrl("s1", "chart.png")).toBe("/data/s1/artifacts/chart.png");
  });
});

describe("client WebSocket 契约", () => {
  it("按当前 host 建立连接并转发解析后的事件", async () => {
    installFakeWebSocket();
    const events: WsEvent[] = [];
    const onOpen = vi.fn();

    connectSession("s1", (event) => events.push(event), onOpen);
    const socket = FakeWebSocket.latest();
    await Promise.resolve();

    expect(socket.url).toBe(`ws://${window.location.host}/ws/s1`);
    expect(onOpen).toHaveBeenCalled();

    socket.emit({ type: "progress", stage: "thinking" });
    expect(events[0]).toEqual({ type: "progress", stage: "thinking" });
  });

  it("坏 JSON 不抛异常（只记录错误）", () => {
    installFakeWebSocket();
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const onEvent = vi.fn();

    connectSession("s1", onEvent);
    FakeWebSocket.latest().emitRaw("{not-json");

    expect(onEvent).not.toHaveBeenCalled();
    expect(errorSpy).toHaveBeenCalled();
  });

  it("仅在 OPEN 态发送；关闭后发送不抛异常", () => {
    installFakeWebSocket();
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const connection = connectSession("s1", () => {});

    connection.send({ type: "chat", content: "hi" });
    expect(FakeWebSocket.latest().sent).toEqual([{ type: "chat", content: "hi" }]);

    FakeWebSocket.latest().readyState = FakeWebSocket.CLOSED;
    connection.send({ type: "chat", content: "later" });

    expect(FakeWebSocket.latest().sent).toHaveLength(1);
    expect(errorSpy).toHaveBeenCalled();

    connection.close();
    expect(FakeWebSocket.latest().readyState).toBe(FakeWebSocket.CLOSED);
  });

  it("035: 非手动断线自动重连并携带 resume+last_seq，状态回调驱动徽标", async () => {
    vi.useFakeTimers();
    installFakeWebSocket();
    const statuses: string[] = [];
    const lastSeq: number | null = 7;
    const connection = connectSession("s1", () => undefined, undefined, {
      getLastSeq: () => lastSeq,
      onStatus: (status) => statuses.push(status),
    });

    // 首次连接成功
    await vi.advanceTimersByTimeAsync(0);
    expect(FakeWebSocket.latest().url).toBe(`ws://${window.location.host}/ws/s1`);
    expect(statuses).toEqual(["connected"]);

    // 非手动断线 → reconnecting → 1s 后重连成功 → resume 携带 last_seq
    FakeWebSocket.latest().onclose?.();
    expect(statuses.at(-1)).toBe("reconnecting");
    await vi.advanceTimersByTimeAsync(1000);

    const reconnected = FakeWebSocket.latest();
    expect(reconnected).not.toBeUndefined();
    const resume = reconnected.sent.find((event) => event.type === "resume");
    expect(resume).toEqual({ type: "resume", last_seq: 7 });
    expect(statuses.at(-1)).toBe("connected");

    // 事件帧透传（seq 由 App 层记录，client 只转发）
    reconnected.emit({ type: "plan", seq: 8 });
    connection.close(); // 手动关闭后不再重连
    vi.useRealTimers();
  });

  it("035: 手动 close 不触发重连", async () => {
    vi.useFakeTimers();
    installFakeWebSocket();
    const statuses: string[] = [];
    const connection = connectSession("s1", () => undefined, undefined, {
      onStatus: (status) => statuses.push(status),
    });
    await vi.advanceTimersByTimeAsync(0);

    connection.close();
    const count = FakeWebSocket.instances.length;
    await vi.advanceTimersByTimeAsync(30000);
    expect(FakeWebSocket.instances.length).toBe(count);
    expect(statuses).toEqual(["connected"]);

    vi.useRealTimers();
  });

  it("035: 重连退避指数增长（连续失败 1s→2s），成功后重置", async () => {
    vi.useFakeTimers();
    installFakeWebSocket();
    const connection = connectSession("s1", () => undefined);

    await vi.advanceTimersByTimeAsync(0);
    // 第一次断线（此前连接成功）：1s 后重连
    FakeWebSocket.latest().onclose?.();
    await vi.advanceTimersByTimeAsync(999);
    expect(FakeWebSocket.instances.length).toBe(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(FakeWebSocket.instances.length).toBe(2);

    // 第二次断线发生在成功连接后：退避重置回 1s
    FakeWebSocket.latest().onclose?.();
    await vi.advanceTimersByTimeAsync(999);
    expect(FakeWebSocket.instances.length).toBe(2);
    await vi.advanceTimersByTimeAsync(1);
    expect(FakeWebSocket.instances.length).toBe(3);

    // 连续失败：同一实例同步两次 onclose → attempt 1→2，退避 1s→2s
    const failing = FakeWebSocket.latest();
    failing.onclose?.();
    failing.onclose?.();
    await vi.advanceTimersByTimeAsync(999);
    expect(FakeWebSocket.instances.length).toBe(3); // 2s timer 未到
    await vi.advanceTimersByTimeAsync(1);
    expect(FakeWebSocket.instances.length).toBe(4); // 1s timer 触发
    await vi.advanceTimersByTimeAsync(999);
    expect(FakeWebSocket.instances.length).toBe(4); // 2s timer 未到
    await vi.advanceTimersByTimeAsync(1);
    expect(FakeWebSocket.instances.length).toBe(5); // 2s timer 触发

    connection.close();
    vi.useRealTimers();
  });
});
