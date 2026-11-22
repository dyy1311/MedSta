import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ChainBuilder from "./ChainBuilder";
import { jsonResponse, mockFetch } from "../test/mocks";

/** 内置推荐流程暂不引入：入口关掉，后端 /templates/builtin 仍可保留。 */

const TOOLS = {
  tools: [
    {
      name: "describe",
      title: "描述统计",
      category: "描述",
      task: "describe",
      charts: ["histogram", "none"],
      accepts: [],
      params: [{ name: "group_by", type: "column", required: false, description: "", choices: [] }],
    },
  ],
  charts: [{ name: "histogram", label: "histogram" }],
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("推荐流程暂不引入", () => {
  it("不渲染内置推荐流程入口，也不请求 /templates/builtin", async () => {
    const spy = mockFetch([
      { path: "/capabilities", method: "GET", respond: () => jsonResponse(TOOLS) },
      { path: "/templates", method: "GET", respond: () => jsonResponse({ templates: [] }) },
    ]);
    render(
      <ChainBuilder
        sessionId="s1"
        columns={["value"]}
        columnTypes={{ value: "continuous" }}
        busy={false}
        importSteps={null}
        onRun={vi.fn()}
      />
    );

    expect(await screen.findByText("工具装配")).toBeInTheDocument();
    expect(screen.queryByTestId("builtin-recipes")).not.toBeInTheDocument();
    expect(screen.queryByText("推荐流程")).not.toBeInTheDocument();
    const urls = spy.mock.calls.map((call) => String(call[0]));
    expect(urls.some((url) => url.includes("/templates/builtin"))).toBe(false);
  });
});
