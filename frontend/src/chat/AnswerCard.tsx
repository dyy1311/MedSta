import { MessagesSquare, TriangleAlert } from "lucide-react";

interface Props {
  content: string;
  caveats: string[];
  unverified: string[];
}

export default function AnswerCard({ content, caveats, unverified }: Props) {
  return (
    <div className="animate-fade-in-up rounded-xl border-l-2 border-primary-cyan bg-surface-card px-3 py-2.5 shadow-card">
      <div className="mb-1 flex items-center gap-1.5 text-[11px] text-primary-cyan">
        <MessagesSquare className="h-3.5 w-3.5" />
        答疑
      </div>
      <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink">{content}</p>
      {caveats.length > 0 && (
        <ul className="mt-2 space-y-1 border-t border-ink/8 pt-2 text-[11px] leading-relaxed text-ink-muted">
          {caveats.map((item, index) => (
            <li key={index}>· {item}</li>
          ))}
        </ul>
      )}
      {unverified.length > 0 && (
        <p className="mt-1.5 text-[11px] leading-relaxed text-warn">
          <TriangleAlert className="mr-1 inline h-3 w-3" />
          含未核验数值：{unverified.join("、")}
        </p>
      )}
    </div>
  );
}
