"""028 B5–B13：MICE 插补、敏感性方法与 delta 扫描、CSV 落盘。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from medsta.agents.discussion import PlanStep
from medsta.stats.impute import impute


def _step(targets: list[str], **params) -> PlanStep:
    return PlanStep(
        title="缺失插补",
        method="impute",
        target_columns=targets,
        chart_type="none",
        params=params,
        rationale="缺失处理",
    )


def _frame_with_missing(
    seed: int = 5, n: int = 120
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    x = rng.normal(0, 1, n)
    y = 2.0 * x + rng.normal(0, 0.3, n)
    frame = pd.DataFrame({"x": x, "y": y})
    mask = rng.random(n) < 0.2
    frame.loc[mask, "y"] = np.nan
    return frame, mask, y


def test_mice_fills_missing_preserving_shape(tmp_path) -> None:
    """B5: 默认 MICE、m=20，插补后目标列无缺失且行列数不变。"""
    frame, _, _ = _frame_with_missing()
    step = _step(["x", "y"], _artifact_dir=str(tmp_path))

    result = impute(frame, step, step.params)

    assert result["method"] == "mice"
    assert result["m"] == 20
    assert result["imputed_dataset"] is not None
    imputed = pd.read_csv(result["imputed_dataset"]["path"])
    assert imputed.shape == frame.shape
    assert imputed[["x", "y"]].isna().sum().sum() == 0
    # 未缺失的列不被改动
    assert imputed["x"].to_numpy() == pytest.approx(frame["x"].to_numpy())


def test_mice_recovers_linear_structure(tmp_path) -> None:
    """B6: y=2x+ε 置空 20% 后，插补值与真实值相关 >0.8。"""
    frame, mask, truth = _frame_with_missing()
    step = _step(["x", "y"], _artifact_dir=str(tmp_path))

    result = impute(frame, step, step.params)
    imputed = pd.read_csv(result["imputed_dataset"]["path"])

    correlation = np.corrcoef(imputed.loc[mask, "y"], truth[mask])[0, 1]
    assert correlation > 0.8


def test_between_imputation_variance(tmp_path) -> None:
    """B7: 无缺失时为 0，有缺失时 >0。"""
    complete = pd.DataFrame({"x": np.arange(1.0, 31.0), "y": np.arange(2.0, 61.0, 2.0)})
    complete_result = impute(
        complete, _step(["x", "y"], _artifact_dir=str(tmp_path)), {"_artifact_dir": str(tmp_path)}
    )
    assert complete_result["between_imputation_variance"] == 0.0

    frame, _, _ = _frame_with_missing()
    step = _step(["x", "y"], _artifact_dir=str(tmp_path))
    missing_result = impute(frame, step, step.params)
    assert missing_result["between_imputation_variance"] > 0


def test_m_count_boundaries(tmp_path) -> None:
    """B8: m<20 给警告仍执行；m>50 截断到 50。"""
    frame, _, _ = _frame_with_missing()
    step_low = _step(["x", "y"], m=5, _artifact_dir=str(tmp_path))
    low = impute(frame, step_low, step_low.params)
    assert low["m"] == 5
    assert any("20" in item for item in low["warnings"])

    step_high = _step(["x", "y"], m=100, _artifact_dir=str(tmp_path))
    high = impute(frame, step_high, step_high.params)
    assert high["m"] == 50
    assert any("50" in item for item in high["warnings"])


def test_rejects_column_with_excessive_missing(tmp_path) -> None:
    """B9: 单列缺失 >50% 时拒绝并给可读错误。"""
    frame = pd.DataFrame(
        {"keep": np.arange(20.0), "sparse": [np.nan] * 15 + [1.0, 2.0, 3.0, 4.0, 5.0]}
    )
    step = _step(["keep", "sparse"], _artifact_dir=str(tmp_path))

    with pytest.raises(ValueError) as excinfo:
        impute(frame, step, step.params)

    assert "sparse" in str(excinfo.value)
    assert "50%" in str(excinfo.value)


@pytest.mark.parametrize("method", ["median", "mean", "locf"])
def test_sensitivity_methods_do_not_emit_dataset(method: str, tmp_path) -> None:
    """B10: median/mean/locf 标记 sensitivity_only 且不产出数据集。"""
    frame, _, _ = _frame_with_missing()
    step = _step(["x", "y"], method=method, _artifact_dir=str(tmp_path))

    result = impute(frame, step, step.params)

    assert result["sensitivity_only"] is True
    assert result["imputed_dataset"] is None
    assert result["missing_after"]["y"] == 0
    assert any("敏感性" in item for item in result["warnings"])


def test_delta_scan_linear_shift(tmp_path) -> None:
    """B11: delta 扫描输出三行，均值按缺失比例线性偏移。"""
    frame = pd.DataFrame({"y": [1.0, 2.0, np.nan, 4.0, np.nan, 6.0]})
    step = _step(["y"], delta=0.5, _artifact_dir=str(tmp_path))

    result = impute(frame, step, step.params)

    rows = result["delta_scan"]["rows"]
    assert [row["delta"] for row in rows] == [-0.5, 0.0, 0.5]
    by_delta = {row["delta"]: row["mean"] for row in rows}
    missing_count = 2
    expected_shift = 0.5 * missing_count / len(frame)
    # 输出均值保留 6 位小数，容差按该精度设定
    assert by_delta[0.5] - by_delta[0.0] == pytest.approx(expected_shift, abs=1e-5)
    assert by_delta[-0.5] - by_delta[0.0] == pytest.approx(-expected_shift, abs=1e-5)


def test_writes_csv_to_artifact_dir(tmp_path) -> None:
    """B12: 插补结果写入 _artifact_dir；未注入 _step_index 时默认 0 号产物。"""
    frame, _, _ = _frame_with_missing()
    step = _step(["x", "y"], _artifact_dir=str(tmp_path))

    result = impute(frame, step, step.params)

    path = result["imputed_dataset"]["path"]
    assert path.endswith("imputed_step_0.csv")
    assert (tmp_path / "imputed_step_0.csv").exists()
    assert result["imputed_dataset"]["name"].endswith("（MICE 插补）")


def test_missing_without_artifact_dir_does_not_crash(tmp_path) -> None:
    """B12: 未注入 _artifact_dir 时不落盘，但仍返回内存结果与提示。"""
    frame, _, _ = _frame_with_missing()

    result = impute(frame, _step(["x", "y"]), {})

    assert result["imputed_dataset"] is None
    assert result["missing_after"]["y"] == 0
    assert any("工作区" in item for item in result["warnings"])
