import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { installFakeWebSocket, jsonResponse, mockFetch } from "./test/mocks";

/** 044 多用户：登录卡、令牌存储、会话列表恢复 */
describe("App 多用户登录（044）", () => {
  beforeEach(() => {
    installFakeWebSocket();
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  function setupBackend() {
    let sessionListStatus = 401;
    mockFetch([
      {
        path: "/sessions",
        method: "GET",
        respond: () =>
          sessionListStatus === 401
            ? jsonResponse({ detail: "not logged in" }, 401)
            : jsonResponse({
                sessions: [
                  {
                    session_id: "restored-1",
                    name: "cohort.csv",
                    status: "delivered",
                    dataset_id: "ds1",
                  },
                ],
              }),
      },
      {
        path: "/auth/login",
        method: "POST",
        respond: () => {
          sessionListStatus = 200;
          return jsonResponse({ token: "tok-1", username: "alice" });
        },
      },
      {
        path: "/capabilities",
        method: "GET",
        respond: () => jsonResponse({ tools: [], charts: [], planned: [], methodology: "m" }),
      },
      { path: "/templates", method: "GET", respond: () => jsonResponse({ templates: [] }) },
    ]);
    return () => sessionListStatus;
  }

  it("B6: 401 显示登录卡；登录成功后加载恢复会话列表并存储令牌", async () => {
    const getStatus = setupBackend();
    render(<App />);

    expect(await screen.findByTestId("login-card")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("用户名"), { target: { value: "alice" } });
    fireEvent.change(screen.getByPlaceholderText("密码"), { target: { value: "pw1" } });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    await waitFor(() => {
      expect(getStatus()).toBe(200);
    });
    expect(await screen.findByRole("button", { name: /^会话（/ })).toBeInTheDocument();
    // 恢复会话条目显示绑定表格名（自动选中后 Tab 与工作区/绑定提示都会出现该名字）
    expect(screen.getAllByText(/cohort\.csv/).length).toBeGreaterThan(0);
    expect(localStorage.getItem("medsta_token")).toBe("tok-1");
  });

  it("B7: 错误凭据提示且不进入主界面（不建立 WS）", async () => {
    setupBackend();
    render(<App />);
    await screen.findByTestId("login-card");

    vi.spyOn(window, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "用户名或密码错误" }), { status: 401 })
    );
    fireEvent.change(screen.getByPlaceholderText("用户名"), { target: { value: "alice" } });
    fireEvent.change(screen.getByPlaceholderText("密码"), { target: { value: "bad" } });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    expect(await screen.findByText("用户名或密码错误")).toBeInTheDocument();
    expect(screen.getByTestId("login-card")).toBeInTheDocument();
  });
});
