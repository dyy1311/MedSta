"""内置统计方法学 skills：从高分医学统计报告规范与检验选择决策树提炼。

来源与取舍（不照抄原文，只保留可执行规则）：
- SAMPL（Lang & Altman，EQUATOR Network）：统计方法描述、样本量依据、缺失数据处理、
  效应量与置信区间、精确 p 值、软件与版本、敏感性分析、多重比较声明；
- 通用检验选择决策树：结局类型 → 组数 → 配对与否 → 正态性/方差齐性；
- 常见误用清单：类别列当目标列、多组两两比较不校正、把 P>0.05 读作「无差异」、
  用「显著性」替代效应量、缺失值直接删除不说明。

宿主只做**关键词挑选 + 长度裁剪**（确定性），模型负责语义判断——避免「用正则做语义」。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StatsSkill:
    """一条方法学 skill：何时用、硬规则、常见误用、报告要求。"""

    key: str
    title: str
    when: str
    rules: tuple[str, ...]
    pitfalls: tuple[str, ...]
    reporting: tuple[str, ...]
    keywords: tuple[str, ...] = field(default=())

    def digest(self) -> str:
        rules = "；".join(self.rules)
        traps = "；".join(self.pitfalls)
        return f"- {self.title}（{self.when}）：{rules}。误用：{traps}"


SKILLS: tuple[StatsSkill, ...] = (
    StatsSkill(
        key="continuous_two_group",
        title="连续变量·两组比较",
        when="两组独立样本比较均值/分布",
        rules=(
            "先看分布：Shapiro-Wilk 正态 + Levene 方差齐 → t；不齐用 Welch t；非正态用 Mann-Whitney U",
            "报告均值差或中位数差及其 95%CI，不只给 P 值",
            "样本量 <30 或强偏态时优先非参数，并说明降级理由",
        ),
        pitfalls=(
            "把类别列（是否手术/性别）当目标列",
            "对配对数据用独立样本检验",
            "P>0.05 直接写「两组相同」（应写「未发现差异」并给 CI）",
        ),
        reporting=("组样本量 n、均值±SD 或 M(P25~P75)、效应量与 CI、精确 P（P=0.03 而非 P<0.05）",),
        keywords=("两组", "t检验", "均数", "均值", "Mann", "秩和", "比较"),
    ),
    StatsSkill(
        key="continuous_multi_group",
        title="连续变量·多组比较",
        when="三组及以上比较（ANOVA / Kruskal-Wallis）",
        rules=(
            "两组用 t/Mann-Whitney，三组及以上用 ANOVA/Kruskal-Wallis（不要两两硬做 t）",
            "ANOVA 显著后做事后比较并校正（Tukey/Holm/Dunnett）；Dunnett 需指定对照组",
            "方差不齐用 Welch ANOVA；非正态用 Kruskal-Wallis + Dunn",
        ),
        pitfalls=("多次两两 t 检验不校正（假阳性膨胀）", "只报总体 P 不报具体哪两组有差异"),
        reporting=("总体检验 + 事后比较的校正方法与两两结果、各组 n 与离散度",),
        keywords=("三组", "多组", "方差分析", "ANOVA", "kruskal", "事后", "两两"),
    ),
    StatsSkill(
        key="categorical_association",
        title="分类变量·关联与构成",
        when="两个类别变量的关联、组间率比较",
        rules=(
            "卡方检验：任一格期望频数 <5 时改用 Fisher 精确检验（2×2）或合并类别",
            "报告率差/OR 及 CI；R×C 表只说明整体关联，定位需分区卡方并校正",
            "配对二分类（同一批人前后）用 McNemar，不用普通卡方",
        ),
        pitfalls=("小样本仍用卡方", "从整体卡方推出具体某两组不同", "忽略表格方向导致 OR 解释反了"),
        reporting=("各格频数与百分比、检验方法、效应量（OR/RD）与 CI",),
        keywords=("率", "构成", "卡方", "chi", "频数", "比例", "四格表"),
    ),
    StatsSkill(
        key="paired_design",
        title="配对/前后设计",
        when="同一对象前后测量或配对样本",
        rules=(
            "连续配对差值近似正态 → 配对 t；否则 Wilcoxon 符号秩",
            "二分类配对 → McNemar；配对一致性看 Kappa/ICC 而不是相关",
        ),
        pitfalls=("配对数据当独立样本（丢失配对信息、低估精度）",),
        reporting=("差值均值/中位数与 CI、配对样本量、失访处理",),
        keywords=("配对", "前后", "自身对照", "重复测量", "wilcoxon"),
    ),
    StatsSkill(
        key="correlation_regression",
        title="相关与回归",
        when="变量间关联强度或影响因素建模",
        rules=(
            "先看散点/线性假设；偏态或离群值用 Spearman",
            "线性回归报告系数、95%CI、R²；logistic 报告 OR 与 CI 并检查分离与事件数（EPV）",
            "多因素模型需说明变量筛选依据，勿按单因素 P 值机械挑选",
        ),
        pitfalls=("相关系数当因果", "共线性未检查", "事件数过少仍塞入过多自变量"),
        reporting=("模型形式、纳入变量与理由、系数/OR+CI、拟合指标与假设检验",),
        keywords=("相关", "回归", "影响因素", "预测", "OR", "logistic", "线性"),
    ),
    StatsSkill(
        key="survival",
        title="生存分析",
        when="带随访时间与结局事件（含删失）",
        rules=(
            "先 KM 曲线与中位生存期，再 log-rank（多组）与 Cox（多因素）",
            "Cox 需检验 PH 假设（Schoenfeld）；不满足时考虑分层或时依效应",
            "随访不足时同时给 RMST（限制平均生存时间），不要只看 HR",
        ),
        pitfalls=("忽略删失直接算率", "把 HR 当风险比绝对差", "中位随访不足却宣称长期疗效"),
        reporting=("随访时间定义、删失比例、事件数、HR+CI、PH 检验结果",),
        keywords=("生存", "随访", "删失", "KM", "cox", "HR", "复发", "死亡"),
    ),
    StatsSkill(
        key="missing_data",
        title="缺失数据",
        when="任意变量存在缺失",
        rules=(
            "先量化缺失（每变量 n/%）与模式（单变量/单调/任意），再谈处理",
            "完全随机缺失可完整病例分析；否则优先多重插补（MICE），单次插补只作敏感性分析",
            "插补后分析需合并插补间方差，不可把插补数据当真实观测",
        ),
        pitfalls=("直接 dropna 不说明", "把 LOCF 当确证性方法", "插补后不报告缺失比例"),
        reporting=("缺失量/模式/机制假设、处理方法与敏感性分析",),
        keywords=("缺失", "插补", "NA", "missing", "填补"),
    ),
    StatsSkill(
        key="sample_size",
        title="样本量与效能",
        when="研究设计期或解释「无差异」时",
        rules=(
            "先验样本量需给效应量来源、α、power（常用 0.8）与单双侧",
            "事后效能（observed power）不能替代样本量论证",
            "阴性结果需说明把握度不足的可能",
        ),
        pitfalls=("用观测到的效应量反推效能", "只写「样本量足够」无计算依据"),
        reporting=("效应量假设及其来源、α、power、单双侧、计算软件",),
        keywords=("样本量", "效能", "power", "把握度", "例数"),
    ),
    StatsSkill(
        key="multiple_comparisons",
        title="多重比较",
        when="同一数据做多次检验（多终点/多组/亚组）",
        rules=(
            "事前声明主要终点与次要终点；确证性推断需 gatekeeping/固定序列，本系统默认不做确证性推断",
            "探索性多重比较用 Holm（默认）或 BH-FDR；Bonferroni 偏保守",
            "亚组分析标注为探索性，不做确证性解读",
        ),
        pitfalls=("只对显著的比较做校正", "把探索性亚组结果写成确证结论"),
        reporting=("校正方法、校正前后 P、主要/次要终点划分",),
        keywords=("多重", "校正", "holm", "bonferroni", "亚组", "多次比较"),
    ),
    StatsSkill(
        key="reporting_sampl",
        title="统计报告规范（SAMPL）",
        when="任何交付结果/撰写报告时",
        rules=(
            "统计方法写到「同行拿到原始数据可复现」：检验名、单双侧、α、软件与版本",
            "每个效应都给点估计 + 95%CI；P 值给精确值（极小用 P<0.001）",
            "说明缺失处理、异常值规则、多重比较与敏感性分析；相关不等于因果",
        ),
        pitfalls=("只写 P<0.05 不写方法名", "用「显著」替代效应量", "把统计显著写成临床有意义"),
        reporting=("方法段落 + 每张表的 n/统计量/CI/P + 软件版本",),
        keywords=("报告", "论文", "写文章", "结果解释", "投稿"),
    ),
)

_BY_KEY = {skill.key: skill for skill in SKILLS}


def select_skills(text: str, limit: int = 4) -> list[StatsSkill]:
    """按关键词命中挑选 skills（宿主确定性规则；未命中时给默认组合）。"""
    lowered = (text or "").lower()
    scored: list[tuple[int, int, StatsSkill]] = []
    for order, skill in enumerate(SKILLS):
        hits = sum(1 for keyword in skill.keywords if keyword.lower() in lowered)
        if hits:
            scored.append((hits, -order, skill))
    scored.sort(reverse=True)
    picked = [skill for _, _, skill in scored[:limit]]
    if picked:
        return picked
    # 没有明显关键词：给「报告规范 + 缺失数据」这两条通用约束
    return [_BY_KEY["reporting_sampl"], _BY_KEY["missing_data"]]


def skills_digest(skills: list[StatsSkill], limit: int = 1400) -> str:
    """把 skills 压成 prompt 可注入的紧凑文本（长度受限，避免挤占画像与工具目录）。"""
    lines = [skill.digest() for skill in skills]
    text = "\n".join(lines)
    return text[:limit]


def skills_for_request(text: str, limit: int = 4) -> str:
    """一步到位：诉求 → 相关 skills 文本。"""
    return skills_digest(select_skills(text, limit=limit))
