import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ReviewCard from "./ReviewCard";
import { REPORT } from "../test/mocks";
import type { ExecutionReport } from "../types";

const NOTE = "§2：正态资料报告 x̄±s；偏态资料报告 M(P25~P75)。";

function reportWithNote(note?: string): ExecutionReport {
  return {
    steps: [
      {
        ...REPORT.steps[0],
        result: note ? { ...REPORT.steps[0].result, method_note: note } : { ...REPORT.steps[0].result },
      },
    ],
  };
}

const baseProps = {
  delivered: false,
  sessionId: "s1",
  artifactBase: "",
  onAccept: vi.fn(),
  onRevise: vi.fn(),
};

describe("ReviewCard 方法依据", () => {
  it("默认收起，展开后显示教材口径原文", () => {
    render(<ReviewCard {...baseProps} report={reportWithNote(NOTE)} />);

    const summary = screen.getByText("方法依据");
    expect(summary).toBeInTheDocument();
    expect(screen.queryByText(NOTE)).not.toBeInTheDocument();

    fireEvent.click(summary);

    expect(screen.getByText(NOTE)).toBeInTheDocument();
  });

  it("没有 method_note 时不渲染方法依据", () => {
    render(<ReviewCard {...baseProps} report={reportWithNote()} />);

    expect(screen.queryByText("方法依据")).not.toBeInTheDocument();
  });
});
