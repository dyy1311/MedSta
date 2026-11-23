import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { FakeWebSocket, PROFILE, installFakeWebSocket, jsonResponse, mockFetch } from "./test/mocks";

/**
 * 「AI 确认类型」体验 + 会话/工作台同步 + 模块卡折叠：
 * 点按钮必须有进行中反馈；采纳建议后左栏要留可核对记录；三个模块卡可收起。
 */

const UPLOAD_NOTICE = /数据「cohort\.csv」已绑定当前会话/;
const SUGGESTION = {
  name: "value",
  suggested_type: "ordinal",
  confidence: 0.9,
  reason: "1-5 评分等级",
};

function setupFetch() {
  const fetchSpy = mockFetch([
    {
      path: "/sessions",
      method: "POST",
      respond: () => jsonResponse({ session_id: "s1", status: "discussing" }),
    },
    {
      path: "/sessions/s1/data",
      method: "POST",
      respond: () =>
        jsonResponse({
          type: "data_profile",
          dataset_id: "d1",
          name: "cohort.csv",
          profile: PROFILE,
        }),
    },
    {
      path: "/sessions/s1/workspace/d1/columns",
      method: "PATCH",
      respond: () => jsonResponse({ type: "data_profile", dataset_id: "d1", profile: PROFILE }),
    },
  ]);
  return fetchSpy;
}

async function openWorkspace(container: HTMLElement) {
  fireEvent.click(screen.getByTitle("新建会话空间"));
  await screen.findByRole("button", { name: /^会话 1/ });
  const input = container.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(["group,value\n"], "cohort.csv")] } });
  await screen.findByText(UPLOAD_NOTICE);

  // 窄屏默认单栏：切到工作区才能看到画像
  const workspaceTab = screen
    .getAllByRole("button", { name: /^工作区（1）/ })
    .find((button) => button.tagName === "BUTTON");
  if (workspaceTab) fireEvent.click(workspaceTab);
  await screen.findByText("数据画像");
}

function socket() {
  return FakeWebSocket.latest();
}

beforeEach(() => {
  installFakeWebSocket();
  vi.spyOn(console, "error").mockImplementation(() => {});
});

describe("AI 类型建议与会话同步", () => {
  it("点击 AI 确认类型立即进入加载态并给出说明，结果到达后恢复正常", async () => {
    setupFetch();
    const { container } = render(<App />);
    await openWorkspace(container);

    fireEvent.click(screen.getByTestId("suggest-types"));

    // 1) 立即反馈：按钮转加载态 + 说明文案，且不重复发送
    const button = await screen.findByRole("button", { name: /正在分析列含义/ });
    expect(button).toBeDisabled();
    expect(screen.getByTestId("suggest-pending")).toBeInTheDocument();
    expect(socket().sent.filter((event) => event.type === "suggest_column_types")).toHaveLength(1);

    // 2) 结果到达：建议条出现、加载态结束、会话区有可核对提示
    act(() => {
      socket().emit({ type: "column_type_suggestions", suggestions: [SUGGESTION], seq: 2 });
    });

    expect(await screen.findByTestId("suggestions-bar")).toBeInTheDocument();
    expect(screen.queryByTestId("suggest-pending")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "AI 确认类型" })).not.toBeDisabled();
    expect(
      await screen.findByText(/AI 已给出 1 列的类型建议/)
    ).toBeInTheDocument();
  });

  it("采纳建议：PATCH 带 source=ai，服务端 type_confirmed 广播后左栏留记录、右栏画像同步", async () => {
    const fetchSpy = setupFetch();
    const { container } = render(<App />);
    await openWorkspace(container);

    act(() => {
      socket().emit({ type: "column_type_suggestions", suggestions: [SUGGESTION], seq: 2 });
    });
    fireEvent.click(await screen.findByRole("button", { name: "全部采纳建议" }));

    const patchCall = fetchSpy.mock.calls.find(
      ([, init]) => (init as RequestInit | undefined)?.method === "PATCH"
    );
    expect(JSON.parse(String((patchCall?.[1] as RequestInit).body))).toEqual({
      types: { value: "ordinal" },
      source: "ai",
    });

    // 服务端广播：工作台画像更新 + 会话区出现「已采纳 AI 建议」
    act(() => {
      socket().emit({
        type: "type_confirmed",
        dataset_id: "d1",
        profile: PROFILE,
        updated: ["value"],
        source: "ai",
        seq: 3,
      });
    });

    expect(await screen.findByText(/已采纳 AI 建议，更新/)).toBeInTheDocument();
    expect(screen.queryByTestId("suggestions-bar")).not.toBeInTheDocument();
  });

  it("手动改单列也广播到会话区（工作台与会话区不再各说各话）", async () => {
    setupFetch();
    const { container } = render(<App />);
    await openWorkspace(container);

    act(() => {
      socket().emit({
        type: "type_confirmed",
        dataset_id: "d1",
        profile: PROFILE,
        updated: ["group"],
        source: "manual",
        seq: 4,
      });
    });

    expect(await screen.findByText(/列类型已更新：「group」/)).toBeInTheDocument();
  });
});

describe("工作区模块卡折叠", () => {
  it("数据画像可收起/展开，标题始终可见", async () => {
    setupFetch();
    const { container } = render(<App />);
    await openWorkspace(container);

    const section = container.querySelectorAll<HTMLElement>("main > section")[1];
    expect(within(section).getAllByRole("table").length).toBeGreaterThan(0);

    fireEvent.click(within(section).getByRole("button", { name: "收起数据画像" }));
    expect(within(section).queryAllByRole("table")).toHaveLength(0);
    expect(within(section).getByText("数据画像")).toBeInTheDocument();

    fireEvent.click(within(section).getByRole("button", { name: "展开数据画像" }));
    expect(within(section).getAllByRole("table").length).toBeGreaterThan(0);
  });

  it("统计表交付与执行产出标题在有报告时可折叠，标题与计数仍在", async () => {
    setupFetch();
    const { container } = render(<App />);
    await openWorkspace(container);

    act(() => {
      socket().emit({
        type: "review_request",
        report: {
          report_id: "r1",
          steps: [
            {
              title: "分布统计",
              method: "describe",
              status: "success",
              artifact: "a.png",
              table: { columns: ["column", "count"], rows: [{ column: "value", count: 6 }] },
            },
          ],
        },
        seq: 5,
      });
    });

    const section = container.querySelectorAll<HTMLElement>("main > section")[1];
    expect(await within(section).findByText("统计表交付（1）")).toBeInTheDocument();

    const delivery = within(section).getByTestId("table-delivery");
    expect(within(delivery).getAllByRole("table").length).toBeGreaterThan(0);

    fireEvent.click(within(section).getByRole("button", { name: "收起统计表交付" }));
    expect(within(section).getByText("统计表交付（1）")).toBeInTheDocument();
    // 收起后该模块内的表格不再渲染（标题行仍在）
    expect(within(within(section).getByTestId("table-delivery")).queryAllByRole("table")).toHaveLength(0);
  });
});
