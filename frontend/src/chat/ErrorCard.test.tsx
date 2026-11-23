import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ErrorCard from "./ErrorCard";

/**
 * 方案/工作链校验失败时，用户看到的不应是大段 JSON：
 * 结构化列出「哪一步、什么问题、怎么改」，原始 JSON 退为二级折叠。
 */
const ISSUES_DETAIL = {
  issues: [
    {
      code: "COLUMN_TYPE_MISMATCH",
      message: "列「是否手术」是categorical型，不适用于 group_compare",
      hint: "「是否手术」更像分组变量：target_columns 只放数值列，并在 params.group_column 里选它（至少 2 组）",
      step_index: 2,
    },
    {
      code: "COLUMN_TYPE_MISMATCH",
      message: "列「手术方式」是categorical型，不适用于 anova",
      hint: "改用 chi_square 比较组间构成",
      step_index: 8,
    },
  ],
};

describe("ErrorCard 方案校验详情", () => {
  it("展开后按条列出步骤/原因/修法，原始 JSON 收进二级折叠", () => {
    render(
      <ErrorCard
        code="INVALID_PLAN"
        message="工作链未通过校验"
        hint="检查各步骤的方法参数与目标列（详见 issues）"
        detail={ISSUES_DETAIL}
      />
    );

    expect(screen.queryByTestId("issue-list")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /查看详情/ }));

    const list = screen.getByTestId("issue-list");
    expect(list).toHaveTextContent("步骤 3"); // step_index 2 → 人类可读的 1 起
    expect(list).toHaveTextContent("步骤 9");
    expect(list).toHaveTextContent("列「是否手术」是categorical型，不适用于 group_compare");
    expect(list).toHaveTextContent("params.group_column");
    expect(list).toHaveTextContent("chi_square");

    // 原始 JSON 仍可查，但需要再点开一层
    expect(screen.getByText("原始 JSON")).toBeInTheDocument();
  });

  it("detail 不含 issues 时保持原样（只显示 JSON）", () => {
    render(
      <ErrorCard
        code="EXECUTION_FAILED"
        message="执行失败"
        detail={{ trace: "boom" }}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /查看详情/ }));
    expect(screen.queryByTestId("issue-list")).not.toBeInTheDocument();
    expect(screen.getByText(/"trace": "boom"/)).toBeInTheDocument();
  });
});
