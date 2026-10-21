"""表格数据解析：CSV / Excel -> DataFrame。"""
from __future__ import annotations

import pathlib

import pandas as pd

_SUPPORTED_SUFFIXES = {".csv", ".xlsx", ".xls"}


def load_table(path: str) -> pd.DataFrame:
    """按扩展名解析表格文件；不支持的扩展名抛出 ValueError。"""
    suffix = pathlib.Path(path).suffix.lower()
    if suffix not in _SUPPORTED_SUFFIXES:
        raise ValueError(
            f"不支持的文件类型：{suffix!r}，支持 {sorted(_SUPPORTED_SUFFIXES)}"
        )
    if suffix == ".csv":
        # utf-8-sig 兼容带 BOM 的导出文件（Excel 常见）：首列名不应残留 \ufeff
        return pd.read_csv(path, encoding="utf-8-sig")
    return pd.read_excel(path)
