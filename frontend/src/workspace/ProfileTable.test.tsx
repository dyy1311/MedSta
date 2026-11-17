import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ProfileTable from "./ProfileTable";
import { PROFILE } from "../test/mocks";

const baseProps = {
  profile: PROFILE,
  onSetColumnType: vi.fn(),
  onSetColumnTypes: vi.fn(),
  onSuggestTypes: vi.fn(),
  suggestions: [
    { name: "value", suggested_type: "ordinal", confidence: 0.9, reason: "1-5 评分等级" },
    { name: "group", suggested_type: "categorical", confidence: 0.95, reason: "无序分组" },
  ] as {
    name: string;
    suggested_type: string;
    confidence: number;
    reason: string;
  }[],
};

describe("ProfileTable 批量列类型修改", () => {
  it("B1: 勾选多列显示选中计数，全选框控制全部列", () => {
    render(<ProfileTable {...baseProps} />);

    fireEvent.click(screen.getByLabelText("选择列 group"));
    expect(screen.getByText("已选 1 列")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("全选列"));
    expect(screen.getByText("已选 2 列")).toBeInTheDocument(); // PROFILE 共 2 列

    fireEvent.click(screen.getByLabelText("全选列"));
    expect(screen.queryByText("已选 2 列")).not.toBeInTheDocument();
  });

  it("B2: 选择批量类型并应用 → 一次回调 {列: 类型}", () => {
    const onSetColumnTypes = vi.fn();
    render(<ProfileTable {...baseProps} onSetColumnTypes={onSetColumnTypes} />);

    fireEvent.click(screen.getByLabelText("选择列 group"));
    fireEvent.click(screen.getByLabelText("选择列 value"));
    fireEvent.change(screen.getByLabelText("批量类型"), { target: { value: "ordinal" } });
    fireEvent.click(screen.getByRole("button", { name: "应用类型" }));

    expect(onSetColumnTypes).toHaveBeenCalledWith({
      group: "ordinal",
      value: "ordinal",
    });
  });

  it("B3: 未选中时批量控件禁用", () => {
    render(<ProfileTable {...baseProps} />);

    expect(screen.getByLabelText("批量类型")).toBeDisabled();
    expect(screen.getByRole("button", { name: "应用类型" })).toBeDisabled();
  });

  it("B5a: 「AI 确认类型」按钮触发建议请求", () => {
    render(<ProfileTable {...baseProps} />);

    fireEvent.click(screen.getByRole("button", { name: "AI 确认类型" }));

    expect(baseProps.onSuggestTypes).toHaveBeenCalled();
  });

  it("B5b: 建议徽标渲染（类型+理由），单列与全部采纳可用", () => {
    const onSetColumnType = vi.fn();
    const onSetColumnTypes = vi.fn();
    render(
      <ProfileTable
        {...baseProps}
        onSetColumnType={onSetColumnType}
        onSetColumnTypes={onSetColumnTypes}
      />
    );

    expect(screen.getByText("建议: 数值-等级型（90%）")).toBeInTheDocument();
    expect(screen.getByText("1-5 评分等级")).toBeInTheDocument();

    // 单列采纳
    fireEvent.click(screen.getByTitle("采纳建议：value"));
    expect(onSetColumnType).toHaveBeenCalledWith("value", "ordinal");

    // 全部采纳
    fireEvent.click(screen.getByRole("button", { name: "全部采纳建议" }));
    expect(onSetColumnTypes).toHaveBeenCalledWith({
      value: "ordinal",
      group: "categorical",
    });
  });
});
