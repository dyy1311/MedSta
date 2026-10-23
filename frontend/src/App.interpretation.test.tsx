import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import {
  FakeWebSocket,
  PLAN_EVENT,
  PROFILE,
  REPORT,
  installFakeWebSocket,
  jsonResponse,
  mockFetch,
} from "./test/mocks";

const INTERPRETATION = {
  type: "interpretation",
  summary: "本次描述统计显示 value 分布较均匀。",
  steps: [{ step_index: 0, finding: "value 的中位数为 4（n=6）。", caveat: "" }],
  caveats: ["本次为探索性分析，未经 SAP 冻结与样本量论证。"],
  unverified_numbers: [],
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
    {
      path: "/capabilities",
      method: "GET",
      respond: () => jsonResponse({ tools: [], charts: [], planned: [], methodology: "" }),
    },
  ]);
}

async function openSessionWithData(container: HTMLElement) {
  fireEvent.click(screen.getByTitle("新建会话空间"));
  await screen.findByRole("button", { name: /^会话 1/ });

  const input = container.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(["group,value\n"], "cohort.csv")] } });
  await screen.findByText(/数据「cohort.csv」已绑定当前会话/);
}

function socket() {
  return FakeWebSocket.latest();
}

async function openReview() {
  const { container } = render(<App />);
  await openSessionWithData(container);
  act(() => {
    socket().emit({ ...PLAN_EVENT });
    socket().emit({ type: "review_request", report: REPORT });
  });
  await screen.findByText("执行完成，请审阅结果");
}

describe("App 结果解读与答疑", () => {
  beforeEach(() => {
    installFakeWebSocket();
    setupFetch();
    vi.restoreAllMocks();
  });

  it("解读事件补进最后一条审阅卡", async () => {
    await openReview();

    act(() => socket().emit(INTERPRETATION));

    expect(await screen.findByText("value 的中位数为 4（n=6）。")).toBeInTheDocument();
    expect(screen.getByText(/未经 SAP 冻结/)).toBeInTheDocument();
    // 解读不新增消息：审阅卡仍只有一张
    expect(screen.getAllByText("执行完成，请审阅结果")).toHaveLength(1);
  });

  it("答疑事件渲染为独立回答卡", async () => {
    await openReview();

    act(() =>
      socket().emit({
        type: "answer",
        answer: "该步骤只做描述统计，没有 p 值可解读。",
        caveats: ["如需推断需补充检验"],
        unverified_numbers: [],
      })
    );

    expect(await screen.findByText("答疑")).toBeInTheDocument();
    expect(screen.getByText("该步骤只做描述统计，没有 p 值可解读。")).toBeInTheDocument();
    expect(screen.getByText("· 如需推断需补充检验")).toBeInTheDocument();
  });
});
