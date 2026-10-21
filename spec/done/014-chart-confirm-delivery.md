# 014 - 出图确认、可视化交付与依据展示

> 状态：done
> 创建：2026-10-19 ｜ 敲定：2026-10-19 ｜ 完成：2026-10-19

## 背景与目标

出图前与用户确认图表类型与画板布局；交付以可视化表格呈现并支持 Excel/CSV 导出；多重检验给出总体+两两分析与修正提醒；思考过程可折叠。

## 范围

- 做：`chart_config`/`chart_choice` 事件（每步图表类型含 pie、多图 shared/separate、α、correction）；执行消费配置；显著性绘图标注（组间比较线+星号/ns）；`StepResult.table`（columns+rows 含 statistic/p/significance）；`GET /export/{session_id}/{step_index}?format=csv|xlsx`；前端工作区 Tab、分析配置卡、可视化交付卡（多重提醒条+策略链展示）、方案卡 rationale 折叠、思考折叠、能力抽屉适用条件
- 不做：图表在线编辑、跨工作区对比图

## 行为列表（TDD 循环队列）

- [x] B1: 确认后存在带图步骤 → 下发 chart_config（默认类型、可选列表、布局、α、correction）
- [x] B2: chart_choice 回填后按所选类型与布局渲染；跳过用默认
- [x] B3: 多图 shared 渲染为一张拼图 artifact；separate 为多个文件
- [x] B4: 组间比较图标注星号/ns
- [x] B5: StepResult.table 生成；/export csv 与 xlsx 可下载且内容正确
- [x] B6: 前端构建通过；思考/依据/策略链 UI 呈现

## 验收标准

- [硬门] B1–B5 pytest GREEN；B6 build 通过
- [软标] 显著性标注位置美观、不遮挡

## 契约与测试映射

公共接口：`SessionService.handle(chart_config 事件)`、`AnalysisWorkflow`（配置注入）、`plotting.render_chart(layout)`、`api/routes_export.py`。测试：`tests/test_chart_flow.py`、`tests/test_export.py`。

## 依赖与影响

依赖 012/013。executor 接受 chart 配置（chart_type 覆盖 + layout + alpha + correction）。
