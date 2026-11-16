import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { FakeWebSocket, installFakeWebSocket, jsonResponse, mockFetch } from "./test/mocks";

function setupFetch() {
  mockFetch([
    {
      path: "/sessions",
      method: "POST",
      respond: () => jsonResponse({ session_id: "s1", status: "discussing" }),
    },
    {
      path: "/capabilities",
      method: "GET",
      respond: () => jsonResponse({ tools: [], charts: [], planned: [], methodology: "m" }),
    },
    { path: "/templates", method: "GET", respond: () => jsonResponse({ templates: [] }) },
  ]);
}

function socket() {
  return FakeWebSocket.latest();
}

beforeEach(() => {
  installFakeWebSocket();
  vi.spyOn(console, "error").mockImplementation(() => {});
  setupFetch();
});

describe("App 事件流回放（036）", () => {
  it("chat_user 回放帧渲染用户气泡（刷新/重启后聊天上下文完整）", async () => {
    render(<App />);
    fireEvent.click(screen.getByTitle("新建会话空间"));
    await screen.findByRole("button", { name: /^会话 1/ });
    await screen.findByText("已连接");

    act(() => {
      socket().emit({ type: "chat_user", content: "回放的历史消息", seq: 3 });
    });

    expect(screen.getByText("回放的历史消息")).toBeInTheDocument();
  });

  it("review_user(revise) 回放帧渲染修正意见气泡", async () => {
    render(<App />);
    fireEvent.click(screen.getByTitle("新建会话空间"));
    await screen.findByRole("button", { name: /^会话 1/ });

    act(() => {
      socket().emit({ type: "review_user", decision: "revise", content: "换个图", seq: 9 });
    });

    expect(screen.getByText("修正意见：换个图")).toBeInTheDocument();
  });
});
