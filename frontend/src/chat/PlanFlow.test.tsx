import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import PlanFlowView from "./PlanFlowView";
import type { PlanFlow } from "../types";

const FLOW: PlanFlow = {
  nodes: [
    {
      index: 0,
      id: "step_1",
      title: "分布统计",
      method: "describe",
      target_columns: ["value"],
      params: {},
      chart_type: "histogram",
      rationale: "连续变量先看分布",
      depends_on: [],
    },
    {
      index: 1,
      id: "step_2",
      title: "组间比较",
      method: "group_compare",
      target_columns: ["value"],
      params: { group_column: "group" },
      chart_type: "boxplot",
      rationale: "两组比较",
      depends_on: [0],
    },
  ],
  edges: [{ from: 0, to: 1 }],
  order: [0, 1],
  mermaid: "flowchart TD\n  n0[\"1. 分布统计<br/>describe\"]\n  n0 --> n1",
};

describe("PlanFlowView 工作流图", () => {
  it("按节点顺序渲染，标注依赖关系，并可展开参数", () => {
    render(<PlanFlowView flow={FLOW} />);

    expect(screen.getByTestId("plan-flow")).toHaveTextContent("工作流图（2 个节点）");
    expect(screen.getByTestId("flow-node-0")).toHaveTextContent("分布统计");
    expect(screen.getByTestId("flow-node-0")).toHaveTextContent("describe");
    expect(screen.getByTestId("flow-node-1")).toHaveTextContent("依赖 1");

    // 默认折叠：展开后才显示参数与依据
    expect(screen.queryByText(/group_column=group/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("flow-node-1").querySelector("button")!);

    expect(screen.getByText(/group_column=group/)).toBeInTheDocument();
    expect(screen.getByText(/两组比较/)).toBeInTheDocument();
  });

  it("提供 Mermaid 文本便于复制评审", () => {
    const { container } = render(<PlanFlowView flow={FLOW} />);
    expect(container.textContent).toContain("flowchart TD");
  });

  it("空图不渲染（旧后端无 flow 时不占位）", () => {
    const { container } = render(
      <PlanFlowView flow={{ nodes: [], edges: [], order: [], mermaid: "" }} />
    );
    expect(container.querySelector('[data-testid="plan-flow"]')).toBeNull();
  });
});
