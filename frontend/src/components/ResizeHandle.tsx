import type { PointerEvent as ReactPointerEvent } from "react";

interface Props {
  onPointerDown: (event: ReactPointerEvent) => void;
  label: string;
  /** 竖条调宽（三栏）或横条调高（工作区上下） */
  orientation?: "vertical" | "horizontal";
  testId?: string;
}

/** 拖拽分隔条：指针按下后由窗口级 move/up 改尺寸，避免指针离开条就丢。 */
export default function ResizeHandle({
  onPointerDown,
  label,
  orientation = "vertical",
  testId,
}: Props) {
  const vertical = orientation === "vertical";
  return (
    <div
      role="separator"
      tabIndex={0}
      data-testid={testId}
      aria-orientation={vertical ? "vertical" : "horizontal"}
      aria-label={label}
      onPointerDown={onPointerDown}
      className={
        vertical
          ? "group hidden w-1.5 shrink-0 cursor-col-resize items-center justify-center bg-surface-page lg:flex"
          : "group flex h-1.5 w-full shrink-0 cursor-row-resize items-center justify-center bg-surface-page hover:bg-primary/10"
      }
      title={vertical ? "拖拽调整宽度" : "拖拽调整高度"}
    >
      <div
        className={
          vertical
            ? "h-14 w-0.5 rounded-full bg-ink/10 transition-colors group-hover:bg-primary/60"
            : "h-0.5 w-14 rounded-full bg-ink/10 transition-colors group-hover:bg-primary/60"
        }
      />
    </div>
  );
}
