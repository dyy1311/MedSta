"""002 数据解析：load_table 公共接口测试。"""
import pandas as pd
import pytest

from medsta.data.parser import load_table


def _sample_records() -> dict:
    return {
        "age": [25.0, None, 31.0, 42.0],
        "city": ["Beijing", "Shanghai", "Beijing", "Shenzhen"],
        "income": [5000.5, 6200.0, None, 4800.0],
    }


def test_load_csv(tmp_path) -> None:
    """B1: 解析 UTF-8 CSV（数值列、类别列、缺失单元格），行数正确"""
    path = tmp_path / "sample.csv"
    path.write_text(
        "age,city,income\n"
        "25,Beijing,5000.5\n"
        ",Shanghai,6200.0\n"
        "31,Beijing,\n"
        "42,Shenzhen,4800.0\n",
        encoding="utf-8",
    )
    df = load_table(str(path))
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 4
    assert list(df.columns) == ["age", "city", "income"]


def test_load_xlsx(tmp_path) -> None:
    """B5: 解析 xlsx 得到与 CSV 等价的数据"""
    path = tmp_path / "sample.xlsx"
    pd.DataFrame(_sample_records()).to_excel(path, index=False)
    df = load_table(str(path))
    assert len(df) == 4
    assert list(df.columns) == ["age", "city", "income"]


def test_unsupported_extension(tmp_path) -> None:
    """B6: 不支持的扩展名抛出带说明的 ValueError"""
    path = tmp_path / "sample.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="不支持"):
        load_table(str(path))


def test_load_legacy_xls_with_xlrd() -> None:
    """终审修复: .xls（xlrd 引擎）真的能解析——此前 pyproject 漏 xlrd，上传必失败。"""
    import pathlib

    fixture = pathlib.Path(__file__).parent / "fixtures" / "legacy.xls"
    df = load_table(str(fixture))

    assert list(df.columns) == ["group", "value"]
    assert df["value"].tolist() == [1.5, 2.5, 4.5, 5.5]


def test_legacy_xls_missing_xlrd_gives_actionable_error(tmp_path, monkeypatch) -> None:
    """终审修复: .xls 依赖 xlrd（openpyxl 只支持 .xlsx）——缺包时给可执行指引。"""
    import sys

    path = tmp_path / "legacy.xls"
    path.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")  # OLE2 magic（内容不解析）
    monkeypatch.setitem(sys.modules, "xlrd", None)

    with pytest.raises(ValueError, match="xlrd"):
        load_table(str(path))


def test_gbk_csv_falls_back_to_gb18030(tmp_path) -> None:
    """P1: 中文医学数据常见 GBK 导出——utf-8 解码失败后回退 gb18030。"""
    path = tmp_path / "gbk.csv"
    path.write_bytes("分组,年龄\n甲组,25\n乙组,31\n".encode("gbk"))

    df = load_table(str(path))

    assert list(df.columns) == ["分组", "年龄"]
    assert df["年龄"].tolist() == [25, 31]
