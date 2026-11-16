import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ErrorBoundary from "./ErrorBoundary";

function Boom(): never {
  throw new Error("渲染爆炸");
}

describe("ErrorBoundary 错误边界", () => {
  it("子组件抛错时显示 fallback 与重载按钮，而非白屏", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>
    );

    expect(screen.getByTestId("error-boundary")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /重新加载/ })).toBeInTheDocument();
    expect(screen.getByText("渲染爆炸")).toBeInTheDocument();
  });

  it("正常子树原样渲染；可注入自定义 fallback", () => {
    render(<ErrorBoundary>正常内容</ErrorBoundary>);
    expect(screen.getByText("正常内容")).toBeInTheDocument();

    const spy = vi.fn(() => <div data-testid="custom-fallback" />);
    render(
      <ErrorBoundary fallback={spy}>
        <Boom />
      </ErrorBoundary>
    );
    expect(screen.getByTestId("custom-fallback")).toBeInTheDocument();
  });
});
