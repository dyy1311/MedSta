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
      group_param: "group_column",
    },
    {
      name: "impute",
      title: "缺失值插补",
      category: "描述与质检",
      description: "MICE/简单插补，产出新数据集",
      task: "描述",
      applicability: "存在缺失的数据",
      slots: [],
      params: [{ name: "method", type: "choice", required: false, description: "插补方法", choices: ["mice", "median"], default: "mice" }],
      charts: ["none"],
      accepts: ["continuous", "ordinal"],
    },
    {
      name: "mcnemar_test",
      title: "配对四格表",
      category: "组间比较",
      description: "配对分类比较",
      task: "因果",
      applicability: "配对二分类",
      slots: [],
      params: [],
      charts: ["none"],
      accepts: ["categorical"],
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
    {
      path: "/templates/import",
      method: "POST",
      respond: () => jsonResponse({ ok: true, name: "外来的" }),
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
    await renderBuilder();

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
    await renderBuilder(
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

  // ---- 037：类型置灰 / 管道提示 / 模板导入导出 ----

  it("037: 数据列类型与 accepts 完全不相交的工具置灰", async () => {
    await renderBuilder({
      columnTypes: { group: "continuous", value: "continuous", age: "continuous" },
    });

    const mcnemar = screen.getByRole("option", { name: /配对四格表/ }) as HTMLOptionElement;
    expect(mcnemar).toBeDisabled();

    const describe = screen.getByRole("option", { name: "描述性统计" }) as HTMLOptionElement;
    expect(describe).not.toBeDisabled();
  });

  it("037: 链含 impute 步骤时显示管道提示", async () => {
    await renderBuilder();

    fireEvent.change(screen.getByLabelText("统计工具"), { target: { value: "impute" } });
    fireEvent.click(screen.getByLabelText("value"));
    fireEvent.click(screen.getByRole("button", { name: /添加到工作链/ }));

    expect(screen.getByTestId("pipeline-hint")).toHaveTextContent("后续步骤将使用插补数据");
  });

  it("037: 模板可导出（链接）与导入（读文件后 POST /templates/import）", async () => {
    await renderBuilder(
      {},
      [{ name: "我的套路", steps: TPL_STEPS, created_at: "t", updated_at: "t" }]
    );

    // 导出：模板列表项的下载链接指向 export 端点
    const exportLink = screen.getByRole("link", { name: "导出 我的套路" });
    expect(exportLink).toHaveAttribute(
      "href",
      `/templates/${TPL_NAME_ENC}/export`
    );

    // 导入：读取 JSON 文件后 POST /templates/import
    const importInput = screen.getByTestId("import-template-input") as HTMLInputElement;
    const file = new File(
      [JSON.stringify({ name: "外来的", steps: TPL_STEPS })],
      "tpl.json",
      { type: "application/json" }
    );
    fireEvent.change(importInput, { target: { files: [file] } });

    await waitFor(() => {
      const post = fetchSpy.mock.calls.find(
        ([url, init]) =>
          url === "/templates/import" && (init as RequestInit)?.method === "POST"
      );
      expect(post).toBeTruthy();
      const body = JSON.parse(String(post![1]?.body));
      expect(body.name).toBe("外来的");
      expect(body.steps).toHaveLength(1);
    });
  });
});

describe("ChainBuilder 类型前置提示（对齐执行期校验）", () => {
  it("类别列误选为目标列时提示，并可一键设为分组列", async () => {
    await renderBuilder({
      columns: ["sex", "value"],
      columnTypes: { sex: "categorical", value: "continuous" },
    });

    fireEvent.change(screen.getByLabelText("统计工具"), { target: { value: "group_compare" } });
    fireEvent.click(screen.getByLabelText("sex"));

    const warning = await screen.findByTestId("target-type-warning");
    expect(warning).toHaveTextContent("sex");
    expect(warning).toHaveTextContent("分组变量");

    fireEvent.click(screen.getByRole("button", { name: /设为分组列/ }));

    expect(screen.getByLabelText("sex")).not.toBeChecked();
    expect(screen.getByLabelText("group_column（必填）")).toHaveValue("sex");
    expect(screen.queryByTestId("target-type-warning")).not.toBeInTheDocument();
  });

  it("目标列类型合法时不显示提示", async () => {
    await renderBuilder({
      columns: ["sex", "value"],
      columnTypes: { sex: "categorical", value: "continuous" },
    });

    fireEvent.change(screen.getByLabelText("统计工具"), { target: { value: "group_compare" } });
    fireEvent.click(screen.getByLabelText("value"));

    expect(screen.queryByTestId("target-type-warning")).not.toBeInTheDocument();
  });
});
