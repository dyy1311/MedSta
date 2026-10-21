import { act, fireEvent, render, screen, within } from "@testing-library/react";
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

const UPLOAD_NOTICE = /数据「cohort.csv」已绑定当前会话/;

function setupFetch(uploadOk = true) {
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
        uploadOk
          ? jsonResponse({
              type: "data_profile",
              dataset_id: "d1",
              name: "cohort.csv",
              profile: PROFILE,
            })
          : jsonResponse({ detail: "不支持的文件类型：.txt" }, 400),
    },
    {
      path: "/sessions/s1/workspace/d1/columns",
      method: "PATCH",
      respond: () =>
        jsonResponse({
          type: "data_profile",
          dataset_id: "d1",
          profile: {
            ...PROFILE,
            type_confirmed: true,
            columns: {
              ...PROFILE.columns,
              value: { ...PROFILE.columns.value, type: "ordinal" },
            },
          },
        }),
    },
    {
      path: "/capabilities",
      method: "GET",
      respond: () =>
        jsonResponse({
          tools: [],
          charts: [],
          planned: [],
          methodology: "依据方法学流程图落地",
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

beforeEach(() => {
  installFakeWebSocket();
  vi.spyOn(console, "error").mockImplementation(() => {});
  setupFetch();
});

describe("会话流交互", () => {
  it("发送讨论消息 → 类型确认 → 方案选项 → 出图配置 → 审阅交付", async () => {
    const { container } = render(<App />);
    await openSessionWithData(container);

    const composer = screen.getByPlaceholderText("描述分析目标，或对方案提出修正意见…");
    fireEvent.change(composer, { target: { value: "分析 value 的分布" } });
    fireEvent.click(screen.getByRole("button", { name: /发送/ }));

    expect(socket().sent.at(-1)).toEqual({ type: "chat", content: "分析 value 的分布" });
    expect(screen.getByText("分析 value 的分布")).toBeInTheDocument();

    act(() => {
      socket().emit({
        type: "type_review",
        dataset_id: "d1",
        message: "请先确认各列的变量类型",
        columns: [
          { name: "group", type: "categorical", missing: 0 },
          { name: "value", type: "continuous", missing: 0 },
        ],
      });
    });
    expect(await screen.findByText("请敲定变量类型")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /确认类型，开始讨论/ }));
    expect(socket().sent.at(-1)).toEqual({
      type: "type_confirm",
      types: { group: "categorical", value: "continuous" },
    });

    act(() => {
      socket().emit(PLAN_EVENT);
    });
    expect(await screen.findByText("分析方案")).toBeInTheDocument();
    expect(screen.getByText("分布统计")).toBeInTheDocument();
    expect(screen.getByText("连续变量先看分布")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /按此执行/ }));
    expect(socket().sent.at(-1)).toMatchObject({ type: "option", option_id: "go" });

    act(() => {
      socket().emit({
        type: "chart_config",
        steps: [{ step_id: "step_1", title: "分布统计", default_chart: "histogram" }],
        multi_chart: false,
        alpha: 0.05,
        correction: "holm",
        message: "出图前请确认图表类型与显著性判断标准",
      });
    });
    expect(await screen.findByText("出图前确认")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /按此配置执行/ }));
    expect(socket().sent.at(-1)).toMatchObject({
      type: "chart_choice",
      choices: [{ step_id: "step_1", chart_type: "histogram" }],
      layout: "separate",
      alpha: 0.05,
      correction: "holm",
    });

    act(() => {
      socket().emit({ type: "review_request", report: REPORT });
    });
    expect(await screen.findByText("执行完成，请审阅结果")).toBeInTheDocument();
    expect(screen.getByText(/已生成统计表格（1 行）/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /确认交付/ }));
    expect(socket().sent.at(-1)).toEqual({ type: "review", decision: "accept" });

    act(() => {
      socket().emit({ type: "delivered", report: REPORT });
    });
    expect(await screen.findByText(/结果已交付/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /确认交付/ })).not.toBeInTheDocument();
  });

  it("类型确认支持「数值列全部设为连续」，类别与索引列不变", async () => {
    const { container } = render(<App />);
    await openSessionWithData(container);

    act(() => {
      socket().emit({
        type: "type_review",
        dataset_id: "d1",
        message: "请先确认各列的变量类型",
        columns: [
          { name: "group", type: "categorical", missing: 0 },
          { name: "age", type: "ordinal", missing: 0 },
          { name: "value", type: "ordinal", missing: 0 },
          { name: "seq", type: "index", missing: 0 },
        ],
      });
    });
    await screen.findByText("请敲定变量类型");

    fireEvent.click(screen.getByRole("button", { name: "数值列全部设为连续" }));
    fireEvent.click(screen.getByRole("button", { name: /确认类型，开始讨论/ }));

    expect(socket().sent.at(-1)).toEqual({
      type: "type_confirm",
      types: { group: "categorical", age: "continuous", value: "continuous", seq: "index" },
    });
  });

  it("表格结果可补绘图：plot_suggest → plot_later", async () => {
    const { container } = render(<App />);
    await openSessionWithData(container);

    act(() => {
      socket().emit({
        type: "plot_suggest",
        steps: [{ step_index: 0, title: "分布统计", charts: ["histogram", "boxplot"] }],
      });
    });

    expect(await screen.findByText("是否为结果绘图？")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /绘图/ }));

    expect(socket().sent.at(-1)).toEqual({
      type: "plot_later",
      step_index: 0,
      chart_type: "histogram",
    });
  });

  it("审阅提出修正 → 发送 revise 并回到讨论", async () => {
    const { container } = render(<App />);
    await openSessionWithData(container);

    act(() => {
      socket().emit(PLAN_EVENT);
      socket().emit({ type: "review_request", report: REPORT });
    });

    fireEvent.click(await screen.findByRole("button", { name: /提出修正/ }));
    fireEvent.change(screen.getByPlaceholderText("例如：不要用直方图，改成看相关性"), {
      target: { value: "改用非参数检验" },
    });
    fireEvent.click(screen.getByRole("button", { name: /提交修正/ }));

    expect(socket().sent.at(-1)).toEqual({
      type: "review",
      decision: "revise",
      content: "改用非参数检验",
    });
    expect(screen.getByText("修正意见：改用非参数检验")).toBeInTheDocument();

    act(() => {
      socket().emit({ type: "back_to_discussion", message: "已记录修正意见，请继续讨论" });
    });
    expect(await screen.findByText("已记录修正意见，请继续讨论")).toBeInTheDocument();
  });

  it("错误事件渲染为可分类的错误卡并支持展开详情", async () => {
    const { container } = render(<App />);
    await openSessionWithData(container);

    act(() => {
      socket().emit({
        type: "error",
        code: "INVALID_PLAN",
        message: "方案参数不完整，已阻止执行",
        hint: "补充参数或更换方法后重试",
        detail: { issues: [{ code: "MISSING_PARAM" }] },
      });
    });

    expect(await screen.findByText("方案校验未通过")).toBeInTheDocument();
    expect(screen.getByText("方案参数不完整，已阻止执行")).toBeInTheDocument();
    expect(screen.getByText("补充参数或更换方法后重试")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /查看详情/ }));
    expect(screen.getByText(/"MISSING_PARAM"/)).toBeInTheDocument();

    act(() => {
      socket().emit({
        type: "error",
        code: "PROTOCOL_UNSUPPORTED",
        message: "未知消息类型：magic",
        hint: "检查前端协议版本",
      });
    });
    expect(await screen.findByText("协议不支持")).toBeInTheDocument();
  });

  it("上传失败时在会话流展示错误，而不是静默失败", async () => {
    setupFetch(false);
    const { container } = render(<App />);
    fireEvent.click(screen.getByTitle("新建会话空间"));
    await screen.findByRole("button", { name: /^会话 1/ });

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["x"], "notes.txt")] } });

    expect(await screen.findByText("上传失败")).toBeInTheDocument();
    expect(screen.getByText(/不支持的文件类型：\.txt/)).toBeInTheDocument();
  });

  it("工作区修改列类型会 PATCH 后端并刷新画像", async () => {
    const fetchSpy = setupFetch();
    const { container } = render(<App />);
    await openSessionWithData(container);

    fireEvent.click(screen.getByRole("button", { name: /工作区（1）/ }));
    const workspaceSection = container.querySelectorAll<HTMLElement>("main > section")[1];
    const typeSelect = within(workspaceSection).getAllByRole("combobox")[1];
    fireEvent.change(typeSelect, { target: { value: "ordinal" } });

    const patchCall = fetchSpy.mock.calls.find(
      ([, init]) => (init as RequestInit | undefined)?.method === "PATCH"
    );
    expect(patchCall).toBeTruthy();
    expect(JSON.parse(String((patchCall?.[1] as RequestInit).body))).toEqual({
      column: "value",
      type: "ordinal",
    });
    expect(await within(workspaceSection).findByDisplayValue("数值-等级型")).toBeInTheDocument();
  });

  it("执行结果进入工作区：表格交付、导出链接与图表卡", async () => {
    const { container } = render(<App />);
    await openSessionWithData(container);

    act(() => {
      socket().emit({ type: "review_request", report: REPORT });
    });
    await screen.findByText("执行完成，请审阅结果");

    fireEvent.click(screen.getByRole("button", { name: /工作区（1）/ }));
    const workspaceSection = container.querySelectorAll<HTMLElement>("main > section")[1];

    expect(within(workspaceSection).getByText("统计表交付（1）")).toBeInTheDocument();
    const csv = within(workspaceSection).getByRole("link", { name: "CSV" });
    expect(csv).toHaveAttribute("href", "/export/s1/0?format=csv");
    expect(within(workspaceSection).getByRole("link", { name: "Excel" })).toHaveAttribute(
      "href",
      "/export/s1/0?format=xlsx"
    );
    expect(within(workspaceSection).getByText("执行产出（1）")).toBeInTheDocument();
    expect(within(workspaceSection).getByRole("img")).toHaveAttribute(
      "src",
      "/data/s1/d1/artifacts/step_0_describe_histogram.png"
    );
  });
});
