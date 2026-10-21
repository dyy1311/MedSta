import { useCallback, useRef, useState } from "react";
import { CloudUpload, FileSpreadsheet } from "lucide-react";

interface Props {
  uploaded: boolean;
  onUpload: (file: File) => void;
}

export default function UploadZone({ uploaded, onUpload }: Props) {
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    async (file: File | undefined) => {
      if (!file) return;
      setBusy(true);
      setFileName(file.name);
      try {
        await onUpload(file);
      } finally {
        setBusy(false);
      }
    },
    [onUpload]
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        void handleFile(e.dataTransfer.files?.[0]);
      }}
      className={`rounded-xl border-2 border-dashed p-5 text-center transition-all duration-200 ${
        dragging
          ? "border-primary bg-primary/5 scale-[1.01]"
          : "border-ink/15 hover:border-primary/50"
      } ${uploaded ? "opacity-90" : ""}`}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.xlsx,.xls"
        className="hidden"
        onChange={(e) => void handleFile(e.target.files?.[0])}
      />
      {uploaded ? (
        <div className="flex items-center justify-center gap-2 text-sm text-ink">
          <FileSpreadsheet className="h-4 w-4 text-primary-cyan" />
          <span className="font-medium">{fileName ?? "已上传数据"}</span>
          <button
            className="cursor-pointer text-xs text-primary hover:underline"
            onClick={() => inputRef.current?.click()}
          >
            更换
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={busy}
          className="flex w-full cursor-pointer flex-col items-center gap-2 disabled:cursor-wait"
        >
          <CloudUpload
            className={`h-8 w-8 ${dragging ? "text-primary" : "text-ink-muted"}`}
          />
          <span className="text-sm font-medium text-ink">
            {busy ? "正在解析数据…" : "拖拽 CSV / Excel 到此处，或点击上传"}
          </span>
          <span className="text-xs text-ink-muted">
            上传后自动生成数据画像，开始与智能体讨论分析方案
          </span>
        </button>
      )}
    </div>
  );
}
