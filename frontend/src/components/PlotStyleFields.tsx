import type { PlotStyle } from "../types";

/** 出图标注：标题与坐标轴可选填，留空则用数据列名/默认刻度。 */
export default function PlotStyleFields({
  value,
  onChange,
}: {
  value: PlotStyle;
  onChange: (next: PlotStyle) => void;
}) {
  const patch = (key: keyof PlotStyle, text: string) =>
    onChange({ ...value, [key]: text });

  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      <label className="block min-w-0 text-[11px] text-ink-muted">
        图标题
        <input
          value={value.title ?? ""}
          onChange={(event) => patch("title", event.target.value)}
          placeholder="留空则用步骤名"
          className="mt-0.5 min-h-11 w-full rounded-md border border-ink/15 bg-white px-2 text-xs text-ink"
        />
      </label>
      <label className="block min-w-0 text-[11px] text-ink-muted">
        X 轴标题
        <input
          value={value.xlabel ?? ""}
          onChange={(event) => patch("xlabel", event.target.value)}
          placeholder="留空则用列名"
          className="mt-0.5 min-h-11 w-full rounded-md border border-ink/15 bg-white px-2 text-xs text-ink"
        />
      </label>
      <label className="block min-w-0 text-[11px] text-ink-muted">
        Y 轴标题
        <input
          value={value.ylabel ?? ""}
          onChange={(event) => patch("ylabel", event.target.value)}
          placeholder="留空则用列名"
          className="mt-0.5 min-h-11 w-full rounded-md border border-ink/15 bg-white px-2 text-xs text-ink"
        />
      </label>
      <label className="block min-w-0 text-[11px] text-ink-muted">
        X 轴刻度
        <input
          value={value.xticks ?? ""}
          onChange={(event) => patch("xticks", event.target.value)}
          placeholder="逗号分隔，如 0,10,20 或 低,中,高"
          className="mt-0.5 min-h-11 w-full rounded-md border border-ink/15 bg-white px-2 text-xs text-ink"
        />
      </label>
      <label className="block min-w-0 text-[11px] text-ink-muted">
        Y 轴刻度
        <input
          value={value.yticks ?? ""}
          onChange={(event) => patch("yticks", event.target.value)}
          placeholder="逗号分隔，如 0,50,100"
          className="mt-0.5 min-h-11 w-full rounded-md border border-ink/15 bg-white px-2 text-xs text-ink"
        />
      </label>
      <label className="block min-w-0 text-[11px] text-ink-muted sm:col-span-2">
        组名
        <input
          value={value.groups ?? ""}
          onChange={(event) => patch("groups", event.target.value)}
          placeholder="原名=新名，如 0=对照组,1=试验组；或按顺序 对照组,试验组"
          className="mt-0.5 min-h-11 w-full rounded-md border border-ink/15 bg-white px-2 text-xs text-ink"
        />
      </label>
      <label className="block min-w-0 text-[11px] text-ink-muted sm:col-span-2">
        组顺序
        <input
          value={value.group_order ?? ""}
          onChange={(event) => patch("group_order", event.target.value)}
          placeholder="从左到右，如 1,0 或 试验组,对照组"
          className="mt-0.5 min-h-11 w-full rounded-md border border-ink/15 bg-white px-2 text-xs text-ink"
        />
      </label>
    </div>
  );
}
