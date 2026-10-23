"""结果解释：宿主给证据，模型写句子（spec 022）。

Owner 划分：
- 宿主：证据白名单抽取、契约校验、因果守卫、句数截断、未核验数值标记；
- 模型：只把已给定的数值组织成受控自然语言，不做统计推断。
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

from pydantic import BaseModel, Field

from medsta.agents.discussion import SAP_STATUS_DECLARED, AnalysisPlan, sap_status_of
from medsta.config import InterpretConfig, ModelGateway
from medsta.data.profiler import TableProfile

EXPLORATORY_CAVEAT = (
    "本次为探索性分析，未声明估计目标，也未经 SAP 冻结与样本量论证；结论不宜直接用于确证性推断。"
)
ESTIMAND_DECLARED_CAVEAT = (
    "本次已声明估计目标，但未经事前注册、SAP 冻结与样本量论证；仍不宜作为确证性结论。"
)

# 合规安全守卫：匹配「因素/干预 + 因果动词」的断言模式，而非裸词。
_CAUSAL_PATTERN = re.compile(
    r"(因素|干预|治疗|用药|分组|暴露|变量|指标)[^。！？]{0,12}?"
    r"(导致|引起|造成|使得|决定了|证明了|致使|带来了)"
)
_NEGATION_PATTERN = re.compile(r"(不能|无法|不足以|并不|未|不应|不可|不代表|不等于)")

_SENTENCE_DELIMITER = re.compile(r"(?<=[。！？])")
_INVERSE_P_VALUE = re.compile(r"[pP]\s*[<≤]\s*[\d.]+")

# 统计语篇中常见的非结论性数字：不参与「未核验」判定。
_COMMON_NUMBERS = {0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 95.0, 99.0, 100.0}


class StepInterpretation(BaseModel):
    step_index: int
    finding: str
    caveat: str = ""


class Interpretation(BaseModel):
    summary: str
    steps: list[StepInterpretation] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    unverified_numbers: list[str] = Field(default_factory=list)


class AnswerReply(BaseModel):
    answer: str
    caveats: list[str] = Field(default_factory=list)
    unverified_numbers: list[str] = Field(default_factory=list)


class _RawPayload(BaseModel):
    """暴露给模型的宽松契约出口：宿主随后做严格校验。"""

    summary: str = ""
    steps: list[dict[str, Any]] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    answer: str = ""

# 每种方法允许进入证据包的结论性数值键（白名单）。
# 未列出的键（原始行、完整表格、矩阵）一律不进 prompt。
_SIMPLE_KEYS: dict[str, tuple[str, ...]] = {
    "group_compare": ("test", "statistic", "p_value", "mean_diff", "ci95", "cohens_d", "groups"),
    "anova": ("test", "statistic", "p_value", "eta_squared", "epsilon_squared", "groups"),
    "chi_square": ("chi2", "dof", "p_value", "cramers_v", "odds_ratio"),
    "levene_test": ("statistic", "p_value", "homogeneous"),
    "normality_test": (),
    "missing_report": ("row_count", "complete_rows"),
    "regression": ("n", "r_squared", "adj_r_squared", "f_pvalue"),
    "logistic_regression": ("n", "pseudo_r_squared", "accuracy", "auc", "event_rate"),
    "correlation": ("method",),
    "timeseries_forecast": ("slope", "intercept", "r_squared", "forecast_n"),
    "describe": (),
    "aggregate_table": ("group_column", "agg"),
    "reference_range": ("percentage", "sides", "n", "lower", "upper", "z_value", "method"),
    "survival_analysis": ("n", "events", "censored", "median_survival", "chi2", "df", "method"),
}

_DESCRIPTIVE_KEYS = ("n", "mean", "sd", "cv", "median", "iqr", "geometric_mean", "recommended")


def build_evidence(
    report: dict,
    plan: AnalysisPlan,
    profile: TableProfile,
) -> dict:
    """把执行报告压缩成证据包：画像摘要 + 逐步结论性数值。

    只读取 `result` 的白名单键，绝不携带原始数据行。
    """
    steps: list[dict] = []
    report_steps = report.get("steps") or []
    for index, raw in enumerate(report_steps):
        plan_step = plan.steps[index] if index < len(plan.steps) else None
        method = str(raw.get("method", ""))
        result = raw.get("result") or {}
        steps.append(
            {
                "ref": f"S{index + 1}",
                "title": str(raw.get("title", "")),
                "method": method,
                "target_columns": list(getattr(plan_step, "target_columns", []) or []),
                "rationale": str(getattr(plan_step, "rationale", "") or ""),
                "params": dict(getattr(plan_step, "params", {}) or {}),
                "values": _extract_values(method, result),
                "method_note": str(result.get("method_note", "") or ""),
                "warning": str(result.get("multiplicity_warning", "") or ""),
                "error": _error_of(raw),
            }
        )
    return {
        "profile": {
            "rows": profile.row_count,
            "columns": profile.column_count,
            "types": {name: column.type for name, column in profile.columns.items()},
        },
        "estimand": plan.estimand.model_dump() if plan.estimand else None,
        "sap_status": sap_status_of(plan),
        "steps": steps,
    }


def _error_of(raw: dict) -> dict | None:
    error = raw.get("error")
    if not isinstance(error, dict):
        return None
    return {
        "code": str(error.get("code", "")),
        "message": str(error.get("message", "")),
    }


def _extract_values(method: str, result: dict) -> dict[str, Any]:
    if method == "descriptive_stats":
        return {
            str(name): {
                key: payload.get(key) for key in _DESCRIPTIVE_KEYS if payload.get(key) is not None
            }
            for name, payload in (result.get("columns") or {}).items()
            if isinstance(payload, dict)
        }
    values: dict[str, Any] = {}
    for key in _SIMPLE_KEYS.get(method, ()):
        value = result.get(key)
        if value is not None:
            values[key] = value
    strategy = result.get("strategy")
    if isinstance(strategy, dict) and strategy.get("final_method"):
        values["final_method"] = strategy["final_method"]
    return values


_INTERPRET_FIELDS = {
    "summary": (str, "受控总述：2–3 句，只引用证据中出现的数值，禁止因果断言"),
    "steps": (
        list,
        "逐步解读数组，每项含 step_index(int，报告步骤下标)/finding(str，不超过指定句数)/caveat(str，可空)",
    ),
    "caveats": (list, "全局注意事项数组：0–4 条字符串"),
}

_ANSWER_FIELDS = {
    "answer": (str, "针对用户问题的回答，只基于给定证据，禁止因果断言"),
    "caveats": (list, "回答的适用范围或局限：0–3 条字符串"),
}


def _interpret_instruct(max_sentences: int) -> str:
    return (
        "你是医学统计结果解读助手。只根据 info 中给出的证据撰写解读，规则：\n"
        "1) 只能引用 info 中出现的数值，不得自行计算、换算或编造；\n"
        "2) 禁止因果断言：不得使用「导致/引起/造成/使得/决定/证明」等表述；"
        "可以说「相关」「差异」「关联」，需要时明确写出「不能说明存在因果关系」；\n"
        f"3) 每个步骤的 finding 最多 {max_sentences} 句，一句话说清「发现了什么 + 数值证据」；\n"
        "4) summary 用 2–3 句概括整体结论与主要局限；caveats 给出 0–4 条可执行的注意事项；\n"
        "5) 证据不足以判断时直接说明「当前结果无法判断」，不要推测；\n"
        "6) 全部使用简体中文。"
    )


def _answer_instruct() -> str:
    return (
        "你是医学统计答疑助手。只根据 info 中给出的证据回答用户问题，规则：\n"
        "1) 不得新增分析、不得编造或换算数值；只能引用 info 中出现的数值；\n"
        "2) 禁止因果断言（导致/引起/造成/使得/决定/证明）；可以说明相关性与研究局限；\n"
        "3) 证据不足时回答「当前交付中无法回答」，并说明需要补充什么；\n"
        "4) 用简体中文，3 句以内；必要时给出 1–2 条 caveats。"
    )


def _causal_violation(text: str) -> str | None:
    """返回命中的因果断言片段；否定语境豁免。"""
    for match in _CAUSAL_PATTERN.finditer(str(text)):
        window = text[max(0, match.start() - 12) : match.end()]
        if _NEGATION_PATTERN.search(window):
            continue
        return match.group(0)
    return None


def _truncate_sentences(text: str, limit: int) -> str:
    parts = [part for part in _SENTENCE_DELIMITER.split(str(text).strip()) if part.strip()]
    if not parts:
        return ""
    return "".join(parts[: max(1, limit)]).strip()


def _allowed_numbers(value: Any, out: set[float] | None = None) -> set[float]:
    numbers = out if out is not None else set()
    if isinstance(value, bool):
        return numbers
    if isinstance(value, (int, float)):
        for digits in range(4):
            numbers.add(round(float(value), digits))
    elif isinstance(value, dict):
        for item in value.values():
            _allowed_numbers(item, numbers)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _allowed_numbers(item, numbers)
    return numbers


def _unverified_numbers(text: str, allowed: set[float]) -> list[str]:
    """文本中出现、但不在证据允许集中的数字（四舍五入与 p<0.001 形式放行）。"""
    cleaned = _INVERSE_P_VALUE.sub(" ", str(text))
    found: list[str] = []
    for token in re.findall(r"-?\d+(?:\.\d+)?", cleaned):
        number = float(token)
        if number in _COMMON_NUMBERS:
            continue
        if any(abs(number - candidate) < 1e-9 for candidate in allowed):
            continue
        if token not in found:
            found.append(token)
    return found


def _sap_caveat(plan: AnalysisPlan) -> str:
    """按估计目标状态选固定文案；两条互斥，避免互相稀释。"""
    if sap_status_of(plan) == SAP_STATUS_DECLARED:
        return ESTIMAND_DECLARED_CAVEAT
    return EXPLORATORY_CAVEAT


def _sanitize(
    raw: Interpretation,
    *,
    step_count: int,
    allowed: set[float],
    max_sentences: int,
    sap_caveat: str = EXPLORATORY_CAVEAT,
) -> Interpretation | None:
    """宿主校验：因果硬门、越界丢弃、句数截断、未核验数值标记。"""
    texts = [raw.summary, *[item.finding for item in raw.steps], *raw.caveats]
    if any(_causal_violation(text) for text in texts):
        return None

    steps: list[StepInterpretation] = []
    for item in raw.steps:
        if not 0 <= item.step_index < step_count:
            continue
        finding = _truncate_sentences(item.finding, max_sentences)
        if not finding:
            continue
        caveat = _truncate_sentences(item.caveat, 1) if item.caveat else ""
        steps.append(
            StepInterpretation(step_index=item.step_index, finding=finding, caveat=caveat)
        )
    if not steps:
        return None

    unverified: list[str] = []
    for text in texts:
        unverified.extend(_unverified_numbers(text, allowed))

    fixed_caveats = {EXPLORATORY_CAVEAT, ESTIMAND_DECLARED_CAVEAT}
    caveats = [
        str(item).strip()
        for item in raw.caveats
        if str(item).strip() and str(item).strip() not in fixed_caveats
    ]
    caveats.append(sap_caveat)
    return Interpretation(
        summary=_truncate_sentences(raw.summary, 3) or "本次分析已完成，详见各步骤结论。",
        steps=steps,
        caveats=caveats[:5],
        unverified_numbers=list(dict.fromkeys(unverified)),
    )


class InterpretationAgent:
    """证据 -> 受控解读 / 答疑。

    request_factory 仅用于测试在模型传输边界注入模拟实现。
    """

    def __init__(
        self,
        gateway: ModelGateway | None = None,
        request_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._gateway = gateway
        self._request_factory = request_factory

    def interpret(
        self,
        *,
        report: dict,
        plan: AnalysisPlan,
        profile: TableProfile,
        config: InterpretConfig | None = None,
        user_request: str = "",
    ) -> Interpretation | None:
        cfg = config or InterpretConfig()
        evidence = build_evidence(report, plan, profile)
        info = json.dumps(evidence, ensure_ascii=False, default=str)
        instruct = _interpret_instruct(cfg.max_sentences)
        allowed = _allowed_numbers(evidence)
        step_count = len(report.get("steps") or [])

        for _ in range(2):
            try:
                raw = self._dispatch(
                    input_value=user_request or plan.message,
                    info=info,
                    instruct=instruct,
                    fields=_INTERPRET_FIELDS,
                )
                parsed = Interpretation.model_validate(raw)
            except Exception:
                continue
            cleaned = _sanitize(
                parsed,
                step_count=step_count,
                allowed=allowed,
                max_sentences=cfg.max_sentences,
                sap_caveat=_sap_caveat(plan),
            )
            if cleaned is not None:
                return cleaned
            instruct += (
                "\n上一次输出被拒绝：出现因果断言或没有可用的步骤解读。"
                "请只做描述性表述，并确保每一步都有 step_index 与 finding。"
            )
        return None

    def answer(
        self,
        *,
        question: str,
        report: dict,
        plan: AnalysisPlan,
        profile: TableProfile,
    ) -> AnswerReply | None:
        """基于已交付报告的答疑：只解释，不新增分析。"""
        evidence = build_evidence(report, plan, profile)
        info = json.dumps(evidence, ensure_ascii=False, default=str)
        allowed = _allowed_numbers(evidence)
        instruct = _answer_instruct()

        for _ in range(2):
            try:
                raw = self._dispatch(
                    input_value=question,
                    info=info,
                    instruct=instruct,
                    fields=_ANSWER_FIELDS,
                )
                reply = AnswerReply.model_validate(raw)
            except Exception:
                continue
            text = str(reply.answer).strip()
            if not text:
                continue
            if _causal_violation(text):
                instruct += "\n上一次输出被拒绝：出现因果断言。请改为描述相关性或研究局限后重新回答。"
                continue
            fixed_caveats = {EXPLORATORY_CAVEAT, ESTIMAND_DECLARED_CAVEAT}
            caveats = [
                str(item).strip()
                for item in reply.caveats
                if str(item).strip() and str(item).strip() not in fixed_caveats
            ]
            caveats.append(_sap_caveat(plan))
            return AnswerReply(
                answer=text,
                caveats=caveats[:4],
                unverified_numbers=_unverified_numbers(text, allowed),
            )
        return None

    def _dispatch(self, *, input_value: str, info: str, instruct: str, fields: dict) -> dict:
        if self._request_factory is not None:
            return (
                self._request_factory()
                .input(input_value)
                .info(info)
                .instruct(instruct)
                .output(fields, format="json")
                .start()
            )
        assert self._gateway is not None, "需要 gateway 或 request_factory 之一"
        payload = self._gateway.request_structured(
            _RawPayload,
            fields=fields,
            input=input_value,
            info=info,
            instruct=instruct,
        )
        return payload.model_dump()
