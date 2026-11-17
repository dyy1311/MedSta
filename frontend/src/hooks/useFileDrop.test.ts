import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useFileDrop } from "./useFileDrop";

function dropWith(files: File[]) {
  const event = new Event("drop");
  Object.defineProperty(event, "dataTransfer", { value: { files, types: ["Files"] } });
  window.dispatchEvent(event);
}

function dragOverWithFiles() {
  const event = new Event("dragover");
  Object.defineProperty(event, "dataTransfer", { value: { types: ["Files"] } });
  window.dispatchEvent(event);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useFileDrop 拖拽导入（042）", () => {
  it("B1: 拖文件悬停 dragOver 置真", () => {
    const { result } = renderHook(() => useFileDrop(() => undefined));
    expect(result.current.dragOver).toBe(false);

    act(() => {
      dragOverWithFiles();
    });
    expect(result.current.dragOver).toBe(true);
  });

  it("B2: drop csv 文件交给回调；非数据扩展名忽略（B3）", async () => {
    const onFiles = vi.fn().mockResolvedValue(undefined);
    renderHook(() => useFileDrop(onFiles));

    await act(async () => {
      dropWith([new File(["a"], "data.csv"), new File(["b"], "notes.txt")]);
    });

    expect(onFiles).toHaveBeenCalledTimes(1);
    expect(onFiles.mock.calls[0][0].name).toBe("data.csv");
  });

  it("B4: 多文件顺序上传（前一个完成后才调用下一个）", async () => {
    const order: string[] = [];
    const onFiles = vi.fn(async (file: File) => {
      order.push(`start:${file.name}`);
      await new Promise((resolve) => setTimeout(resolve, 20));
      order.push(`end:${file.name}`);
    });
    renderHook(() => useFileDrop(onFiles));

    await act(async () => {
      dropWith([new File(["a"], "a.csv"), new File(["b"], "b.csv")]);
      await new Promise((resolve) => setTimeout(resolve, 80)); // 让顺序队列跑完
    });

    expect(onFiles).toHaveBeenCalledTimes(2);
    // 顺序：第一个完整结束后才开始第二个
    expect(order).toEqual(["start:a.csv", "end:a.csv", "start:b.csv", "end:b.csv"]);
  });

  it("drop 后 dragOver 复位", async () => {
    const { result } = renderHook(() => useFileDrop(() => undefined));
    act(() => {
      dragOverWithFiles();
    });
    expect(result.current.dragOver).toBe(true);

    await act(async () => {
      dropWith([]);
    });
    expect(result.current.dragOver).toBe(false);
  });
});
