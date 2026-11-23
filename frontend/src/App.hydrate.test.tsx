import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { FakeWebSocket, installFakeWebSocket, jsonResponse, mockFetch, PROFILE, REPORT } from "./test/mocks";

/**
 * 刷新后「工作区 ↔ 会话区」同源：
 * 快照接口补齐右栏，事件流只做增量；工作区按会话过滤，切会话不得串台。
 */

const REPORT_WITH_ID = { ...REPORT, report_id: "r1" };

interface SessionItem {
  session_id: string;
  dataset_id: string | null;
  name: string;
  status: string;
}

function snapshotOf(sessionId: string, datasetId: string | null, name: string, report: unknown) {
  return {
    session_id: sessionId,
    status: report ? "plan_confirmed" : "discussing",
    active_dataset_id: datasetId,
    datasets: datasetId
      ? [
          {
            dataset_id: datasetId,
            name,
            profile: PROFILE,
            type_confirmed: true,
            active: true,
          },
        ]
      : [],
    report,
    report_id: report ? "r1" : null,
  };
}

function setup(sessions: SessionItem[], snapshots: Record<string, () => unknown>) {
  mockFetch([
    { path: "/sessions", method: "GET", respond: () => jsonResponse({ sessions }) },
    {
      path: "/capabilities",
      method: "GET",
      respond: () => jsonResponse({ tools: [], charts: [], planned: [], methodology: "m" }),
    },
    { path: "/templates", method: "GET", respond: () => jsonResponse({ templates: [] }) },
    ...Object.entries(snapshots).map(([path, respond]) => ({
      path,
      method: "GET",
      respond: () => jsonResponse(respond()),
    })),
  ]);
}

beforeEach(() => {
  installFakeWebSocket();
  localStorage.clear();
  vi.spyOn(console, "error").mockImplementation(() => {});
});

describe("App 刷新恢复（工作区与会话区同源）", () => {
  it("刷新后自动回到会话，右栏由快照恢复画像与报告，回放重复帧不堆叠", async () => {
    setup([{ session_id: "s1", dataset_id: "d1", name: "cohort.csv", status: "delivered" }], {
      "/sessions/s1/workspace": () => snapshotOf("s1", "d1", "cohort.csv", REPORT_WITH_ID),
    });

    render(<App />);

    // 不需要点击会话 Tab：自动选中 → WS 连接 → 右栏与左栏同属 s1
    expect(await screen.findByText("已连接")).toBeInTheDocument();
    expect(await screen.findByText("数据画像")).toBeInTheDocument();
    expect(await screen.findByText("统计表交付（1）")).toBeInTheDocument();

    // 回放同一份报告（report_id 相同）不得堆出第二份
    act(() => {
      FakeWebSocket.latest().emit({ type: "review_request", report: REPORT_WITH_ID, seq: 5 });
    });
    expect(screen.getByText("统计表交付（1）")).toBeInTheDocument();
  });

  it("切到没有数据集的会话：右栏清空，不残留上一个会话的表与报告", async () => {
    setup(
      [
        { session_id: "s1", dataset_id: "d1", name: "cohort.csv", status: "delivered" },
        { session_id: "s2", dataset_id: null, name: "未绑定", status: "discussing" },
      ],
      {
        "/sessions/s1/workspace": () => snapshotOf("s1", "d1", "cohort.csv", REPORT_WITH_ID),
        "/sessions/s2/workspace": () => snapshotOf("s2", null, "未绑定", null),
      }
    );

    render(<App />);
    expect(await screen.findByText("统计表交付（1）")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^会话 2/ }));

    expect(
      await screen.findByText("上传数据并确认方案后，数据画像与图表将展示在这里")
    ).toBeInTheDocument();
    expect(screen.queryByText("统计表交付（1）")).not.toBeInTheDocument();
  });

  it("后端缺快照接口（旧进程 404）时给出可执行提示，而不是静默空白", async () => {
    mockFetch([
      {
        path: "/sessions",
        method: "GET",
        respond: () =>
          jsonResponse({
            sessions: [
              { session_id: "s1", dataset_id: "d1", name: "cohort.csv", status: "discussing" },
            ],
          }),
      },
      {
        path: "/capabilities",
        method: "GET",
        respond: () => jsonResponse({ tools: [], charts: [], planned: [], methodology: "m" }),
      },
      { path: "/templates", method: "GET", respond: () => jsonResponse({ templates: [] }) },
      {
        path: "/sessions/s1/workspace",
        method: "GET",
        respond: () => jsonResponse({ detail: "Not Found" }, 404),
      },
    ]);

    render(<App />);

    expect(
      await screen.findByText(/后端未提供工作区快照接口（404）/)
    ).toBeInTheDocument();
  });

  it("回放重放了历史 progress 帧：resumed 阶段校正后不卡在「执行中」", async () => {
    setup([{ session_id: "s1", dataset_id: "d1", name: "cohort.csv", status: "discussing" }], {
      "/sessions/s1/workspace": () => snapshotOf("s1", "d1", "cohort.csv", null),
    });

    render(<App />);
    expect(await screen.findByText("已连接")).toBeInTheDocument();
    const socket = FakeWebSocket.latest();

    // 事件流里的历史进度帧（进程重启后任务其实已不在）
    act(() => {
      socket.emit({ type: "progress", stage: "executing", step: 1, total: 2, title: "分布统计", seq: 1 });
    });
    const input = screen.getByPlaceholderText("描述分析目标，或对方案提出修正意见…");
    expect(input).toBeDisabled();

    // 服务端 resume 声明的当前阶段才是真相：回到讨论态，输入必须可用
    act(() => {
      socket.emit({ type: "resumed", stage: "discussion", seq: 2 });
    });
    expect(
      screen.getByPlaceholderText("描述分析目标，或对方案提出修正意见…")
    ).not.toBeDisabled();
  });

  it("报告比画像先到（刷新回放）：先挂占位，快照到达后迁移到真实数据集", async () => {
    const gate: { release?: () => void } = {};
    mockFetch([
      {
        path: "/sessions",
        method: "GET",
        respond: () =>
          jsonResponse({
            sessions: [
              { session_id: "s1", dataset_id: "d1", name: "cohort.csv", status: "plan_confirmed" },
            ],
          }),
      },
      {
        path: "/capabilities",
        method: "GET",
        respond: () => jsonResponse({ tools: [], charts: [], planned: [], methodology: "m" }),
      },
      { path: "/templates", method: "GET", respond: () => jsonResponse({ templates: [] }) },
      {
        path: "/sessions/s1/workspace",
        method: "GET",
        // 快照挂起，保证回放帧先到（模拟事件流比 REST 快）
        respond: () =>
          new Promise<Response>((resolve) => {
            gate.release = () =>
              resolve(jsonResponse(snapshotOf("s1", "d1", "cohort.csv", null)));
          }),
      },
    ]);

    render(<App />);
    expect(await screen.findByText("已连接")).toBeInTheDocument();

    act(() => {
      FakeWebSocket.latest().emit({ type: "review_request", report: REPORT_WITH_ID, seq: 3 });
    });
    expect(await screen.findByText("统计表交付（1）")).toBeInTheDocument();

    act(() => {
      gate.release?.();
    });

    // 占位迁移到真实数据集：统计表仍只有一份，画像换成真实表
    expect(await screen.findByText("cohort.csv")).toBeInTheDocument();
    expect(screen.getByText("统计表交付（1）")).toBeInTheDocument();
  });
});
