"""035 后续：统计层中危修复 M8/M19/M20 的守护测试。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from medsta.stats.impute import impute, impute_mice
from medsta.stats.survival import _schoenfeld_check

# ---- M8: Schoenfeld 残差检查排除删失行（statsmodels 置 0 的伪残差） ----


class _FakeCoxModel:
    def schoenfeld_residuals(self):
        # 6 行：前 4 行事件（残差随时间递增），后 2 行删失（statsmodels 0.14 置 0）
        return np.array([[1.0], [2.0], [3.0], [4.0], [0.0], [0.0]])


def test_schoenfeld_check_excludes_censored_rows() -> None:
    times = np.array([1.0, 2.0, 3.0, 4.0, 100.0, 200.0])
    events = np.array([1, 1, 1, 1, 0, 0])

    checks = _schoenfeld_check(_FakeCoxModel(), ["x"], times, events)

    assert len(checks) == 1
    # 缺陷实现把删失行（残差 0 + 超大时间）一并纳入 Spearman → rho 被稀释、p 值变大
    assert checks[0]["rho"] == pytest.approx(1.0)
    assert checks[0]["p_value"] < 0.05


# ---- M19: MICE 插补间方差只在缺失格计算（观测格不稀释） ----


class _FakeIterativeImputer:
    """确定性替身：第 k 次调用把缺失格填为 k（观测格原样保留）。"""

    counter = 0

    def __init__(self, **kwargs) -> None:
        pass

    def fit_transform(self, data):
        _FakeIterativeImputer.counter += 1
        filled = np.array(data, dtype=float, copy=True)
        filled[np.isnan(filled)] = float(_FakeIterativeImputer.counter)
        return filled


def test_between_variance_only_over_missing_cells(monkeypatch) -> None:
    # 先真实 enable（sklearn experimental 守卫），否则 monkeypatch 读取属性时抛 ImportError
    from sklearn.experimental import enable_iterative_imputer  # noqa: F401

    monkeypatch.setattr("sklearn.impute.IterativeImputer", _FakeIterativeImputer)
    _FakeIterativeImputer.counter = 0

    frame = pd.DataFrame({"x": [1.0, 2.0, np.nan, np.nan]})
    _, between = impute_mice(frame, ["x"], m=3, max_iter=1, random_state=1)

    # 缺失格 2 个 × 3 次插补值 [1,2,3] → 每格方差 var([1,2,3], ddof=1)=1
    # 缺陷实现把观测格（方差恒 0）计入均值 → 被稀释为 1 × 2/4 = 0.5
    assert between == pytest.approx(1.0)


# ---- M20: 插补产物按步骤索引命名，同计划两次插补不再互相覆盖 ----


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {"group": ["A", "A", "B"], "value": [1.0, np.nan, 3.0], "age": [25.0, 31.0, 42.0]}
    )


def _impute_step() -> object:
    from medsta.agents.discussion import PlanStep

    return PlanStep(
        title="插补",
        method="impute",
        target_columns=["value"],
        chart_type="none",
        params={},
        rationale="缺失插补",
    )


def test_imputed_csv_names_include_step_index(tmp_path) -> None:
    step = _impute_step()
    frame = _frame()

    first = impute(frame, step, {"_artifact_dir": str(tmp_path), "_step_index": 0})
    second = impute(frame, step, {"_artifact_dir": str(tmp_path), "_step_index": 1})

    path0 = first["imputed_dataset"]["path"]
    path1 = second["imputed_dataset"]["path"]
    assert path0.endswith("imputed_step_0.csv")
    assert path1.endswith("imputed_step_1.csv")
    assert (tmp_path / "imputed_step_0.csv").is_file()
    assert (tmp_path / "imputed_step_1.csv").is_file()


# ---- 审查修复批（P1）：McNemar 单元格含义按列联表真实水平生成 ----


def test_mcnemar_cell_meanings_follow_actual_levels() -> None:
    """P1: 中文编码（「阳」U+9633 排序先于「阴」U+9634）下，
    crosstab 首行是「阳」——a=「两法均阳性」的硬编码文案会贴在两法均「阴」的格子上。
    """
    from medsta.agents.discussion import PlanStep
    from medsta.stats.inference import mcnemar_test

    df = pd.DataFrame(
        {
            "甲法": ["阳", "阳", "阳", "阴"],
            "乙法": ["阳", "阳", "阴", "阴"],
        }
    )
    step = PlanStep(
        title="配对四格表", method="mcnemar_test",
        target_columns=["甲法", "乙法"], chart_type="none",
        params={"row_column": "甲法", "col_column": "乙法"},
        rationale="测试依据：配对二分类",
    )

    result = mcnemar_test(df, step, step.params)
    meanings = {row["cell"]: row["meaning"] for row in result["table"]["rows"]}

    # 排序后 index[0]=「阳」、index[1]=「阴」→ a 单元格是两法均「阴」
    assert "阴" in meanings["a"] and "均" in meanings["a"]
    assert "阳" in meanings["d"] and "均" in meanings["d"]
    # 对角线（一致格）口径不受单元格语义影响
    assert result["agreement_rate"] == pytest.approx(3 / 4)
