import { useEffect, useRef, useState } from "react";

/** 数据文件扩展名白名单（与后端 parser 一致：csv/xlsx/xls） */
export const DATA_FILE_PATTERN = /\.(csv|xlsx|xls)$/i;

/**
 * 全局拖拽导入（042）：拖数据文件到窗口任意位置 → drop 后交给回调。
 * 多文件顺序处理（非并发），非数据扩展名静默忽略。
 * 返回 dragOver 驱动全屏遮罩反馈。
 */
export function useFileDrop(onFiles: (file: File) => void | Promise<void>) {
  const [dragOver, setDragOver] = useState(false);
  const callbackRef = useRef(onFiles);
  callbackRef.current = onFiles;

  useEffect(() => {
    const isFileDrag = (event: DragEvent) =>
      Array.from(event.dataTransfer?.types ?? []).includes("Files");

    const onDragOver = (event: DragEvent) => {
      if (!isFileDrag(event)) return;
      event.preventDefault(); // 允许 drop
      setDragOver(true);
    };
    const onDragLeave = (event: DragEvent) => {
      if (event.relatedTarget === null) setDragOver(false);
    };
    const onDrop = async (event: DragEvent) => {
      event.preventDefault();
      setDragOver(false);
      const files = Array.from(event.dataTransfer?.files ?? []).filter((file) =>
        DATA_FILE_PATTERN.test(file.name)
      );
      for (const file of files) {
        // 顺序上传：避免并发竞态（会话绑定/上传状态互踩）
        await callbackRef.current(file);
      }
    };

    window.addEventListener("dragover", onDragOver);
    window.addEventListener("dragleave", onDragLeave);
    window.addEventListener("drop", onDrop);
    return () => {
      window.removeEventListener("dragover", onDragOver);
      window.removeEventListener("dragleave", onDragLeave);
      window.removeEventListener("drop", onDrop);
    };
  }, []);

  return { dragOver };
}
