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
