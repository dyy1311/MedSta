import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import WorkspacePanel from "./WorkspacePanel";
import type { WorkspaceTab } from "../types";
import { PROFILE } from "../test/mocks";

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
  uploading: false,
  onActivate: vi.fn(),
  onUpload: vi.fn(),
  onSetColumnType: vi.fn(),
};

describe("WorkspacePanel 插补数据集", () => {
  it("插补工作区显示「已插补」角标与方差警示", () => {
    const imputed = workspace({
      datasetId: "d2",
      name: "cohort.csv（MICE 插补）",
      imputed: true,
    });

    render(
      <WorkspacePanel
        {...baseProps}
        activeId="d2"
        workspaces={[workspace(), imputed]}
      />
    );

    expect(screen.getAllByText("已插补").length).toBeGreaterThan(0);
    expect(screen.getByText(/MICE 单数据集插补结果/)).toBeInTheDocument();
    expect(screen.getByText(/标准误偏小/)).toBeInTheDocument();
  });

  it("原始工作区不显示插补警示", () => {
    render(<WorkspacePanel {...baseProps} activeId="d1" workspaces={[workspace()]} />);

    expect(screen.queryByText("已插补")).not.toBeInTheDocument();
    expect(screen.queryByText(/MICE 单数据集插补结果/)).not.toBeInTheDocument();
  });
});
