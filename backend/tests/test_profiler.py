"""002 数据画像：profile_dataframe 公共接口测试。"""
import pandas as pd

from medsta.data.profiler import profile_dataframe


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "age": [25.0, None, 31.0, 42.0],
            "city": ["Beijing", "Shanghai", "Beijing", "Shenzhen"],
            "income": [5000.5, 6200.0, None, 4800.0],
        }
    )


def test_numeric_column_profile() -> None:
    """B2: 数值列画像含 count/mean/std/min/50%/max 与缺失数"""
    profile = profile_dataframe(_sample_df())
    age = profile.columns["age"]
    assert age.type == "continuous"
    assert age.missing == 1
    stats = age.stats
    assert stats["count"] == 3
    assert abs(stats["mean"] - (25.0 + 31.0 + 42.0) / 3) < 0.001
    assert abs(stats["min"] - 25.0) < 1e-9
    assert abs(stats["max"] - 42.0) < 1e-9
    assert "median" in stats


def test_categorical_column_profile() -> None:
    """B3: 类别列画像含 distinct 计数与最高频类别"""
    profile = profile_dataframe(_sample_df())
    city = profile.columns["city"]
    assert city.type == "categorical"
    assert city.missing == 0
    assert city.stats["distinct"] == 3
    assert city.stats["top"] == "Beijing"


def test_table_profile_summary_and_json() -> None:
    """B4: 画像汇总含 row_count/column_count，且整体可 JSON 序列化"""
    profile = profile_dataframe(_sample_df())
    assert profile.row_count == 4
    assert profile.column_count == 3
    assert set(profile.columns) == {"age", "city", "income"}
    payload = profile.model_dump_json()
    assert isinstance(payload, str)
    assert '"row_count":4' in payload.replace(" ", "")
