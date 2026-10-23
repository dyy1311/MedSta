import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import {
  FakeWebSocket,
  PROFILE,
  installFakeWebSocket,
  jsonResponse,
  mockFetch,
} from "./test/mocks";

const UPLOAD_NOTICE = /数据「cohort.csv」已绑定当前会话/;

function setupFetch() {
  return mockFetch([
    {
      path: "/sessions",
      method: "POST",
      respond: () => jsonResponse({ session_id: "s1", status: "discussing" }),
    },
    {
      path: "/sessions/s1/data",
      method: "POST",
      respond: () =>
        jsonResponse({
          type: "data_profile",
          dataset_id: "d1",
          name: "cohort.csv",
          profile: PROFILE,
        }),
    },
    {
      path: "/capabilities",
      method: "GET",
      respond: () => jsonResponse({ tools: [], charts: [], planned: [], methodology: "x" }),
    },
  ]);
}

async function openSessionWithData(container: HTMLElement) {
  fireEvent.click(screen.getByTitle("新建会话空间"));
  await screen.findByRole("button", { name: /^会话 1/ });

  const input = container.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(["group,value\n"], "cohort.csv")] } });
  await screen.findByText(UPLOAD_NOTICE);
}

beforeEach(() => {
  installFakeWebSocket();
  vi.spyOn(console, "error").mockImplementation(() => {});
  setupFetch();
});

describe("插补数据集工作区", () => {
  it("收到 dataset_added 追加标签页但不切换 active", async () => {
    const { container } = render(<App />);
    await openSessionWithData(container);

    act(() => {
      FakeWebSocket.latest().emit({
        type: "dataset_added",
        dataset_id: "d2",
        name: "cohort.csv（MICE 插补）",
        profile: PROFILE,
        imputed: true,
        source_dataset_id: "d1",
      });
    });

    const added = await screen.findByRole("button", { name: /cohort\.csv（MICE 插补）/ });
    const original = screen.getByRole("button", { name: "cohort.csv" });

    expect(added).toBeInTheDocument();
    // active 仍是原始数据集：只有它带激活态的内阴影样式
    expect(original.className).toContain("inset");
    expect(added.className).not.toContain("inset");
  });

  it("提示文案说明已生成但未切换", async () => {
    const { container } = render(<App />);
    await openSessionWithData(container);

    act(() => {
      FakeWebSocket.latest().emit({
        type: "dataset_added",
        dataset_id: "d2",
        name: "cohort.csv（MICE 插补）",
        profile: PROFILE,
        imputed: true,
        source_dataset_id: "d1",
      });
    });

    expect(await screen.findByText(/已生成插补数据集/)).toBeInTheDocument();
    expect(screen.getAllByText("已插补").length).toBeGreaterThan(0);
  });
});
