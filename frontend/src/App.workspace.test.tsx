import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import {
  FakeWebSocket,
  PROFILE,
  installFakeWebSocket,
  jsonResponse,
  mockFetch,
} from "./test/mocks";

const SECOND_PROFILE = {
  ...PROFILE,
  row_count: 40,
};

/** 上传后的绑定提示（首次绑定） */
const UPLOAD_NOTICE = /数据「cohort\.csv」已绑定当前会话/;

function setupFetch() {
  let uploadCount = 0;
  return mockFetch([
    {
      path: "/sessions",
      method: "POST",
      respond: () => jsonResponse({ session_id: "s1", status: "discussing" }),
    },
    {
      path: "/sessions/s1/data",
      method: "POST",
      respond: () => {
        uploadCount += 1;
        const first = uploadCount === 1;
        return jsonResponse({
          type: "data_profile",
          dataset_id: first ? "d1" : `d-extra-${uploadCount}`,
          name: first ? "cohort.csv" : `extra-${uploadCount}.csv`,
          profile: PROFILE,
        });
      },
    },
    {
      path: "/sessions/s1/workspace/d2/activate",
      method: "POST",
      respond: () =>
        jsonResponse({
          type: "data_profile",
          dataset_id: "d2",
          name: "插补结果",
          type_confirmed: false,
          profile: SECOND_PROFILE,
        }),
    },
  ]);
}

async function openSessionWithData(container: HTMLElement) {
  fireEvent.click(screen.getByTitle("新建会话空间"));
  await screen.findByRole("button", { name: /^会话 1/ });

  const input = container.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(["group,value\n"], "cohort.csv")] } });
  await screen.findByText(UPLOAD_NOTICE);
}

function socket() {
  return FakeWebSocket.latest();
}

function dropWith(files: File[]) {
  const event = new Event("drop");
  Object.defineProperty(event, "dataTransfer", { value: { files, types: ["Files"] } });
  window.dispatchEvent(event);
}

beforeEach(() => {
  installFakeWebSocket();
  vi.spyOn(console, "error").mockImplementation(() => {});
});

describe("工作区激活与多文件导入（终审修复）", () => {
  it("点击工作区标签会同步后端 active_dataset_id，并回写会话绑定", async () => {
    const fetchSpy = setupFetch();
    const { container } = render(<App />);
    await openSessionWithData(container);

    // 插补/清洗数据集：新增标签但保持原激活（不打断当前查看的数据）
    act(() => {
      socket().emit({
        type: "dataset_added",
        dataset_id: "d2",
        name: "插补结果",
        profile: SECOND_PROFILE,
        imputed: true,
        source_dataset_id: "d1",
      });
    });
    await screen.findByRole("button", { name: /插补结果/ });

    fireEvent.click(screen.getByRole("button", { name: /插补结果/ }));

    // 激活回执把画像切到新数据集（40 行）
    expect(await screen.findByText("40 行 × 2 列")).toBeInTheDocument();
    const activateCall = fetchSpy.mock.calls.find(
      ([url, init]) =>
        String(url) === "/sessions/s1/workspace/d2/activate" &&
        (init as RequestInit | undefined)?.method === "POST"
    );
    expect(activateCall).toBeTruthy();
    // 会话绑定名同步为新数据集（否则「显示新表、分析旧表」）
    expect(screen.getByText("插补结果", { selector: "span" })).toBeInTheDocument();
  });

  it("一次拖入两个文件：逐个弹窗确认，两份都不丢", async () => {
    const fetchSpy = setupFetch();
    const { container } = render(<App />);
    await openSessionWithData(container);

    await act(async () => {
      dropWith([
        new File(["a,b\n1,2\n"], "first.csv"),
        new File(["c,d\n3,4\n"], "second.csv"),
      ]);
    });

    // 第一个文件弹窗 → 加入当前工作区；完成后第二个文件继续弹窗
    fireEvent.click(await screen.findByRole("button", { name: /加入当前工作区/ }));
    await screen.findByText(/上传「second\.csv」/);
    fireEvent.click(screen.getByRole("button", { name: /加入当前工作区/ }));

    expect(await screen.findByText(/已添加数据集「second\.csv」/)).toBeInTheDocument();
    const uploads = fetchSpy.mock.calls.filter(
      ([url, init]) =>
        String(url) === "/sessions/s1/data" &&
        (init as RequestInit | undefined)?.method === "POST"
    );
    expect(uploads).toHaveLength(3); // 1 次初始上传 + 2 次拖拽上传
    expect(screen.getAllByText(/已添加数据集/).length).toBe(2);
  });

  it("已绑定会话再上传：新增标签但显示与绑定仍停在原表", async () => {
    setupFetch();
    const { container } = render(<App />);
    await openSessionWithData(container);

    act(() => {
      socket().emit({
        type: "data_profile",
        dataset_id: "d9",
        name: "extra.csv",
        profile: SECOND_PROFILE,
        active: false,
      });
    });

    expect(await screen.findByText(/已添加数据集「extra\.csv」/)).toBeInTheDocument();
    expect(screen.getByText(/当前会话绑定表格：/)).toHaveTextContent("cohort.csv");
  });

  it("切走再切回：出图配置卡仍在（交互卡按会话保留，否则输入只读又无卡可确认）", async () => {
    let created = 0;
    mockFetch([
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
          jsonResponse({
            type: "data_profile",
            dataset_id: "d1",
            name: "cohort.csv",
            profile: PROFILE,
          }),
      },
    ]);

    const { container } = render(<App />);
    await openSessionWithData(container);
    const firstSocket = socket();

    act(() => {
      firstSocket.emit({
        type: "chart_config",
        steps: [{ step_id: "step_1", title: "分布统计", default_chart: "histogram", charts: ["histogram"] }],
        multi_chart: false,
        alpha: 0.05,
        correction: "holm",
        message: "出图前请确认图表类型与显著性判断标准",
      });
    });
    expect(await screen.findByText("出图前确认")).toBeInTheDocument();

    // 新建第二个会话（切走）→ 卡不得串到别的会话
    fireEvent.click(screen.getByTitle("新建会话空间"));
    await screen.findByRole("button", { name: /^会话 2/ });
    expect(screen.queryByText("出图前确认")).not.toBeInTheDocument();

    // 切回会话 1 → 卡回来（旧实现里已被 switch 清理，会话再无入口可确认）
    fireEvent.click(screen.getByRole("button", { name: /^会话 1/ }));
    expect(await screen.findByText("出图前确认")).toBeInTheDocument();
  });
});
