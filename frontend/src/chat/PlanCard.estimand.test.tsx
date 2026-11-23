import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import PlanCard from "./PlanCard";
import type { EstimandSpec, PlanOption, PlanStep } from "../types";

const STEPS: PlanStep[] = [
  {
    title: "两组比较",
    method: "group_compare",
    target_columns: ["value"],
    chart_type: "none",
    params: { group_column: "group" },
    rationale: "比较两组均值",
  },
];

const OPTIONS: PlanOption[] = [
  { id: "go", label: "按此执行", action: "confirm", description: "" },
];

const FULL: EstimandSpec = {
  population: "接受手术的成年患者",
  variable: "术后 12 个月 JOA 评分",
  treatment: "手术组 vs 保守治疗组",
  intercurrent_events: [{ event: "中途停药", strategy: "treatment-policy" }],
  summary_measure: "两组均数差",
};

function renderCard(estimand: EstimandSpec | null, sapStatus: string) {
  return render(
    <PlanCard
      message="方案说明"
      steps={STEPS}
      options={OPTIONS}
      estimand={estimand}
      sapStatus={sapStatus}
      confirming={false}
      onOption={vi.fn()}
    />
  );
}

describe("PlanCard 估计目标", () => {
  it("五要素齐全默认折叠，展开后逐项展示", () => {
    renderCard(FULL, "estimand_declared");

    expect(screen.getByText("已声明估计目标")).toBeInTheDocument();
    expect(screen.queryByText("接受手术的成年患者")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("查看估计目标"));

    expect(screen.getByText("接受手术的成年患者")).toBeInTheDocument();
    expect(screen.getByText("术后 12 个月 JOA 评分")).toBeInTheDocument();
    expect(screen.getByText(/中途停药（treatment-policy）/)).toBeInTheDocument();
    expect(screen.getByText("两组均数差")).toBeInTheDocument();
  });

  it("探索性默认展开并列出缺失要素", () => {
    renderCard({ ...FULL, treatment: "" }, "exploratory");

    expect(screen.getByText("探索性分析")).toBeInTheDocument();
    expect(screen.getByText("缺少要素：处理与对照")).toBeInTheDocument();
    expect(screen.getByText("未填写")).toBeInTheDocument();
  });

  it("未给出估计目标时显示提示而非空白", () => {
    renderCard(null, "exploratory");

    expect(screen.getByText("探索性分析")).toBeInTheDocument();
    expect(screen.getByText(/模型未给出估计目标/)).toBeInTheDocument();
    expect(screen.queryByText("查看估计目标")).not.toBeInTheDocument();
  });
});
