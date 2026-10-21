import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import App from "./App";
import {
  CAPABILITIES,
  FakeWebSocket,
  PROFILE,
  installFakeWebSocket,
  jsonResponse,
  mockFetch,
} from "./test/mocks";

function setupFetch() {
  let sessionCounter = 0;
  return mockFetch([
    {
      path: "/sessions",
      method: "POST",
      respond: () => {
        sessionCounter += 1;
        return jsonResponse({ session_id: `s${sessionCounter}`, status: "discussing" });
      },
    },
    {
      path: "/sessions/s1/data",
      method: "POST",
      respond: () =>
        jsonResponse({ type: "data_profile", dataset_id: "d1", name: "cohort.csv", profile: PROFILE }),
    },
    {
      path: "/sessions/s2/data",
      method: "POST",
      respond: () =>
        jsonResponse({ type: "data_profile", dataset_id: "d2", name: "second.csv", profile: PROFILE }),
    },
    { path: "/capabilities", method: "GET", respond: () => jsonResponse(CAPABILITIES) },
  ]);
}

async function createSessionByClick(expected: number) {
  fireEvent.click(screen.getByTitle("新建会话空间"));
  await screen.findByRole("button", { name: new RegExp(`^会话 ${expected}`) });
}

function uploadFile(container: HTMLElement, file = new File(["group,value\nA,1\n"], "cohort.csv")) {
  const input = container.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [file] } });
  return input;
}

beforeEach(() => {
  installFakeWebSocket();
  setupFetch();
});

describe("App 布局骨架", () => {
  it("渲染双栏工作台与顶部计数，工作区初始为空态", () => {
    const { container } = render(<App />);

    expect(screen.getByText("MedSta")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /会话（0）/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /工作区（0）/ })).toBeInTheDocument();
    expect(
      screen.getByText("上传数据并确认方案后，数据画像与图表将展示在这里")
    ).toBeInTheDocument();

    const [chat, workspace] = Array.from(container.querySelectorAll("main > section"));
    expect(chat.classList.contains("hidden")).toBe(false);
    expect(workspace.classList.contains("hidden")).toBe(true);
  });

  it("顶部 Tab 切换左右栏（窄屏同一条路径）", () => {
    const { container } = render(<App />);
    const [chat, workspace] = Array.from(container.querySelectorAll("main > section"));

    fireEvent.click(screen.getByRole("button", { name: /工作区（0）/ }));
    expect(chat.classList.contains("hidden")).toBe(true);
    expect(workspace.classList.contains("hidden")).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: /会话（0）/ }));
    expect(chat.classList.contains("hidden")).toBe(false);
    expect(workspace.classList.contains("hidden")).toBe(true);
  });

  it("新建会话后出现会话 Tab 与绑定提示条", async () => {
    render(<App />);

    await createSessionByClick(1);

    expect(screen.getByRole("button", { name: /^会话 1/ })).toBeInTheDocument();
    expect(screen.getByText("未绑定")).toBeInTheDocument();
    expect(screen.getByText(/会话（1）/)).toBeInTheDocument();
  });

  it("上传后工作区出现画像并能切换 Tab 查看", async () => {
    const { container } = render(<App />);
    await createSessionByClick(1);

    uploadFile(container);
    await screen.findByText(/数据「cohort.csv」已绑定当前会话/);

    expect(screen.getByText(/工作区（1）/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /工作区（1）/ }));

    expect(screen.getByText("数据画像")).toBeInTheDocument();
    expect(screen.getByText("6 行 × 2 列")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "列名" })).toBeInTheDocument();
  });

  it("多会话 Tab 切换时更新绑定表格名", async () => {
    render(<App />);
    await createSessionByClick(1);
    await createSessionByClick(2);

    fireEvent.click(screen.getByRole("button", { name: /^会话 1/ }));
    expect(screen.getByText("未绑定")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^会话 2/ }));
    expect(screen.getByText("未绑定")).toBeInTheDocument();
  });

  it("能力抽屉按需加载并展示方法与规划中能力", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: /能力/ }));

    expect(await screen.findByText("统计能力披露")).toBeInTheDocument();
    expect(screen.getByText("描述性统计")).toBeInTheDocument();
    expect(screen.getByText("生存分析")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "关闭能力抽屉" }));
    await waitFor(() => expect(screen.queryByText("统计能力披露")).not.toBeInTheDocument());
  });
});

describe("App 会话隔离", () => {
  it("非激活会话的事件不进入当前会话流", async () => {
    render(<App />);
    await createSessionByClick(1);
    await createSessionByClick(2);

    const secondSocket = FakeWebSocket.latest();
    act(() => {
      secondSocket.emit({
        type: "plan",
        message: "第二个会话的方案",
        steps: [],
        options: [{ id: "go", label: "按此执行", action: "confirm" }],
      });
    });
    expect(await screen.findByText("第二个会话的方案")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^会话 1/ }));
    await act(async () => {});
    expect(screen.queryByText("第二个会话的方案")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^会话 2/ }));
    expect(await screen.findByText("第二个会话的方案")).toBeInTheDocument();
  });
});
