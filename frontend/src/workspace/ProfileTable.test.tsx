import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ProfileTable from "./ProfileTable";
import { PROFILE } from "../test/mocks";

const baseProps = { profile: PROFILE, onSetColumnType: vi.fn(), onSetColumnTypes: vi.fn() };

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
});
