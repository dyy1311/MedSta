import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ChainBuilder from "./ChainBuilder";
import { jsonResponse, mockFetch } from "../test/mocks";

const TOOLS = {
  tools: [
    {
      name: "describe",
      title: "描述性统计",
      category: "描述与质检",
      description: "数值列分布概览",
      task: "描述",
      applicability: "任何分析第一步",
      slots: [],
      params: [{ name: "group_by", type: "column", required: false, description: "分组列", choices: [], default: null }],
      charts: ["histogram", "boxplot"],
      accepts: ["continuous", "ordinal"],
    },
    {
      name: "group_compare",
      title: "两组比较",
      category: "组间比较",
      description: "两组数值比较",
      task: "因果",
      applicability: "两组独立样本",
      slots: [],
      params: [
        { name: "group_column", type: "column", required: true, description: "分组列", choices: [], default: null },
        { name: "paired", type: "boolean", required: false, description: "是否配对", choices: [], default: false },
      ],
      charts: ["boxplot", "none"],
      accepts: ["continuous", "ordinal"],
    },
  ],
  charts: [{ name: "boxplot", label: "boxplot" }],
};

const TPL_NAME_ENC = encodeURIComponent("我的套路");
const TPL_STEPS = [
  { method: "describe", title: "分布统计", target_columns: ["value"], chart_type: "none", params: {} },
];

const baseProps = {
  sessionId: "s1",
  columns: ["group", "value", "age"],
  busy: false,
  importSteps: null,
  onRun: vi.fn(),
};

let fetchSpy: ReturnType<typeof mockFetch>;

beforeEach(() => {
  vi.clearAllMocks();
});

async function renderBuilder(props = {}, templates: unknown[] = []) {
  fetchSpy = mockFetch([
    { path: "/capabilities", method: "GET", respond: () => jsonResponse(TOOLS) },
    { path: "/templates", method: "GET", respond: () => jsonResponse({ templates }) },
    {
      path: `/templates/${TPL_NAME_ENC}`,
      method: "PUT",
      respond: () => jsonResponse({ ok: true }),
    },
    {
      path: `/templates/${TPL_NAME_ENC}`,
      method: "DELETE",
      respond: () => jsonResponse({ ok: true }),
    },
  ]);
  render(<ChainBuilder {...baseProps} {...props} />);
  await screen.findByRole("option", { name: "两组比较" });
  return fetchSpy;
}

describe("ChainBuilder 原子工具装配", () => {
  it("B8: 选择工具后按 ToolSpec 动态渲染参数表单，添加进工作链", async () => {
    await renderBuilder();

    fireEvent.change(screen.getByLabelText("统计工具"), { target: { value: "group_compare" } });

    expect(screen.getByLabelText("group_column（必填）")).toBeInTheDocument();
    expect(screen.getByLabelText("paired")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("value"));
    fireEvent.change(screen.getByLabelText("group_column（必填）"), { target: { value: "group" } });
    fireEvent.change(screen.getByLabelText("图表"), { target: { value: "none" } });

    fireEvent.click(screen.getByRole("button", { name: /添加到工作链/ }));

    expect(screen.getByTestId("chain-step-0")).toHaveTextContent("两组比较");
  });

  it("B9: 工作链可上移/删除，执行发送完整 run_chain 步骤", async () => {
    await renderBuilder();

    fireEvent.change(screen.getByLabelText("统计工具"), { target: { value: "describe" } });
    fireEvent.click(screen.getByLabelText("value"));
    fireEvent.click(screen.getByRole("button", { name: /添加到工作链/ }));
    fireEvent.change(screen.getByLabelText("统计工具"), { target: { value: "group_compare" } });
    fireEvent.click(screen.getByLabelText("value"));
    fireEvent.change(screen.getByLabelText("group_column（必填）"), { target: { value: "group" } });
    fireEvent.click(screen.getByRole("button", { name: /添加到工作链/ }));

    expect(screen.getByTestId("chain-step-0")).toHaveTextContent("描述性统计");
    expect(screen.getByTestId("chain-step-1")).toHaveTextContent("两组比较");

    fireEvent.click(screen.getByTestId("chain-up-1"));
    expect(screen.getByTestId("chain-step-0")).toHaveTextContent("两组比较");

    fireEvent.click(screen.getByRole("button", { name: /执行工作链/ }));
    expect(baseProps.onRun).toHaveBeenCalledWith([
      expect.objectContaining({ method: "group_compare", target_columns: ["value"], chart_type: "none" }),
      expect.objectContaining({ method: "describe" }),
    ]);

    fireEvent.click(screen.getByTestId("chain-remove-0"));
    expect(screen.getByTestId("chain-step-0")).toHaveTextContent("描述性统计");
  });

  it("B10: 从模型方案导入步骤并继续编辑", async () => {
    await renderBuilder({
      importSteps: [
        { method: "describe", title: "分布统计", target_columns: ["value"], chart_type: "histogram", params: {} },
      ],
    });

    fireEvent.click(screen.getByRole("button", { name: /导入最新方案/ }));

    expect(screen.getByTestId("chain-step-0")).toHaveTextContent("分布统计");
  });

  it("忙时不允许执行", async () => {
    await renderBuilder({ busy: true });
    expect(screen.getByRole("button", { name: /执行工作链/ })).toBeDisabled();
  });

  it("B6a: 命名保存当前工作链（PUT /templates/{name}）", async () => {
    const spy = await renderBuilder();

    fireEvent.change(screen.getByLabelText("统计工具"), { target: { value: "describe" } });
    fireEvent.click(screen.getByLabelText("value"));
    fireEvent.click(screen.getByRole("button", { name: /添加到工作链/ }));

    fireEvent.change(screen.getByPlaceholderText("模板名称"), { target: { value: "我的套路" } });
    fireEvent.click(screen.getByRole("button", { name: "保存模板" }));

    await waitFor(() => {
      const put = fetchSpy.mock.calls.find(
        ([url, init]) =>
          url === `/templates/${TPL_NAME_ENC}` && (init as RequestInit)?.method === "PUT"
      );
      expect(put).toBeTruthy();
      expect(JSON.parse(String(put![1]?.body)).steps).toHaveLength(1);
    });
    await waitFor(() => {
      expect(screen.getByTestId("tpl-notice").textContent).toContain("已保存");
    });
  });

  it("B6b: 模板列表可载入（步骤回填）与删除（DELETE）", async () => {
    const spy = await renderBuilder(
      {},
      [{ name: "我的套路", steps: TPL_STEPS, created_at: "2026-11-16", updated_at: "2026-11-16" }]
    );

    expect(await screen.findByText("我的套路")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /载入/ }));
    expect(screen.getByTestId("chain-step-0")).toHaveTextContent("分布统计");

    fireEvent.click(screen.getByRole("button", { name: "删除 我的套路" }));
    await waitFor(() => {
      const del = fetchSpy.mock.calls.find(
        ([url, init]) =>
          url === `/templates/${TPL_NAME_ENC}` && (init as RequestInit)?.method === "DELETE"
      );
      expect(del).toBeTruthy();
    });
  });

  it("B6c: 目标列快捷勾选按列类型批量选择", async () => {
    await renderBuilder({
      columnTypes: { group: "categorical", value: "continuous", age: "continuous" },
    });

    fireEvent.change(screen.getByLabelText("统计工具"), { target: { value: "describe" } });
    fireEvent.click(screen.getByRole("button", { name: "全部数值列" }));

    expect(screen.getByLabelText("value")).toBeChecked();
    expect(screen.getByLabelText("age")).toBeChecked();
    expect(screen.getByLabelText("group")).not.toBeChecked();
  });
});
