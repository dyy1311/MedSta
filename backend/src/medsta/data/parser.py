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
        try:
            return pd.read_csv(path, encoding="utf-8-sig")
        except UnicodeDecodeError:
            # 中文医学数据常见 GBK 导出：utf-8 失败后回退 gb18030（GBK 超集）
            return pd.read_csv(path, encoding="gb18030")
    if suffix == ".xls":
        # pandas 的 .xls 引擎是 xlrd（openpyxl 只支持 .xlsx）：缺包时给可执行指引，
        # 而不是抛出 ImportError 让上传变成不可解释的 400
        try:
            import xlrd  # noqa: F401
        except ImportError as exc:
            raise ValueError(
                "旧版 .xls 需要 xlrd 依赖才能解析（当前环境未安装）："
                "请安装 xlrd，或用 Excel 将文件另存为 .xlsx 后重新上传"
            ) from exc
    return pd.read_excel(path)
