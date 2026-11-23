"""045 数据清洗层：去重 / 筛选 / 标准化 / 分箱 / 异常值识别 / 截尾。

行为编号对齐 spec/implementing/045-data-cleaning.md；出口 JSON 严格性由
test_json_contract 的采样硬门覆盖（清洗结果只产标准类型）。
"""
from __future__ import annotations

import pathlib

import pandas as pd
import pytest

from medsta.agents.discussion import AnalysisPlan, PlanStep
from medsta.session.manager import manager
from medsta.stats.cleaning import (
    bin_column,
    dedupe,
    filter_rows,
    outlier_report,
    standardize,
    winsorize,
)
from medsta.stats.registry import get_tool, validate_step


def _step(method: str, targets: list[str], **params) -> PlanStep:
    return PlanStep(
        title=method,
        method=method,
        target_columns=targets,
        chart_type="none",
        params=params,
        rationale="测试依据：清洗工具确定性验证",
    )


def _dup_df() -> pd.DataFrame:
    return pd.DataFrame({"group": ["A", "A", "A", "B"], "value": [1.0, 1.0, 2.0, 3.0]})


def test_dedupe_removes_duplicates_and_writes_dataset(tmp_path) -> None:
    """B1: 整行去重 keep=first；写出 cleaned_step_0.csv 并挂 cleaned_dataset/_next_frame。"""
    result = dedupe(
        _dup_df(),
        _step("dedupe", []),
        {"_artifact_dir": str(tmp_path), "_step_index": 0},
    )
    row = result["table"]["rows"][0]
    assert row["n_before"] == 4 and row["n_after"] == 3 and row["duplicates"] == 1
    assert row["keep"] == "first" and row["subset"] == "（整行）"

    path = pathlib.Path(result["cleaned_dataset"]["path"])
    assert path.name == "cleaned_step_0.csv"
    loaded = pd.read_csv(path)
    assert len(loaded) == 3

    frame = result["_next_frame"]
    assert len(frame) == 3
    assert list(frame["group"]) == ["A", "A", "B"]
    assert list(frame["value"]) == [1.0, 2.0, 3.0]


def test_dedupe_keep_last_and_subset_columns(tmp_path) -> None:
    """B2: keep=last 保留最后一次出现；columns 指定判重子集列。"""
    df = pd.DataFrame(
        {"id": [1, 1, 2, 2], "visit": [1, 2, 1, 2], "value": [10.0, 20.0, 30.0, 40.0]}
    )
    result = dedupe(
        df,
        _step("dedupe", []),
        {"columns": ["id"], "keep": "last"},
    )
    row = result["table"]["rows"][0]
    assert row["duplicates"] == 2 and row["n_after"] == 2
    assert row["subset"] == "id"
    frame = result["_next_frame"]
    assert list(frame["visit"]) == [2, 2]
    assert list(frame["value"]) == [20.0, 40.0]


def test_dedupe_no_duplicates_writes_nothing(tmp_path) -> None:
    """B3: 无重复行时不落盘、不产 _next_frame（no_change=true）。"""
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0]})
    result = dedupe(df, _step("dedupe", []), {"_artifact_dir": str(tmp_path)})
    row = result["table"]["rows"][0]
    assert row["duplicates"] == 0 and row["n_after"] == 3
    assert result["no_change"] is True
    assert "cleaned_dataset" not in result
    assert "_next_frame" not in result
    assert not list(tmp_path.glob("cleaned_*.csv"))


def test_dedupe_rejects_unknown_columns_and_keep() -> None:
    """B6 族：判重列不存在 / keep 非法 → ValueError。"""
    with pytest.raises(ValueError, match="不存在的列"):
        dedupe(_dup_df(), _step("dedupe", []), {"columns": ["nope"]})
    with pytest.raises(ValueError, match="keep"):
        dedupe(_dup_df(), _step("dedupe", []), {"keep": "middle"})


# ---- filter_rows（B4–B6）----


def test_filter_rows_conditions(tmp_path) -> None:
    """B4: 多条件 AND（ge + between）；产出清洗数据集与 _next_frame。"""
    df = pd.DataFrame({"age": [20.0, 22.0, 25.0, 30.0, 41.0]})
    result = filter_rows(
        df,
        _step("filter_rows", []),
        {
            "conditions": [
                {"column": "age", "op": "ge", "value": 22},
                {"column": "age", "op": "between", "value": [22, 40]},
            ],
            "_artifact_dir": str(tmp_path),
            "_step_index": 1,
        },
    )
    row = result["table"]["rows"][0]
    assert row["n_before"] == 5 and row["n_kept"] == 3 and row["n_dropped"] == 2
    frame = result["_next_frame"]
    assert list(frame["age"]) == [22.0, 25.0, 30.0]
    assert pathlib.Path(result["cleaned_dataset"]["path"]).name == "cleaned_step_1.csv"


def test_filter_rows_ops_and_guards() -> None:
    """B5/B6: eq/in/isna；筛后 0 行拒绝；未知列与操作符拒绝。"""
    df = pd.DataFrame({"g": ["A", "B", "A", None], "v": [1.0, 2.0, 3.0, 4.0]})
    kept = filter_rows(
        df,
        _step("filter_rows", []),
        {
            "conditions": [
                {"column": "g", "op": "eq", "value": "A"},
                {"column": "v", "op": "in", "value": [1.0, 3.0]},
            ]
        },
    )
    assert list(kept["_next_frame"]["v"]) == [1.0, 3.0]

    na = filter_rows(
        df, _step("filter_rows", []), {"conditions": [{"column": "g", "op": "isna"}]}
    )
    assert len(na["_next_frame"]) == 1

    with pytest.raises(ValueError, match="0 行"):
        filter_rows(
            df,
            _step("filter_rows", []),
            {"conditions": [{"column": "v", "op": "gt", "value": 99.0}]},
        )
    with pytest.raises(ValueError, match="不存在的列"):
        filter_rows(
            df,
            _step("filter_rows", []),
            {"conditions": [{"column": "nope", "op": "eq", "value": 1}]},
        )
    with pytest.raises(ValueError, match="操作符"):
        filter_rows(
            df,
            _step("filter_rows", []),
            {"conditions": [{"column": "v", "op": "like", "value": 1}]},
        )


# ---- standardize（B7–B9）----


def test_standardize_zscore(tmp_path) -> None:
    """B7: z-score 后 mean≈0、sd≈1；产出清洗数据集。"""
    df = pd.DataFrame({"value": [1.0, 2.0, 3.0, 4.0, 100.0], "g": list("AABBA")})
    result = standardize(
        df, _step("standardize", ["value"]), {"_artifact_dir": str(tmp_path)}
    )
    frame = result["_next_frame"]
    assert frame["value"].mean() == pytest.approx(0.0, abs=1e-9)
    assert frame["value"].std(ddof=1) == pytest.approx(1.0, abs=1e-9)
    row = result["table"]["rows"][0]
    assert row["column"] == "value" and row["method"] == "zscore"
    assert "cleaned_dataset" in result


def test_standardize_minmax_and_guards() -> None:
    """B8/B9: minmax 映射到 [0,1]；sd=0 与非数值拒绝。"""
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [5.0, 5.0, 5.0], "c": list("xyz")})
    result = standardize(df, _step("standardize", ["a"]), {"method": "minmax"})
    assert list(result["_next_frame"]["a"]) == [0.0, 0.5, 1.0]
    with pytest.raises(ValueError, match="标准差为 0"):
        standardize(df, _step("standardize", ["b"]), {})
    with pytest.raises(ValueError, match="非数值"):
        standardize(df, _step("standardize", ["c"]), {})


# ---- bin_column（B10–B12）----


def test_bin_column_quantile(tmp_path) -> None:
    """B10: 等频分箱默认 4 箱，输出 {col}_bin 箱号 1..k。"""
    df = pd.DataFrame({"x": [float(i) for i in range(1, 9)]})
    result = bin_column(
        df, _step("bin_column", ["x"]), {"_artifact_dir": str(tmp_path)}
    )
    frame = result["_next_frame"]
    assert "x_bin" in frame.columns
    assert sorted(frame["x_bin"].dropna().unique()) == [1.0, 2.0, 3.0, 4.0]
    row = result["table"]["rows"][0]
    assert row["method"] == "quantile" and row["bins_actual"] == 4


def test_bin_column_equal_width_and_output_name() -> None:
    """B11/B12: 等宽分箱；单列 output_column 生效；bins<2 拒绝。"""
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0, 10.0]})
    result = bin_column(
        df,
        _step("bin_column", ["x"]),
        {"method": "equal_width", "bins": 3, "output_column": "等级"},
    )
    assert "等级" in result["_next_frame"].columns
    row = result["table"]["rows"][0]
    assert row["method"] == "equal_width" and row["bins_actual"] == 3
    with pytest.raises(ValueError, match="至少为 2"):
        bin_column(df, _step("bin_column", ["x"]), {"bins": 1})


# ---- outlier_report（B13–B15）----


def test_outlier_report_iqr_and_zscore() -> None:
    """B13/B14/B15: IQR 界外计数、z-score 3σ；报告型不产数据集。"""
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 100.0]})
    iqr = outlier_report(df, _step("outlier_report", ["x"]), {})
    row = iqr["table"]["rows"][0]
    assert row["method"] == "iqr" and row["lower"] < 1.0
    assert row["outliers"] == 1 and row["percent"] == pytest.approx(20.0)

    wide = pd.DataFrame({"x": [float(i) for i in range(20)] + [50.0]})
    zs = outlier_report(wide, _step("outlier_report", ["x"]), {"method": "zscore"})
    zs_row = zs["table"]["rows"][0]
    assert zs_row["method"] == "zscore" and zs_row["outliers"] == 1

    assert "cleaned_dataset" not in iqr and "_next_frame" not in iqr


# ---- winsorize（B16）----


def test_winsorize_caps_to_bounds(tmp_path) -> None:
    """B16: 截尾到界内；产出数据集；table 计数上下侧。"""
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 100.0]})
    result = winsorize(
        df, _step("winsorize", ["x"]), {"_artifact_dir": str(tmp_path)}
    )
    frame = result["_next_frame"]
    row = result["table"]["rows"][0]
    assert float(frame["x"].max()) == pytest.approx(row["upper"])
    assert row["n_capped_upper"] == 1 and row["n_capped_lower"] == 0
    assert "cleaned_dataset" in result


# ---- 注册与契约（B17/B18/B19）----


def test_registry_accepts_cleaning_tools(sample_df) -> None:
    """B17: 六工具入注册表；dedupe/filter_rows 允许空 target_columns；
    filter_rows 缺 conditions 被 MISSING_PARAM 硬拦。"""
    names = (
        "dedupe", "filter_rows", "standardize",
        "bin_column", "outlier_report", "winsorize",
    )
    for name in names:
        assert get_tool(name) is not None, name

    dedupe_step = PlanStep(
        title="去重", method="dedupe", target_columns=[],
        chart_type="none", params={}, rationale="清洗前置",
    )
    assert validate_step(dedupe_step, sample_df) == []

    standardize_step = PlanStep(
        title="标准化", method="standardize", target_columns=["value"],
        chart_type="none", params={}, rationale="统一量纲",
    )
    assert validate_step(standardize_step, sample_df) == []

    filter_step = PlanStep(
        title="筛选", method="filter_rows", target_columns=[],
        chart_type="none", params={}, rationale="取子集",
    )
    codes = {issue.code for issue in validate_step(filter_step, sample_df)}
    assert "MISSING_PARAM" in codes


def test_chaining_dedupe_then_describe(tmp_path) -> None:
    """B19: dedupe → describe 链间管道生效：describe 统计的是去重后的数据。"""
    from medsta.pipeline.executor import PipelineExecutor

    df = pd.DataFrame({"value": [1.0, 1.0, 2.0, 3.0], "group": ["A", "A", "B", "B"]})
    plan = AnalysisPlan(
        message="清洗链",
        steps=[
            PlanStep(
                title="去重", method="dedupe", target_columns=[],
                chart_type="none", params={}, rationale="先去重",
            ),
            PlanStep(
                title="描述", method="describe", target_columns=["value"],
                chart_type="none", params={}, rationale="描述去重结果",
            ),
        ],
    )
    report = PipelineExecutor().execute(df, plan, tmp_path / "artifacts")
    stats = report.steps[1].result["stats"]["value"]
    assert stats["count"] == 3


CSV_DUP = b"group,value,age\nA,1.0,20\nA,1.0,20\nB,2.0,41\nB,3.0,42\n"


def test_cleaned_dataset_registered_flow(client, app, session_id) -> None:
    """B19: WS 执行去重方案后 dataset_added（imputed=False）注册清洗数据集，不切换 active。"""
    from tests.helpers import collect_until, drive_to_review, fake_agent, upload_csv

    plan_payload = {
        "message": "先去重再分析",
        "steps": [
            {
                "title": "去重", "method": "dedupe", "target_columns": [],
                "chart_type": "none", "params": {},
                "rationale": "数据含重复行，先去重",
            }
        ],
        "options": [{"id": "go", "label": "按此执行", "action": "confirm"}],
    }
    app.state.service.set_agent(fake_agent(plan_payload))
    upload_csv(client, session_id, content=CSV_DUP)
    original = manager.get(session_id).active_dataset_id

    with client.websocket_connect(f"/ws/{session_id}") as ws:
        drive_to_review(ws)
        _, added = collect_until(ws, {"dataset_added"})

    assert added["imputed"] is False
    assert added["dataset_id"] != original
    assert manager.get(session_id).active_dataset_id == original
    session = manager.get(session_id)
    assert len(session.datasets) == 2
