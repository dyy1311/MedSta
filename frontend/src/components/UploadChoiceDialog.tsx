import { FileSpreadsheet, Layers, Plus, X } from "lucide-react";

/** 046 数据去向选择：已绑定数据的会话再上传时，让用户决定这份数据
 *  是「加入当前工作区（同会话新增数据集标签）」还是「新建会话」。 */
export default function UploadChoiceDialog({
  filename,
  sessionName,
  onChoose,
  onCancel,
}: {
  filename: string;
  sessionName: string;
  onChoose: (target: "current" | "new") => void;
  onCancel: () => void;
}) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-primary-dark/45 p-4 backdrop-blur-[2px]"
    >
      <div className="w-full max-w-sm animate-fade-in-up rounded-2xl border border-ink/10 bg-white px-6 py-5 shadow-pop">
        <div className="flex items-center gap-2">
          <FileSpreadsheet className="h-5 w-5 text-primary" aria-hidden="true" />
          <h3 className="text-sm font-semibold text-primary-dark">上传「{filename}」</h3>
        </div>
        <p className="mt-2 text-xs leading-relaxed text-ink-muted">
          会话「{sessionName}」已绑定数据，请选择这份数据的去向：
        </p>
        <div className="mt-4 flex flex-col gap-2">
          <button
            type="button"
            className="flex min-h-11 cursor-pointer items-start gap-2 rounded-xl border border-primary/40 px-3 py-2 text-left transition-colors duration-200 hover:bg-primary-soft"
            onClick={() => onChoose("current")}
          >
            <Layers className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
            <span className="text-xs font-medium text-primary-dark">
              加入当前工作区
              <span className="block text-[11px] font-normal text-ink-muted">
                作为新数据集标签添加到本会话
              </span>
            </span>
          </button>
          <button
            type="button"
            className="flex min-h-11 cursor-pointer items-start gap-2 rounded-xl border border-ink/15 px-3 py-2 text-left transition-colors duration-200 hover:bg-surface-page"
            onClick={() => onChoose("new")}
          >
            <Plus className="mt-0.5 h-4 w-4 shrink-0 text-ink-muted" aria-hidden="true" />
            <span className="text-xs font-medium text-primary-dark">
              新建会话
              <span className="block text-[11px] font-normal text-ink-muted">
                新开一个会话标签页绑定这份数据
              </span>
            </span>
          </button>
          <button
            type="button"
            className="ml-auto mt-1 flex min-h-11 cursor-pointer items-center gap-1 rounded-lg px-2 py-1 text-xs text-ink-muted transition-colors duration-200 hover:text-primary-dark"
            onClick={onCancel}
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
            取消
          </button>
        </div>
      </div>
    </div>
  );
}
