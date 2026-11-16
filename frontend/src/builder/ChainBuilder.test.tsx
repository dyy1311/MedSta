import { fireEvent, render, screen } from "@testing-library/react";
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
    },
  ],
  charts: [{ name: "boxplot", label: "boxplot" }],
};

function setupFetch() {
  mockFetch([{ path: "/capabilities", method: "GET", respond: () => jsonResponse(TOOLS) }]);
}

const baseProps = {
  sessionId: "s1",
  columns: ["group", "value", "age"],
  busy: false,
  importSteps: null,
  onRun: vi.fn(),
};

beforeEach(() => {
  setupFetch();
  vi.clearAllMocks();
});

async function renderBuilder(props = {}) {
  render(<ChainBuilder {...baseProps} {...props} />);
  await screen.findByRole("option", { name: "两组比较" }); // capabilities 已加载
}

describe("ChainBuilder 原子工具装配", () => {
  it("B8: 选择工具后按 ToolSpec 动态渲染参数表单，添加进工作链", async () => {
    await renderBuilder();

    fireEvent.change(screen.getByLabelText("统计工具"), { target: { value: "group_compare" } });

    // 必填 column 参数 → 下拉；boolean → checkbox
    expect(screen.getByLabelText("group_column（必填）")).toBeInTheDocument();
    expect(screen.getByLabelText("paired")).toBeInTheDocument();

    // 目标列多选 + 图表选择
    fireEvent.click(screen.getByLabelText("value"));
    fireEvent.change(screen.getByLabelText("group_column（必填）"), { target: { value: "group" } });
    fireEvent.change(screen.getByLabelText("图表"), { target: { value: "none" } });

    fireEvent.click(screen.getByRole("button", { name: /添加到工作链/ }));

    expect(screen.getByTestId("chain-step-0")).toHaveTextContent("两组比较");
  });

  it("B9: 工作链可上移/删除，执行发送完整 run_chain 步骤", async () => {
    await renderBuilder();


    // 添加 describe 步骤
    fireEvent.change(screen.getByLabelText("统计工具"), { target: { value: "describe" } });
    fireEvent.click(screen.getByLabelText("value"));
    fireEvent.click(screen.getByRole("button", { name: /添加到工作链/ }));
    // 添加 group_compare 步骤
    fireEvent.change(screen.getByLabelText("统计工具"), { target: { value: "group_compare" } });
    fireEvent.click(screen.getByLabelText("value"));
    fireEvent.change(screen.getByLabelText("group_column（必填）"), { target: { value: "group" } });
    fireEvent.click(screen.getByRole("button", { name: /添加到工作链/ }));

    expect(screen.getByTestId("chain-step-0")).toHaveTextContent("描述性统计");
    expect(screen.getByTestId("chain-step-1")).toHaveTextContent("两组比较");

    // 上移第二步
    fireEvent.click(screen.getByTestId("chain-up-1"));
    expect(screen.getByTestId("chain-step-0")).toHaveTextContent("两组比较");

    // 执行 → run_chain 载荷
    fireEvent.click(screen.getByRole("button", { name: /执行工作链/ }));
    expect(baseProps.onRun).toHaveBeenCalledWith([
      expect.objectContaining({ method: "group_compare", target_columns: ["value"], chart_type: "none" }),
      expect.objectContaining({ method: "describe" }),
    ]);

    // 删除
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
});
