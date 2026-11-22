import { useEffect } from "react";
import { Eraser, X } from "lucide-react";

/** 清空工作区产出前的确认：提醒先下载，确认后才真正删除图表与报告。 */
export default function ClearOutputsDialog({
  onConfirm,
  onCancel,
}: {
  onConfirm: () => void;
  onCancel: () => void;
}) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onCancel]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="clear-outputs-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-primary-dark/45 p-4 backdrop-blur-[2px]"
    >
      <div className="w-full max-w-sm animate-fade-in-up rounded-2xl border border-ink/10 bg-white px-6 py-5 shadow-pop">
        <div className="flex items-center gap-2">
          <Eraser className="h-5 w-5 text-warn" aria-hidden="true" />
          <h3 id="clear-outputs-title" className="text-sm font-semibold text-primary-dark">
            清空工作台既往产出
          </h3>
        </div>
        <p className="mt-2 text-xs leading-relaxed text-ink">
          将删除本会话工作区中的统计表、图表与执行报告，导入的数据表格会保留。此操作不可恢复，请先下载需要留存的结果。
        </p>
        <div className="mt-4 flex items-center justify-end gap-2">
          <button
            type="button"
            className="inline-flex min-h-11 cursor-pointer items-center gap-1 rounded-lg px-3 text-xs text-ink-muted transition-colors duration-200 hover:text-primary-dark"
            onClick={onCancel}
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
            取消
          </button>
          <button
            type="button"
            className="inline-flex min-h-11 cursor-pointer items-center rounded-xl bg-danger px-4 text-xs font-medium text-white transition-colors duration-200 hover:brightness-110"
            onClick={onConfirm}
          >
            确认清空
          </button>
        </div>
      </div>
    </div>
  );
}
