"""015/016 变量类型系统：推断、修改端点、口径与类型驱动映射。"""
import io

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from medsta.agents.discussion import PlanStep
from medsta.data.profiler import profile_dataframe
from medsta.stats.registry import execute_step, validate_step
from medsta.app import create_app


def _profile_types(df: pd.DataFrame) -> dict:
    return {name: col.type for name, col in profile_dataframe(df).columns.items()}


def test_type_inference_four_slots() -> None:
    """B1(015): 四类推断——等级/连续/类别/索引"""
    df = pd.DataFrame({
        "grade": [1, 2, 3, 2, 1, 3, 2, 1],
        "age": [25.5, 31.2, 42.8, 38.1, 51.0, 47.3, 29.9, 60.4],
        "city": ["北京", "上海", "北京", "广州", "上海", "北京", "广州", "上海"],
        "idx": [1, 2, 3, 4, 5, 6, 7, 8],
    })
    types = _profile_types(df)
    assert types["grade"] == "ordinal"
    assert types["age"] == "continuous"
    assert types["city"] == "categorical"
    assert types["idx"] == "index"


def test_patch_column_type_endpoint(tmp_path, monkeypatch) -> None:
    """B2(015): PATCH 修改列类型并重算统计；非法类型 400"""
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    sid = client.post("/sessions").json()["session_id"]
    csv = b"grade,value\n1,10\n2,20\n3,30\n"
    up = client.post(
        f"/sessions/{sid}/data",
        files={"file": ("d.csv", io.BytesIO(csv), "text/csv")},
    ).json()
    dsid = up["dataset_id"]
    assert up["profile"]["columns"]["grade"]["type"] == "ordinal"

    resp = client.patch(
        f"/sessions/{sid}/workspace/{dsid}/columns",
        json={"column": "grade", "type": "continuous"},
    )
    assert resp.status_code == 200
    assert resp.json()["profile"]["columns"]["grade"]["type"] == "continuous"
    assert resp.json()["profile"]["type_confirmed"] is True

    resp = client.patch(
        f"/sessions/{sid}/workspace/{dsid}/columns",
        json={"column": "grade", "type": "nonsense"},
    )
    assert resp.status_code == 400


def test_seven_key_stats_and_categorical_freq_table(tmp_path) -> None:
    """B3/B4(015): 七列统计口径 + 类别频数表"""
    df = pd.DataFrame({"score": [3.0, 4.0, 5.0, 6.0], "city": ["a", "b", "a", "b"]})
    step = PlanStep(
        title="描述", method="describe", target_columns=["score", "city"],
        chart_type="none", params={}, rationale="口径验证",
    )
    result, _ = execute_step(df, step, tmp_path, 0)
    score = result["stats"]["score"]
    for key in ("count", "mean", "median", "q25", "q75", "min", "max"):
        assert key in score
    table = result["table"]
    assert table["columns"] == ["column", "value", "count", "ratio"]
    a_row = next(row for row in table["rows"] if row["value"] == "a")
    assert a_row["count"] == 2 and a_row["ratio"] == 0.5
