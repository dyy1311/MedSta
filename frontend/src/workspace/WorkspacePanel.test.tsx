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
    expect(screen.getByText("执行产出（1）")).toBeInTheDocument();
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

    fireEvent.click(screen.getByRole("button", { name: /导入表格/ }));
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["a"], "new.csv")] } });

    expect(onUpload).toHaveBeenCalledTimes(1);
    expect(onUpload.mock.calls[0][0]).toBeInstanceOf(File);
  });

  it("修改列类型下拉会回调 onSetColumnType", () => {
    const onSetColumnType = vi.fn();
    render(
      <WorkspacePanel
        {...baseProps}
        onSetColumnType={onSetColumnType}
        workspaces={[workspace()]}
      />
    );

    const selects = screen.getAllByRole("combobox");
    fireEvent.change(selects[1], { target: { value: "index" } });

    expect(onSetColumnType).toHaveBeenCalledWith("value", "index");
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
    expect(screen.getByText("分布统计")).toBeInTheDocument();
    expect(screen.getByText("两组比较")).toBeInTheDocument();
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

  it("提供下载链接", () => {
    render(<ChartCard baseUrl="/data/s1/d1/artifacts" filename="chart.png" />);

    const download = screen.getByTitle("下载");
    expect(download).toHaveAttribute("href", "/data/s1/d1/artifacts/chart.png");
    expect(download).toHaveAttribute("download", "chart.png");
  });
});
