import { Download, Maximize2, X } from "lucide-react";
import { useState } from "react";
import type { PlotStyle } from "../types";
import PlotStyleFields from "../components/PlotStyleFields";

interface Props {
  baseUrl: string; // 例如 /data/{sid}/{datasetId}/artifacts
  filename: string;
  /** 额外导出格式（033）：JPG/PDF/TIF 走导出端点按需重渲染 */
  extraFormats?: { label: string; href: string }[];
  caption?: string;
  cacheRev?: number;
  chartType?: string;
  plotStyle?: PlotStyle;
  onRestyle?: (style: PlotStyle) => void;
}

export default function ChartCard({
  baseUrl,
  filename,
  extraFormats = [],
  caption,
  cacheRev,
  chartType,
  plotStyle,
  onRestyle,
}: Props) {
  const [zoomed, setZoomed] = useState(false);
  const [failed, setFailed] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<PlotStyle>(plotStyle ?? {});
  const fileUrl = `${baseUrl}/${filename}`;
  const src = cacheRev
    ? `${fileUrl}${fileUrl.includes("?") ? "&" : "?"}rev=${cacheRev}`
    : fileUrl;

  return (
    <>
      <div className="group relative overflow-hidden rounded-2xl bg-surface-card shadow-card transition-shadow hover:shadow-hover">
        <div className="relative">
          {failed ? (
            <div className="flex h-40 items-center justify-center text-xs text-ink-muted">
              图表生成中或不存在（后端重启后重新执行即可）
            </div>
          ) : (
            <img src={src} alt={caption || filename} className="w-full object-contain" onError={() => setFailed(true)} />
          )}
          <div className="absolute inset-x-0 bottom-0 flex justify-end gap-1 bg-gradient-to-t from-primary-dark/70 to-transparent p-2 opacity-0 transition-opacity group-hover:opacity-100">
            <button
              onClick={() => setZoomed(true)}
              className="cursor-pointer rounded-lg bg-white/90 p-1.5 text-primary-dark transition-colors hover:bg-white"
              title="放大"
            >
              <Maximize2 className="h-4 w-4" />
            </button>
            <a
              href={src}
              download={filename}
              className="cursor-pointer rounded-lg bg-white/90 p-1.5 text-primary-dark transition-colors hover:bg-white"
              title="下载 PNG"
            >
              <Download className="h-4 w-4" />
            </a>
            {extraFormats.map((item) => (
              <a
                key={item.label}
                href={item.href}
                className="cursor-pointer rounded-lg bg-white/90 px-1.5 py-1 text-[10px] font-medium text-primary-dark transition-colors hover:bg-white"
                title={`下载 ${item.label}`}
              >
                {item.label}
              </a>
            ))}
          </div>
        </div>
        {(caption || (onRestyle && chartType && chartType !== "none")) && (
          <div className="flex items-start justify-between gap-2 px-3 py-1.5">
            {caption && (
              <p className="min-w-0 flex-1 break-words text-xs leading-relaxed text-ink">{caption}</p>
            )}
            {onRestyle && chartType && chartType !== "none" && (
              <button
                type="button"
                onClick={() => {
                  setDraft(plotStyle ?? {});
                  setEditing((prev) => !prev);
                }}
                className="shrink-0 cursor-pointer text-[11px] text-primary hover:underline"
              >
                {editing ? "收起标注" : "修改标注"}
              </button>
            )}
          </div>
        )}
        {editing && onRestyle && (
          <div className="space-y-2 border-t border-ink/8 p-3">
            <PlotStyleFields value={draft} onChange={setDraft} />
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setEditing(false)}
                className="min-h-11 cursor-pointer rounded-lg px-3 text-xs text-ink-muted"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => {
                  onRestyle(draft);
                  setEditing(false);
                }}
                className="min-h-11 cursor-pointer rounded-lg bg-primary px-3 text-xs font-medium text-white"
              >
                重新出图
              </button>
            </div>
          </div>
        )}
      </div>

      {zoomed && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-primary-dark/80 p-8 backdrop-blur-sm"
          onClick={() => setZoomed(false)}
        >
          <div className="relative max-h-full max-w-full">
            <img
              src={src}
              alt={filename}
              className="max-h-[85vh] rounded-xl bg-white object-contain shadow-2xl"
              onClick={(event) => event.stopPropagation()}
            />
            <button
              className="absolute -top-3 -right-3 cursor-pointer rounded-full bg-white p-2 text-ink shadow-card transition-colors duration-200 hover:text-primary"
              onClick={() => setZoomed(false)}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </>
  );
}
