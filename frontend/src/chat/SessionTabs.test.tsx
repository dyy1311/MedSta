import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import SessionTabs from "./SessionTabs";

const sessions = [
  { sessionId: "s1", datasetId: "d1", name: "d.csv" },
  { sessionId: "s2", datasetId: null, name: "未绑定" },
];

describe("SessionTabs（批次12/13 会话管理）", () => {
  it("每个标签有删除按钮，点击携带对应会话 id", () => {
    const onDelete = vi.fn();
    render(
      <SessionTabs
        sessions={sessions}
        activeId="s1"
        onSelect={() => {}}
        onCreate={() => {}}
        onDelete={onDelete}
      />
    );

    const buttons = screen.getAllByTitle("删除会话");
    expect(buttons).toHaveLength(2);
    fireEvent.click(buttons[0]);
    expect(onDelete).toHaveBeenCalledWith("s1");
    fireEvent.click(buttons[1]);
    expect(onDelete).toHaveBeenCalledWith("s2");
  });

  it("传入 onCleanupDuplicates 时渲染「清理重复」按钮并回调（批次13）", () => {
    const onCleanup = vi.fn();
    render(
      <SessionTabs
        sessions={sessions}
        activeId="s1"
        onSelect={() => {}}
        onCreate={() => {}}
        onCleanupDuplicates={onCleanup}
      />
    );

    fireEvent.click(screen.getByTitle("清理重复会话"));
    expect(onCleanup).toHaveBeenCalledTimes(1);
  });

  it("未传 onDelete/onCleanupDuplicates 时不渲染删除与清理按钮（向后兼容）", () => {
    render(
      <SessionTabs
        sessions={sessions}
        activeId="s1"
        onSelect={() => {}}
        onCreate={() => {}}
      />
    );
    expect(screen.queryAllByTitle("删除会话")).toHaveLength(0);
    expect(screen.queryAllByTitle("清理重复会话")).toHaveLength(0);
  });
});
