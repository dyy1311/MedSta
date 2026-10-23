import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ReviewCard from "./ReviewCard";
import { REPORT } from "../test/mocks";
import type { ExecutionReport } from "../types";

const WITH_INTERPRETATION: ExecutionReport = {
  ...REPORT,
  interpretation: {
    summary: "本次描述统计显示 value 分布较均匀。",
    steps: [
      { step_index: 0, finding: "value 的中位数为 4（n=6）。", caveat: "样本量偏小，解释需谨慎" },
    ],
    caveats: ["本次为探索性分析，未经 SAP 冻结与样本量论证。"],
    unverified_numbers: ["42.7"],
  },
};

const baseProps = {
  delivered: false,
  sessionId: "s1",
  artifactBase: "",
  onAccept: vi.fn(),
  onRevise: vi.fn(),
};

describe("ReviewCard 结果解读", () => {
  it("渲染汇总、逐步结论与全局注意事项", () => {
    render(<ReviewCard {...baseProps} report={WITH_INTERPRETATION} />);

    expect(screen.getByText("本次描述统计显示 value 分布较均匀。")).toBeInTheDocument();
    expect(screen.getByText("value 的中位数为 4（n=6）。")).toBeInTheDocument();
    expect(screen.getByText("样本量偏小，解释需谨慎")).toBeInTheDocument();
    expect(screen.getByText(/未经 SAP 冻结/)).toBeInTheDocument();
  });

  it("未核验数值以角标提示而不隐藏结论", () => {
    render(<ReviewCard {...baseProps} report={WITH_INTERPRETATION} />);

    expect(screen.getByText(/含未核验数值：42.7/)).toBeInTheDocument();
    expect(screen.getByText("value 的中位数为 4（n=6）。")).toBeInTheDocument();
  });

  it("没有解读时不渲染解读区域", () => {
    render(<ReviewCard {...baseProps} report={REPORT} />);

    expect(screen.queryByText(/含未核验数值/)).not.toBeInTheDocument();
    expect(screen.queryByText(/未经 SAP 冻结/)).not.toBeInTheDocument();
  });

  it("交付态提供「调整分析方案」入口", () => {
    const onRevise = vi.fn();
    render(
      <ReviewCard {...baseProps} report={REPORT} delivered onRevise={onRevise} />
    );

    fireEvent.click(screen.getByRole("button", { name: /调整分析方案/ }));

    expect(onRevise).toHaveBeenCalledWith("");
  });
});
