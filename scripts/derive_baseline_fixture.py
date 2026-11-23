"""从 1009 例基线数据派生固定测试子集（spec 024）。

只在需要更新夹具时手动运行；CI 直接读取已生成的 CSV，不依赖 docs/ 与 Excel。
分层抽样：按「手术方式」每组取前 N 例，保证多组比较（含 n 较小的 3/4 组）可测试。
"""
from __future__ import annotations

import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "1.基线数据（1009例）.xlsx"
TARGET = ROOT / "backend" / "tests" / "fixtures" / "baseline_sample.csv"
PER_GROUP = 12


def main() -> None:
    frame = pd.read_excel(SOURCE, sheet_name="Sheet1")
    sampled = (
        frame.sort_values("序号")
        .groupby("手术方式", sort=True, group_keys=False)
        .head(PER_GROUP)
    )
    target = TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    sampled.to_csv(target, index=False, encoding="utf-8-sig")
    print(f"written {target} rows={len(sampled)} groups={sampled['手术方式'].nunique()}")
    print(sampled["手术方式"].value_counts().sort_index().to_string())


if __name__ == "__main__":
    main()
