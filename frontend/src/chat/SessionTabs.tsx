import { Brush, MessageSquarePlus, X } from "lucide-react";

export interface ChatSessionEntry {
  sessionId: string;
  datasetId: string | null;
  name: string; // 绑定的表格名（未绑定时为"未绑定"）
}

interface Props {
  sessions: ChatSessionEntry[];
  activeId: string | null;
  onSelect: (sessionId: string) => void;
  onCreate: () => void;
  /** 批次12 会话删除：传入时每个标签显示「×」删除按钮 */
  onDelete?: (sessionId: string) => void;
  /** 批次13 批量清理重复会话：传入时显示「清理重复」按钮 */
  onCleanupDuplicates?: () => void;
}

export default function SessionTabs({
  sessions,
  activeId,
  onSelect,
  onCreate,
  onDelete,
  onCleanupDuplicates,
}: Props) {
  return (
    <div className="flex shrink-0 items-center gap-1 overflow-x-auto border-b border-ink/8 bg-surface-card px-3 py-2">
      {sessions.map((session, index) => {
        const isActive = session.sessionId === activeId;
        return (
          <div key={session.sessionId} className="flex shrink-0 items-center">
            <button
              onClick={() => onSelect(session.sessionId)}
              className={`min-h-11 cursor-pointer rounded-lg border-b-2 px-3 py-1.5 text-xs font-medium transition-colors duration-200 ${
                isActive
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-transparent text-ink-muted hover:bg-surface-page hover:text-ink"
              }`}
              title={`会话 ${index + 1} · 绑定表格：${session.name}`}
            >
              会话 {index + 1}
              <span className="ml-1 text-[10px] text-ink-muted">· {session.name}</span>
            </button>
            {onDelete && (
              <button
                onClick={() => onDelete(session.sessionId)}
                title="删除会话"
                aria-label={`删除会话 ${index + 1}`}
                className="-ml-1 h-4 w-4 cursor-pointer rounded text-ink-muted/50 transition-colors hover:text-red-500"
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </div>
        );
      })}
      <button
        onClick={onCreate}
        title="新建会话空间"
        className="inline-flex shrink-0 cursor-pointer items-center gap-1 rounded-lg border border-dashed border-ink/20 px-2.5 py-1.5 text-xs text-ink-muted transition-colors hover:border-primary hover:text-primary"
      >
        <MessageSquarePlus className="h-3.5 w-3.5" />
        新会话
      </button>
      {onCleanupDuplicates && (
        <button
          onClick={onCleanupDuplicates}
          title="清理重复会话"
          className="inline-flex shrink-0 cursor-pointer items-center gap-1 rounded-lg border border-dashed border-ink/20 px-2.5 py-1.5 text-xs text-ink-muted transition-colors hover:border-primary hover:text-primary"
        >
          <Brush className="h-3.5 w-3.5" />
          清理重复
        </button>
      )}
    </div>
  );
}
