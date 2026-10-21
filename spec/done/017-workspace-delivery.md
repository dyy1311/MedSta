# 017 - 会话/工作区语义重构：追加导入、交付进工作区、绘图追问

> 状态：done
> 创建：2026-10-19 ｜ 敲定：2026-10-19 ｜ 完成：2026-10-19

## 背景与目标

会话区应只承载 LLM 交互；数据画像、交付表格、图表属于工作区。当前"+"导入未实装、表格结果以 JSON 直出在会话流、表格型步骤交付后无"是否绘图"追问。

## 范围

- 做：工作区"+"内嵌 file input 直接上传并新建 Tab；ChatPanel 仅在无工作区时显示完整上传区；交付表格卡渲染进工作区（含 CSV/XLSX 导出），会话流 ReviewCard 精简为摘要卡（状态+图表链接+去工作区）；表格型步骤交付后 `plot_suggest`（可选图类型）→ `plot_later` 单步补渲染并更新报告
- 不做：工作区内联数据编辑（后续 spec）、图表删除管理

## 行为列表（TDD 循环队列）

- [x] B1: WorkspacePanel"+"上传后新建 Tab 并激活（前端行为，build + 交互冒烟验证）
- [x] B2: 表格型步骤（有 table）交付后服务端发 plot_suggest（含该步骤可绘图类型）
- [x] B3: plot_later 指定 chart_type 后补渲染 artifact 并重发 review_request（更新后的报告）
- [x] B4: 无 table 步骤不发 plot_suggest
- [x] B5: ReviewCard 摘要化 + 工作区表格卡（前端，build 验证）

## 验收标准

- [硬门] B2–B4 pytest GREEN；B1/B5 build 通过 + 端到端冒烟
- [硬门] 补渲染复用 render_chart，不重复执行统计计算

## 契约与测试映射

| 行为 | 接口 | 测试 |
|---|---|---|
| B2–B4 | `SessionService.handle`（plot_suggest/plot_later） | `tests/test_plot_suggest.py` |
| B1/B5 | 前端组件 | `npm run build` + e2e |
