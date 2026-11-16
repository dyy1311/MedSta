import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ResultTable, { resultToSections } from "./ResultTable";

describe("ResultTable 结果 JSON 转表格", () => {
  it("标量键值渲染为指标表，数字保留精度", () => {
    render(<ResultTable result={{ test: "t", p_value: 0.0312, n: 24 }} />);

    expect(screen.getByText("test")).toBeInTheDocument();
    expect(screen.getByText("t")).toBeInTheDocument();
    expect(screen.getByText("p_value")).toBeInTheDocument();
    expect(screen.getByText("0.0312")).toBeInTheDocument();
  });

  it("对象数组渲染为动态列子表", () => {
    render(
      <ResultTable
        result={{
          pairwise: [
            { group: "A-B", p_value: 0.02 },
            { group: "A-C", p_value: 0.31 },
          ],
        }}
      />
    );

    expect(screen.getByText("pairwise")).toBeInTheDocument();
    expect(screen.getByText("A-B")).toBeInTheDocument();
    expect(screen.getByText("0.31")).toBeInTheDocument();
  });

  it("跳过 method_note/strategy 等元键（另有专属 UI）", () => {
    const sections = resultToSections({
      method_note: "教材口径说明",
      strategy: { steps: ["x"], final_method: "t", alternative: "y" },
      p_value: 0.5,
    });

    expect(sections).toHaveLength(1);
    expect(sections[0].kind === "kv" && sections[0].rows).toEqual([["p_value", "0.5"]]);
  });

  it("空结果渲染 null", () => {
    const { container } = render(<ResultTable result={{}} />);
    expect(container.querySelector("table")).toBeNull();
  });
});
