"""027 B1–B9：Kaplan-Meier 与组间生存率比较。

数值基准来自《医学统计学》第 8 版第十四章例 14-2 与表 14-2（教材 p.146–148）。
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from medsta.stats.survival import km_estimate, logrank_test, survival_analysis

# 例 14-2：肿瘤直径 ≤2cm 组，15 例（`+` 表示删失）
TIME_14_2 = np.array([10, 10, 13, 18, 25, 29, 30, 33, 46, 50, 54, 68, 71, 88, 95], dtype=float)
EVENT_14_2 = np.array([1, 0, 1, 1, 0, 1, 1, 1, 1, 0, 1, 0, 1, 0, 0], dtype=int)

# 表 14-2 第 (8)(9) 栏，按 15 个时间点逐行
EXPECTED_SURVIVAL = [
    0.933, 0.933, 0.862, 0.790, 0.790, 0.711, 0.632, 0.553,
    0.474, 0.474, 0.379, 0.379, 0.253, 0.253, 0.253,
]
EXPECTED_SE = [
    0.064, 0.064, 0.091, 0.108, 0.108, 0.123, 0.132, 0.137,
    0.139, 0.139, 0.140, 0.140, 0.139, 0.139, 0.139,
]

# 例 14-2：肿瘤直径 >5cm 组，21 例（无删失）
TIME_GT5 = np.array(
    [5, 9, 13, 13, 14, 15, 19, 20, 21, 22, 24, 25, 26, 27, 28, 32, 47, 52, 54, 60, 86],
    dtype=float,
)
EVENT_GT5 = np.ones(21, dtype=int)


def test_km_survival_matches_table_14_2() -> None:
    """B1: KM 逐时间点生存率复现表 14-2 第 (8) 栏。"""
    result = km_estimate(TIME_14_2, EVENT_14_2)

    points = result["points"]
    assert len(points) == 15
    for point, expected in zip(points, EXPECTED_SURVIVAL):
        assert point["survival"] == pytest.approx(expected, abs=1e-3), point["time"]


def test_km_greenwood_se_matches_table_14_2() -> None:
    """B2: Greenwood 标准误复现表 14-2 第 (9) 栏。"""
    points = km_estimate(TIME_14_2, EVENT_14_2)["points"]

    for point, expected in zip(points, EXPECTED_SE):
        assert point["se"] == pytest.approx(expected, abs=1e-3), point["time"]


def test_censored_sorted_after_events_at_same_time() -> None:
    """B3: 同一时间点完全数据排在删失数据之前（教材 §14-2 计算规则）。"""
    points = km_estimate(TIME_14_2, EVENT_14_2)["points"]

    first, second = points[0], points[1]
    assert first["time"] == second["time"] == 10
    assert first["events"] == 1 and first["censored"] == 0
    assert first["n_at_risk"] == 15
    assert second["events"] == 0 and second["censored"] == 1
    assert second["n_at_risk"] == 14
    # 删失不改变生存率
    assert second["survival"] == pytest.approx(first["survival"], abs=1e-12)


def test_median_survival_interpolated() -> None:
    """B4: 生存率首次降至 50% 以下时在相邻时间点间插值。"""
    result = km_estimate(TIME_14_2, EVENT_14_2)

    # S(33)=0.553 > 0.5，S(46)=0.474 < 0.5 → 33 + (0.553−0.5)/(0.553−0.474)×13
    assert result["median_survival"] == pytest.approx(41.73, abs=0.05)
    assert result["median_reached"] is True
    assert result["median_survival_note"] == ""


def test_median_survival_not_reached() -> None:
    """B4: 随访期内生存率始终高于 50% 时返回 None 并说明。"""
    time = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
    event = np.array([0, 0, 0, 0, 1, 0, 0, 0, 0, 0])

    result = km_estimate(time, event)

    assert result["median_survival"] is None
    assert result["median_reached"] is False
    assert "未降至 50%" in result["median_survival_note"]


def test_confidence_interval_truncated_to_unit_range() -> None:
    """B5: 末端生存率 CI 超出 [0,1] 时截断并标记。"""
    time = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
    event = np.array([1, 0, 0, 0, 0, 0, 0, 0])

    result = km_estimate(time, event)

    assert result["ci_truncated"] is True
    for point in result["points"]:
        assert 0.0 <= point["ci_low"] <= 1.0
        assert 0.0 <= point["ci_high"] <= 1.0


def test_risk_table_reported() -> None:
    """B6: 输出风险人数表（时间点 × 期初人数 × 事件数 × 删失数）。"""
    result = km_estimate(TIME_14_2, EVENT_14_2)

    table = result["risk_table"]
    assert table["columns"] == ["time", "n_at_risk", "events", "censored"]
    assert len(table["rows"]) == 15
    assert table["rows"][0] == {"time": 10.0, "n_at_risk": 15, "events": 1, "censored": 0}


def test_logrank_two_groups() -> None:
    """B7: log-rank 两组检验输出 χ²、df=1、p。"""
    time = np.concatenate([TIME_14_2, TIME_GT5])
    event = np.concatenate([EVENT_14_2, EVENT_GT5])
    group = np.array(["le2cm"] * len(TIME_14_2) + ["gt5cm"] * len(TIME_GT5))

    result = logrank_test(time, event, group)

    assert result["method"] == "logrank"
    assert result["df"] == 1
    assert result["chi2"] > 0
    assert 0.0 <= result["p_value"] <= 1.0


def test_logrank_multi_group_uses_quadratic_form() -> None:
    """B8: 多组用 g−1 维二次型，自由度 g−1。"""
    rng = np.random.default_rng(27)
    groups = ("a", "b", "c")
    time = np.concatenate([rng.exponential(10 + index * 5, 20) + 1 for index in range(3)])
    event = np.ones(len(time), dtype=int)
    group = np.array([label for label in groups for _ in range(20)])

    result = logrank_test(time, event, group)

    assert result["df"] == 2
    assert result["chi2"] >= 0
    assert result["method"] == "logrank"


def test_breslow_weights_differ_from_logrank() -> None:
    """B9: Breslow 以 n_i 加权，与 log-rank 在同一数据上给出不同 χ²。"""
    time = np.concatenate([TIME_14_2, TIME_GT5])
    event = np.concatenate([EVENT_14_2, EVENT_GT5])
    group = np.array(["le2cm"] * len(TIME_14_2) + ["gt5cm"] * len(TIME_GT5))

    logrank = logrank_test(time, event, group)
    breslow = logrank_test(time, event, group, weight="breslow")

    assert breslow["method"] == "breslow"
    assert breslow["chi2"] != pytest.approx(logrank["chi2"], rel=1e-6)


def test_breslow_variance_uses_squared_weights() -> None:
    """P0: Breslow 加权和检验的方差项须乘 w²（Σw²·Var），否则 χ² 被系统性放大。

    手算基准：A 组 (1,事件)(5,删失)，B 组 (2,事件)(4,事件)(6,删失)。
    事件时刻 1/2/4 的 w 依次为 5/4/3，w² 依次为 25/16/9：
      O_A = 5·1 = 5，E_A = 5·(2/5)·1 + 4·(1/4)·1 + 3·(1/3)·1 = 4 → 差 = 1
      Var(A) = 25·0.4·0.6 + 16·0.25·0.75 + 9·(1/3)(2/3) = 11 → χ² = 1/11
    （缺 w² 时 Var(A)=2.6167，χ²=0.382，被放大 4 倍以上）
    """
    time = np.array([1.0, 5.0, 2.0, 4.0, 6.0])
    event = np.array([1, 0, 1, 1, 0])
    group = np.array(["a", "a", "b", "b", "b"])

    result = logrank_test(time, event, group, weight="breslow")

    assert result["chi2"] == pytest.approx(1.0 / 11.0, abs=1e-6)


def test_rmst_group_comparison_uses_common_tau() -> None:
    """P0: 未指定 tau 时组间 RMST 须以「各组最大随访最小值」统一截断后才能相减。

    registry 承诺 tau「默认各组最大随访最小值」；各组各用自己的最大随访
    截断会导致 tau 不同的 RMST 直接相减，差值无效。
    """
    frame = pd.DataFrame(
        {
            "time": [1.0, 2.0, 3.0, 20.0, 1.0, 2.0, 3.0, 30.0],
            "event": [1, 1, 1, 0, 1, 1, 1, 0],
            "group": ["a", "a", "a", "a", "b", "b", "b", "b"],
        }
    )
    step = SimpleNamespace(target_columns=["time", "event"])

    result = survival_analysis(
        frame,
        step,
        {"time_col": "time", "event_col": "event", "group_col": "group", "method": "km"},
    )

    groups = result["rmst"]["groups"]
    assert groups["a"]["tau"] == pytest.approx(20.0)
    assert groups["b"]["tau"] == pytest.approx(20.0)
