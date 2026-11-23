import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ChartCard from "./ChartCard";
import WorkspacePanel from "./WorkspacePanel";
import type { ExecutionReport, WorkspaceTab } from "../types";
import { PROFILE, REPORT } from "../test/mocks";

function workspace(overrides: Partial<WorkspaceTab> = {}): WorkspaceTab {
  return {
    datasetId: "d1",
    name: "cohort.csv",
    profile: PROFILE,
    reports: [],
    sessionId: "s1",
    ...overrides,
  };
}

const baseProps = {
  sessionId: "s1",
  activeId: "d1",
  uploading: false,
  onActivate: vi.fn(),
  onUpload: vi.fn(),
  onSetColumnType: vi.fn(),
};

describe("WorkspacePanel", () => {
  it("无数据时展示空态引导", () => {
    render(<WorkspacePanel {...baseProps} workspaces={[]} activeId={null} />);

    expect(
      screen.getByText("上传数据并确认方案后，数据画像与图表将展示在这里")
    ).toBeInTheDocument();
  });

  it("渲染画像表、图表与表格交付，并带工作区 Tab", () => {
    render(<WorkspacePanel {...baseProps} workspaces={[workspace({ reports: [REPORT] })]} />);

    expect(screen.getByRole("button", { name: "cohort.csv" })).toBeInTheDocument();
    expect(screen.getByText("数据画像")).toBeInTheDocument();
    expect(screen.getByText("6 行 × 2 列")).toBeInTheDocument();
    expect(screen.getByText("统计表交付（1）")).toBeInTheDocument();
    expect(screen.getByText("图表交付（1）")).toBeInTheDocument();
    expect(screen.getByRole("separator", { name: "调整导入表格与图表交付高度" })).toBeInTheDocument();
    expect(screen.getByRole("separator", { name: "调整图表交付与表格区域高度" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "收起导入表格" }));
    expect(screen.queryByText("数据画像")).not.toBeInTheDocument();
    expect(screen.getAllByText("导入表格").length).toBeGreaterThan(0);
    expect(screen.getByText("图表交付（1）")).toBeInTheDocument();
    expect(screen.queryByRole("separator", { name: "调整导入表格与图表交付高度" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "展开导入表格" }));
    expect(screen.getByText("数据画像")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "CSV" })).toHaveAttribute(
      "href",
      "/export/s1/0?format=csv"
    );
    expect(screen.getByRole("link", { name: "Excel" })).toHaveAttribute(
      "href",
      "/export/s1/0?format=xlsx"
    );
    expect(screen.getByRole("img")).toHaveAttribute(
      "src",
      "/data/s1/d1/artifacts/step_0_describe_histogram.png"
    );
  });

  it("切换工作区 Tab 调用 onActivate", () => {
    const onActivate = vi.fn();
    render(
      <WorkspacePanel
        {...baseProps}
        onActivate={onActivate}
        workspaces={[workspace(), { ...workspace({ datasetId: "d2", name: "second.csv" }) }]}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "second.csv" }));

    expect(onActivate).toHaveBeenCalledWith("d2");
  });

  it("导入表格按钮触发文件选择并回调 onUpload", () => {
    const onUpload = vi.fn();
    const { container } = render(
      <WorkspacePanel {...baseProps} onUpload={onUpload} workspaces={[]} />
    );

    fireEvent.click(screen.getByRole("button", { name: "导入表格" }));
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["a"], "new.csv")] } });

    expect(onUpload).toHaveBeenCalledTimes(1);
    expect(onUpload.mock.calls[0][0]).toBeInstanceOf(File);
  });

  it("修改列类型下拉会回调 onSetColumnType（带当前工作区 datasetId）", () => {
    const onSetColumnType = vi.fn();
    render(
      <WorkspacePanel
        {...baseProps}
        onSetColumnType={onSetColumnType}
        workspaces={[workspace()]}
      />
    );

    const selects = screen.getAllByRole("combobox");
    // [0]=批量类型，[1..]=逐行类型下拉；value 是第 2 行
    fireEvent.change(selects[2], { target: { value: "index" } });

    // 修复：跨工作区编辑必须落到被编辑的数据集（此前误改会话绑定数据集）
    expect(onSetColumnType).toHaveBeenCalledWith("d1", "value", "index", undefined);
  });

  it("事后比较表新增 method 列可正常渲染", () => {
    const report: ExecutionReport = {
      steps: [
        {
          title: "多组比较",
          method: "anova",
          status: "success",
          artifact: null,
          table: {
            columns: ["group_a", "group_b", "mean_diff", "q_value", "method", "p_value"],
            rows: [
              {
                group_a: "A",
                group_b: "B",
                mean_diff: 2.0,
                q_value: 3.2,
                method: "tukey",
                p_value: 0.01,
              },
            ],
          },
          result: {},
        },
      ],
    };
    render(<WorkspacePanel {...baseProps} workspaces={[workspace({ reports: [report] })]} />);

    expect(screen.getByText("method")).toBeInTheDocument();
    expect(screen.getByText("tukey")).toBeInTheDocument();
  });

  it("多次执行的表格按顺序保留，且交错渲染", () => {
    const secondReport: ExecutionReport = {
      steps: [
        {
          title: "两组比较",
          method: "group_compare",
          status: "success",
          artifact: null,
          table: {
            columns: ["test", "p_value"],
            rows: [{ test: "t", p_value: 0.01 }],
          },
          result: {},
        },
      ],
    };
    render(
      <WorkspacePanel {...baseProps} workspaces={[workspace({ reports: [REPORT, secondReport] })]} />
    );

    expect(screen.getByText("统计表交付（2）")).toBeInTheDocument();
    expect(screen.getAllByText("分布统计").length).toBeGreaterThan(0);
    expect(screen.getAllByText("两组比较").length).toBeGreaterThan(0);
    // 第二次报告的步骤序号从 0 开始，导出链接按报告内 step_index
    const links = screen.getAllByRole("link", { name: "CSV" });
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "/export/s1/0?format=csv",
      "/export/s1/0?format=csv",
    ]);
  });
});

describe("ChartCard", () => {
  it("图片加载失败时显示可恢复提示", () => {
    render(<ChartCard baseUrl="/data/s1/d1/artifacts" filename="chart.png" />);

    fireEvent.error(screen.getByRole("img"));

    expect(
      screen.getByText("图表生成中或不存在（后端重启后重新执行即可）")
    ).toBeInTheDocument();
  });

  it("支持放大查看与关闭", () => {
    const { container } = render(
      <ChartCard baseUrl="/data/s1/d1/artifacts" filename="chart.png" />
    );

    fireEvent.click(screen.getByTitle("放大"));

    expect(container.querySelectorAll("img")).toHaveLength(2);
    const overlay = container.querySelector(".fixed.inset-0") as HTMLElement;
    fireEvent.click(overlay);

    expect(container.querySelectorAll("img")).toHaveLength(1);
  });

  it("提供下载链接与多格式导出", () => {
    render(
      <ChartCard
        baseUrl="/data/s1/d1/artifacts"
        filename="chart.png"
        extraFormats={[
          { label: "JPG", href: "/export/s1/0?format=jpg" },
          { label: "PDF", href: "/export/s1/0?format=pdf" },
        ]}
      />
    );

    const download = screen.getByTitle("下载 PNG");
    expect(download).toHaveAttribute("href", "/data/s1/d1/artifacts/chart.png");
    expect(download).toHaveAttribute("download", "chart.png");
    expect(screen.getByTitle("下载 JPG")).toHaveAttribute("href", "/export/s1/0?format=jpg");
    expect(screen.getByTitle("下载 PDF")).toHaveAttribute("href", "/export/s1/0?format=pdf");
  });

  it("报告带 report_id 时导出链接携带该参数（历史报告可寻址导出）", () => {
    const reportWithId: ExecutionReport = { ...REPORT, report_id: "abc12345" };
    render(<WorkspacePanel {...baseProps} workspaces={[workspace({ reports: [reportWithId] })]} />);

    expect(screen.getByRole("link", { name: "CSV" })).toHaveAttribute(
      "href",
      "/export/s1/0?format=csv&report_id=abc12345"
    );
    expect(screen.getByRole("link", { name: "Excel" })).toHaveAttribute(
      "href",
      "/export/s1/0?format=xlsx&report_id=abc12345"
    );
  });

  it("导出报告：风格与格式选择正确拼入下载链接（040）", () => {
    render(<WorkspacePanel {...baseProps} workspaces={[workspace({ reports: [REPORT] })]} />);

    // 默认：学术风 docx
    expect(screen.getByRole("link", { name: "导出报告" })).toHaveAttribute(
      "href",
      "/report/s1?style=academic&format=docx"
    );

    // 用户自主切换风格与格式
    fireEvent.change(screen.getByLabelText("报告风格"), { target: { value: "lite" } });
    fireEvent.change(screen.getByLabelText("报告格式"), { target: { value: "pdf" } });
    expect(screen.getByRole("link", { name: "导出报告" })).toHaveAttribute(
      "href",
      "/report/s1?style=lite&format=pdf"
    );
  });
});

describe("图表按轮次倒序展示", () => {
  const OLD_REPORT = {
    report_id: "r1",
    steps: [
      {
        title: "主要指标分布描述",
        method: "describe",
        status: "success",
        artifact: "old_hist.png",
        result: {},
      },
    ],
  };
  const NEW_REPORT = {
    report_id: "r2",
    steps: [
      {
        title: "主要指标分布描述",
        method: "describe",
        status: "success",
        artifact: "new_hist.png",
        result: {},
      },
    ],
  };

  it("所有轮次的图表都展示，最新交付的排在最上面", () => {
    const tab = workspace({ reports: [OLD_REPORT, NEW_REPORT] });
    const { container } = render(
      <WorkspacePanel
        sessionId="s1"
        workspaces={[tab]}
        activeId={tab.datasetId}
        uploading={false}
        onActivate={vi.fn()}
        onSetColumnType={vi.fn()}
        onUpload={vi.fn()}
      />
    );

    expect(screen.getByText(/图表交付（2）/)).toBeInTheDocument();
    const images = [...container.querySelectorAll("img")];
    expect(images.map((node) => node.getAttribute("src"))).toEqual([
      "/data/s1/d1/artifacts/new_hist.png",
      "/data/s1/d1/artifacts/old_hist.png",
    ]);
    expect(screen.queryByTestId("previous-rounds")).not.toBeInTheDocument();
  });
});
