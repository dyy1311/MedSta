import { Download, Maximize2, X } from "lucide-react";
import { useState } from "react";

interface Props {
  baseUrl: string; // 例如 /data/{sid}/{datasetId}/artifacts
  filename: string;
}

export default function ChartCard({ baseUrl, filename }: Props) {
  const [zoomed, setZoomed] = useState(false);
  const [failed, setFailed] = useState(false);
  const src = `${baseUrl}/${filename}`;

  return (
    <>
      <div className="group relative overflow-hidden rounded-2xl bg-surface-card shadow-card transition-shadow hover:shadow-hover">
        {failed ? (
          <div className="flex h-40 items-center justify-center text-xs text-ink-muted">
            图表生成中或不存在（后端重启后重新执行即可）
          </div>
        ) : (
          <img src={src} alt={filename} className="w-full object-contain" onError={() => setFailed(true)} />
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
            title="下载"
          >
            <Download className="h-4 w-4" />
          </a>
        </div>
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
              className="absolute -top-3 -right-3 cursor-pointer rounded-full bg-white p-2 text-ink shadow-card transition-transform hover:scale-105"
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
