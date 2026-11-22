import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { FakeWebSocket, PROFILE, installFakeWebSocket, jsonResponse, mockFetch } from "./test/mocks";

/**
 * 047 节点级交付：执行期逐节点展示结果/错误，失败节点可单点重跑或定点修正。
 * 用户痛点：整条链一次报错就得全部重来。
 */

function setupFetch() {
  let created = 0;
  return mockFetch([
    {
      path: "/sessions",
      method: "POST",
      respond: () => {
        created += 1;
        return jsonResponse({ session_id: `s${created}`, status: "discussing" });
      },
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

function socket() {
  return FakeWebSocket.latest();
}

const OK_STEP = {
  index: 0,
  total: 2,
  title: "分布统计",
  method: "describe",
  status: "success" as const,
  table: { columns: ["column", "mean"], rows: [{ column: "value", mean: 4 }] },
  result: {},
};

const FAILED_STEP = {
  index: 1,
  total: 2,
  title: "组间比较",
  method: "group_compare",
  status: "failed" as const,
  error: { code: "EXECUTION_FAILED", message: "分组列不足 2 组", hint: "检查 group 列取值" },
};

beforeEach(() => {
  installFakeWebSocket();
  vi.spyOn(console, "error").mockImplementation(() => {});
});

describe("节点级交付与断点续接", () => {
  it("执行期逐节点渲染结果；失败节点支持重跑与补充信息修正", async () => {
    setupFetch();
    const { container } = render(<App />);
    await openSession(container);

    act(() => {
      socket().emit({ type: "step_result", index: 0, total: 2, step: OK_STEP, seq: 5 });
      socket().emit({ type: "step_result", index: 1, total: 2, step: FAILED_STEP, seq: 6 });
    });

    const card = await screen.findByTestId("step-delivery");
    expect(card).toHaveTextContent("1/2 完成");
    expect(card).toHaveTextContent("1 个失败");
    expect(card).toHaveTextContent("分布统计");

    // 成功节点：展开可见该节点表格
    const firstNode = screen.getByTestId("step-delivery-0");
    fireEvent.click(firstNode.querySelector("button")!);
    expect(within(firstNode).getByRole("table")).toBeInTheDocument();
    expect(within(firstNode).getByText("mean")).toBeInTheDocument();

    // 执行收尾（真实时序：全部节点交付后下发审阅请求，phase 回到 idle）
    act(() => {
      socket().emit({
        type: "review_request",
        report: { report_id: "r1", steps: [] },
        seq: 7,
      });
    });

    // 失败节点：展开可见原因与两个动作入口
    fireEvent.click(screen.getByTestId("step-delivery-1").querySelector("button")!);
    expect(screen.getByText("分组列不足 2 组")).toBeInTheDocument();

    // 定点修正：补充信息 → 让模型只重写该节点
    fireEvent.change(screen.getByLabelText("节点2补充说明"), {
      target: { value: "按 group 分组比较 value" },
    });
    fireEvent.click(screen.getByRole("button", { name: /让 AI 修正/ }));
    expect(socket().sent).toContainEqual({
      type: "amend_step",
      index: 1,
      note: "按 group 分组比较 value",
    });
    // 用户补充也进会话气泡（可回放、可核对）
    expect(await screen.findByText(/补充（节点 2）：按 group 分组比较 value/)).toBeInTheDocument();

    // 修正触发的重跑收尾后，可以直接重跑该节点（不必整条链重来）
    act(() => {
      socket().emit({
        type: "review_request",
        report: { report_id: "r1", steps: [] },
        seq: 11,
      });
    });
    fireEvent.click(screen.getByRole("button", { name: /重跑该节点及其下游/ }));
    expect(socket().sent).toContainEqual({ type: "retry_step", index: 1 });
  });

  it("同一节点重复交付（updated）就地更新，不堆重复行", async () => {
    setupFetch();
    const { container } = render(<App />);
    await openSession(container);

    act(() => {
      socket().emit({ type: "step_result", index: 0, total: 1, step: OK_STEP, seq: 5 });
    });
    const before = await screen.findByTestId("step-delivery");
    expect(before.querySelectorAll("li")).toHaveLength(1);

    act(() => {
      socket().emit({
        type: "step_result",
        index: 0,
        total: 1,
        step: { ...OK_STEP, updated: true, title: "分布统计（已更新）" },
        seq: 9,
      });
    });

    const after = screen.getByTestId("step-delivery");
    expect(after.querySelectorAll("li")).toHaveLength(1);
    expect(after).toHaveTextContent("分布统计（已更新）");
  });

  it("新的方案（plan 帧）清空上一轮的节点交付", async () => {
    setupFetch();
    const { container } = render(<App />);
    await openSession(container);

    act(() => {
      socket().emit({ type: "step_result", index: 0, total: 1, step: OK_STEP, seq: 5 });
    });
    expect(await screen.findByTestId("step-delivery")).toBeInTheDocument();

    act(() => {
      socket().emit({
        type: "plan",
        message: "新方案",
        steps: [],
        options: [{ id: "go", label: "按此执行", action: "confirm" }],
        seq: 8,
      });
    });

    expect(screen.queryByTestId("step-delivery")).not.toBeInTheDocument();
  });
});

describe("WS 回放与竞态", () => {
  it("回放 retry_step_user / amend_step_user 生成可读气泡（不是空气泡）", async () => {
    setupFetch();
    const { container } = render(<App />);
    await openSession(container);

    act(() => {
      socket().emit({ type: "retry_step_user", content: "1", seq: 20 });
      socket().emit({ type: "amend_step_user", content: "按 group 分组", seq: 21 });
    });

    expect(await screen.findByText("重跑节点 2")).toBeInTheDocument();
    expect(screen.getByText("补充说明：按 group 分组")).toBeInTheDocument();
  });

  it("重连回放与本地发出的同一句话不堆成两条", async () => {
    setupFetch();
    const { container } = render(<App />);
    await openSession(container);

    fireEvent.change(screen.getByPlaceholderText(/描述分析目标/), {
      target: { value: "比较两组 value" },
    });
    fireEvent.click(screen.getByRole("button", { name: /发送/ }));
    expect(await screen.findByText("比较两组 value")).toBeInTheDocument();

    act(() => {
      socket().emit({ type: "chat_user", content: "比较两组 value", seq: 4 });
    });

    expect(screen.getAllByText("比较两组 value")).toHaveLength(1);
  });

  it("切到别的会话后，旧会话的 data_profile 不改变当前显示", async () => {
    setupFetch();
    const { container } = render(<App />);
    await openSession(container);

    // 新建第二个会话并切过去
    fireEvent.click(screen.getByTitle("新建会话空间"));
    await screen.findByRole("button", { name: /^会话 2/ });
    // 窄屏单栏：切到工作区才能观察右栏是否被旧会话污染
    fireEvent.click(screen.getAllByRole("button", { name: /^工作区（/ })[0]);

    const oldSocket = FakeWebSocket.instances[0];
    act(() => {
      oldSocket.emit({
        type: "data_profile",
        dataset_id: "d-old",
        name: "old.csv",
        profile: PROFILE,
        active: true,
        seq: 30,
      });
    });

    // 旧会话的数据集只挂在它自己名下：当前会话仍是「未绑定」，也不出现 old.csv
    const binding = await screen.findByText(/当前会话绑定表格：/);
    expect(binding.textContent).toContain("未绑定");
    // 工作区标签是按钮：旧会话的数据集不得出现在当前会话的标签里
    expect(screen.queryAllByRole("button", { name: "old.csv" })).toHaveLength(0);
  });
});
