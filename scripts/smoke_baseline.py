"""1009 例基线数据全量冒烟（spec 024）。

手动运行，不入 CI：验证真实规模下的画像、统计描述、多组比较与卡方耗时和结果合理性。
    python scripts/smoke_baseline.py
"""
from __future__ import annotations

import pathlib
import time

import pandas as pd

from medsta.agents.discussion import PlanStep
from medsta.data.profiler import profile_dataframe
from medsta.stats.descriptive import descriptive_stats
from medsta.stats.methods import anova, chi_square

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "1.基线数据（1009例）.xlsx"


def _step(tool: str, targets: list[str], **params) -> PlanStep:
    return PlanStep(
        title=f"{tool} 冒烟",
        method=tool,
        target_columns=targets,
        chart_type="none",
        params=params,
        rationale="全量数据冒烟",
    )


def main() -> None:
    started = time.perf_counter()
    frame = pd.read_excel(SOURCE, sheet_name="Sheet1")
    profile = profile_dataframe(frame)
    print(f"read+profile: {time.perf_counter() - started:.2f}s rows={profile.row_count} cols={profile.column_count}")
    print("types:", {name: column.type for name, column in list(profile.columns.items())[:6]}, "...")

    started = time.perf_counter()
    describe_step = _step("descriptive_stats", ["年龄", "术前JOA评分"])
    summary = descriptive_stats(frame, describe_step, describe_step.params)
    print(f"\ndescriptive_stats: {time.perf_counter() - started:.3f}s")
    for name, entry in summary["columns"].items():
        print(f"  {name}: n={entry['n']} mean={entry['mean']} sd={entry['sd']} "
              f"median={entry['median']} IQR={entry['iqr']} 推荐={entry['recommended']}")

    started = time.perf_counter()
    anova_step = _step("anova", ["年龄"], group_column="手术方式")
    groups = anova(frame, anova_step, anova_step.params)
    print(f"\nanova by 手术方式: {time.perf_counter() - started:.3f}s "
          f"test={groups['test']} p={groups['p_value']:.4g} 事后={groups['pairwise']['method']}")
    print(f"  pairwise rows={len(groups['pairwise']['rows'])}")

    started = time.perf_counter()
    chi_step = _step("chi_square", ["性别", "是否有空洞"])
    table = chi_square(frame, chi_step, {**chi_step.params, "event_value": 1})
    print(f"\nchi_square 性别×是否有空洞: {time.perf_counter() - started:.3f}s "
          f"tier={table['tier']} chi2={table.get('chi2')} p={table['p_value']:.4g}")
    for row in table["group_rates"]:
        print(f"  组 {row['group']}: n={row['n']} 率={row['rate']:.3f} "
              f"95%CI=({row['ci_low']:.3f}, {row['ci_high']:.3f}) via {row['ci_method']}")

    print(f"\ntotal: {time.perf_counter() - started:.2f}s (last step)")


if __name__ == "__main__":
    main()
