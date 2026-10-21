import { useState } from "react";
import { CircleAlert, ChevronDown, ChevronUp, Lightbulb } from "lucide-react";
import type { AppErrorPayload } from "../types";

const CODE_LABELS: Record<string, string> = {
  MODEL_UNAVAILABLE: "模型未配置",
  MODEL_REQUEST_FAILED: "模型请求失败",
  DATA_REQUIRED: "缺少数据",
  INVALID_PLAN: "方案校验未通过",
  MISSING_PARAM: "缺少参数",
  INVALID_PARAM: "参数非法",
  COLUMN_NOT_FOUND: "列不存在",
  TOOL_NOT_FOUND: "方法不存在",
  INSUFFICIENT_DATA: "数据量不足",
  EXECUTION_FAILED: "执行失败",
  NO_ACTIVE_RUN: "没有进行中的任务",
  PROTOCOL_UNSUPPORTED: "协议不支持",
  UPLOAD_FAILED: "上传失败",
};

export default function ErrorCard({ code, message, hint, detail }: AppErrorPayload) {
  const [open, setOpen] = useState(false);
  return (
    <div className="animate-fade-in-up rounded-xl border border-danger/25 bg-danger/5 p-3">
      <div className="flex items-start gap-2">
        <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-danger" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded bg-danger/12 px-1.5 py-0.5 font-mono text-[11px] font-medium text-danger">
              {code}
            </span>
            <span className="text-xs text-ink-muted">
              {CODE_LABELS[code] ?? "请求失败"}
            </span>
          </div>
          <p className="mt-1 text-sm leading-relaxed text-ink">{message}</p>
          {hint && (
            <p className="mt-1 flex items-start gap-1 text-xs text-warn">
              <Lightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              {hint}
            </p>
          )}
          {detail != null && (
            <button
              onClick={() => setOpen((prev) => !prev)}
              className="mt-1.5 inline-flex cursor-pointer items-center gap-1 text-xs text-ink-muted hover:text-primary"
            >
              {open ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
              {open ? "收起详情" : "查看详情"}
            </button>
          )}
          {open && (
            <pre className="mt-1.5 max-h-40 overflow-auto rounded bg-primary-dark/95 p-2 text-[11px] leading-relaxed text-primary-cyan">
              {JSON.stringify(detail, null, 2)}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
