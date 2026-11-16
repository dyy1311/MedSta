# 040 - 分析报告导出（学术/轻量 × docx/pdf/md）

> 状态：done
> 创建：2026-11-17 ｜ 敲定：2026-11-17 ｜ 完成：2026-11-17
> 上游：用户确认——课题组共享部署（多用户化列为 041）；报告双风格、三格式随用户选择

## 背景与目标

分析交付目前是零散的表格/图，医学统计的最终交付物是**一份完整报告**。
本 spec 提供一键导出：用户自主选择**风格**（学术风：方法学章节化、图表编号、
教材口径；轻量风：结果要点式）与**格式**（docx / pdf / markdown），
闭合「数据 → 分析 → 交付物」链路。

## 范围

- 做：
  - 报告中间表示（ReportDocument：sections[]，段落/表格/图片/方法注）——风格在构建层、
    格式在渲染层，2×3 正交不爆炸
  - `GET /report/{session_id}?style=academic|lite&format=docx|pdf|md&report_id=`
    - md：纯字符串生成
    - docx：python-docx（三线表风、标题层级、图注）
    - pdf：reportlab + CJK 字体注册（复用 `_detect_cjk_font`，无字体时报错提示）
  - 素材：report（步骤表格/图/结果）、plan（步骤标题/rationale）、method_note、
    解释文本（record_store kind=interpretation，若有则附结论节）
  - 鉴权：/report 加入 API 前缀（038 中间件自动覆盖）
  - 前端：工作区「执行产出」区新增「导出报告」控件（风格 × 格式选择 → 下载）
- 不做（YAGNI）：
  - 模板化封面/机构 Logo 定制、参考文献管理、md→pdf 混排引擎
  - 多报告合并导出（按 report_id 单份导出）

## 行为列表（TDD 循环队列）

- [x] B1: md 学术风：含「方法学」章节（方法名+教材口径）、结果章节图表带编号（表 1/图 1）、解释结论节（有解释时）
- [x] B2: md 轻量风：无方法学章节，每步为「标题+表格+要点」，结构紧凑
- [x] B3: docx 可用 python-docx 打开：标题层级存在、表格数=步骤表格数、图片嵌入非空（学术风含方法学段落）
- [x] B4: pdf 魔数 `%PDF` 且页数 ≥1（CJK 字体路径）；环境无 CJK 字体时返回明确错误（跳过式断言）
- [x] B5: 会话无报告 404；非法 style/format 400；report_id 寻址历史报告
- [x] B6: 前端「导出报告」：风格与格式选择正确拼入下载链接

## 验收标准

- [硬门] B1–B6 确定性测试通过；既有测试全绿；ruff/mypy/CI 三道门不回退
- [软标] 文件名含会话标识与日期；md 编码 UTF-8

## 契约与测试映射

| 行为 | 接口 | 测试 |
|---|---|---|
| B1–B5 | `GET /report/{session_id}` | `tests/test_report_export.py` |
| B6 | WorkspacePanel | `src/workspace/WorkspacePanel.test.tsx` 追加 |
