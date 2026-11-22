import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import UploadChoiceDialog from "./UploadChoiceDialog";

describe("UploadChoiceDialog（046 数据去向选择）", () => {
  it("展示文件名与会话名，三按钮语义精确回调（B3–B6）", () => {
    const onChoose = vi.fn();
    const onCancel = vi.fn();

    render(
      <UploadChoiceDialog
        filename="新数据.csv"
        sessionName="会话一"
        onChoose={onChoose}
        onCancel={onCancel}
      />
    );

    expect(screen.getByText(/新数据\.csv/)).toBeTruthy();
    expect(screen.getByText(/会话一/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /加入当前工作区/ }));
    expect(onChoose).toHaveBeenCalledTimes(1);
    expect(onChoose).toHaveBeenCalledWith("current");

    fireEvent.click(screen.getByRole("button", { name: /新建会话/ }));
    expect(onChoose).toHaveBeenCalledTimes(2);
    expect(onChoose).toHaveBeenCalledWith("new");

    fireEvent.click(screen.getByRole("button", { name: /取消/ }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
