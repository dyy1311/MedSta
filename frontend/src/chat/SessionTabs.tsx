import { MessageSquarePlus } from "lucide-react";

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
}

export default function SessionTabs({ sessions, activeId, onSelect, onCreate }: Props) {
  return (
    <div className="flex items-center gap-1 overflow-x-auto border-b border-ink/8 bg-surface-card px-3 py-2">
      {sessions.map((session, index) => {
        const isActive = session.sessionId === activeId;
        return (
          <button
            key={session.sessionId}
            onClick={() => onSelect(session.sessionId)}
            className={`shrink-0 cursor-pointer rounded-lg px-3 py-1.5 text-xs font-medium transition-all duration-200 ${
              isActive
                ? "bg-primary/10 text-primary shadow-[inset_0_-2px_0_0_#3B5BDB]"
                : "text-ink-muted hover:bg-surface-page hover:text-ink"
            }`}
            title={`会话 ${index + 1} · 绑定表格：${session.name}`}
          >
            会话 {index + 1}
            <span className="ml-1 text-[10px] text-ink-muted">· {session.name}</span>
          </button>
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
    </div>
  );
}
