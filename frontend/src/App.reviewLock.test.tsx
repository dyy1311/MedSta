import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { FakeWebSocket, PROFILE, installFakeWebSocket, jsonResponse, mockFetch } from "./test/mocks";

/**
 * 用户实测：提交修正意见后没有反应，重复点「提交修正」还会撞 NO_ACTIVE_RUN。
 * 现在提交即锁定该审阅卡（后端会带着修正意见自动重出方案）。
 */

const REPORT = {
  report_id: "r1",
  summary: "描述性统计",
  steps: [
    {
      title: "主要指标分布描述",
      method: "describe",
      status: "success",
      result: {},
    },
  ],
};

function setupFetch() {
  return mockFetch([
    {
      path: "/sessions",
      method: "POST",
      respond: () => jsonResponse({ session_id: "s1", status: "discussing" }),
    },
    {
      path: "/sessions/s1/data",
      method: "POST",
      respond: () =>
        jsonResponse({ type: "data_profile", dataset_id: "d1", name: "cohort.csv", profile: PROFILE }),
    },
  ]);
}

async function openSession(container: HTMLElement) {
  fireEvent.click(screen.getByTitle("新建会话空间"));
  await screen.findByRole("button", { name: /^会话 1/ });
  const input = container.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(["group,value\n"], "cohort.csv")] } });
  await screen.findByText(/已绑定当前会话/);
}

beforeEach(() => {
  installFakeWebSocket();
  vi.spyOn(console, "error").mockImplementation(() => {});
});

describe("审阅卡提交修正", () => {
  it("提交后锁定卡片，重复点击不再发帧（避免 NO_ACTIVE_RUN）", async () => {
    setupFetch();
    const { container } = render(<App />);
    await openSession(container);

    act(() => {
      FakeWebSocket.latest().emit({ type: "review_request", report: REPORT, seq: 5 });
    });

    fireEvent.click(await screen.findByRole("button", { name: /提出修正/ }));
    fireEvent.change(screen.getByPlaceholderText(/例如：不要用直方图/), {
      target: { value: "每个类别做一张图" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交修正" }));

    // 卡片锁定：显示已提交提示，修正入口消失
    expect(await screen.findByTestId("review-submitted")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "提交修正" })).not.toBeInTheDocument();

    const reviews = FakeWebSocket.latest().sent.filter((frame) => frame.type === "review");
    expect(reviews).toEqual([
      { type: "review", decision: "revise", content: "每个类别做一张图" },
    ]);
    // 修正意见同时进入会话气泡（可回放、可核对）
    expect(screen.getByText(/修正意见：每个类别做一张图/)).toBeInTheDocument();
  });

  it("后端回到讨论并重出方案后，新方案卡正常出现", async () => {
    setupFetch();
    const { container } = render(<App />);
    await openSession(container);

    act(() => {
      FakeWebSocket.latest().emit({ type: "review_request", report: REPORT, seq: 5 });
    });
    fireEvent.click(await screen.findByRole("button", { name: /提出修正/ }));
    fireEvent.change(screen.getByPlaceholderText(/例如：不要用直方图/), {
      target: { value: "改成按类别分面" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交修正" }));

    act(() => {
      FakeWebSocket.latest().emit({
        type: "back_to_discussion",
        message: "已记录修正意见，正在按修正重新生成方案…",
        seq: 6,
      });
      FakeWebSocket.latest().emit({
        type: "plan",
        message: "已按修正调整：每个类别分面绘制",
        steps: [
          {
            title: "分面分布",
            method: "describe",
            target_columns: ["value"],
            chart_type: "histogram",
            params: { group_by: "group" },
            rationale: "按类别看分布",
          },
        ],
        options: [{ id: "go", label: "按此执行", action: "confirm" }],
        seq: 7,
      });
    });

    expect(await screen.findByText("已按修正调整：每个类别分面绘制")).toBeInTheDocument();
    expect(screen.getByText(/已记录修正意见，正在按修正重新生成方案/)).toBeInTheDocument();
  });
});
