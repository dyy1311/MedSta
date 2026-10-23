# 028 - 缺失数据路径（诊断 + MICE 插补 + 数据集产出）

> 状态：done
> 创建：2026-10-23 ｜ 敲定：2026-10-23 ｜ 完成：2026-10-23

## 背景与目标

项目目前只能报「缺了多少」，不能回答「为什么缺、该怎么处理、处理后还能不能分析」。
本 spec 把 `missing_report` 升级为诊断，并新增 `impute` 产出可继续分析的插补数据集。

**教材 0 覆盖**：`缺失值 / 插补 / MCAR / MAR / MNAR / 多重插补` 在《医学统计学》第 8 版中全部为 0 次，
无专章。全部依据外部标准（Little & Rubin 2019、van Buuren 2018），必须在 `method_note` 与
`docs/statistics-methods.md` 标注来源，不得声称「按教材」。

## 范围

- 做：缺失模式诊断、机制提示（不给判定）、完整行比例、阈值警告；MICE（m 次取均值 + 插补间方差）、
  median/mean/LOCF（仅敏感性）、单变量 delta 扫描、插补数据集写回工作区。
- 不做：完整多重插补与 Rubin 合并、MMRM、tipping point、MNAR 选择模型、纵向缺失、Little's MCAR 正式检验。

## 关键设计决策

1. **单数据集插补 ≠ 多重插补**：产出的数据集是 single imputation，标准误必然偏小。
   m 次插补取逐元素均值写入，另报 `between_imputation_variance` 作不确定性指示；
   但**不称**为 Rubin 合并。结果字段、`method_note`、数据集名称三处同时声明。
2. **不自动切换 active**：插补数据集注册后推 `dataset_added`，工作区追加标签页但保持当前 active，
   避免打断用户正在看的表。
3. **`_artifact_dir` 为内部保留键**：`execute_step` 向 `params` 注入，handler 据此写 CSV；
   该键不得出现在工具目录参数中，也不得被模型填写。
4. **机制只给提示**：不做 Little's MCAR 检验。用缺失模式形态 + 分组缺失差异卡方给 `mechanism_hint`，
   并固定声明「不能据此断定 MCAR/MAR/MNAR」。
5. **m 的边界**：默认 20；<20 时执行但给 warning；>50 截断到 50 并提示（性能保护）。

## 行为列表（TDD 队列，18 条）

- [x] B1: `missing_report` 输出逐列缺失模式（单变量/单调/非单调）与完整行比例
- [x] B2: 存在分组列时输出「缺失 vs 非缺失 × 组别」卡方与 p，p<0.05 时给机制提示
- [x] B3: 单列缺失 >50% 给「建议删除该列」警告；完整行 <10% 给样本量警告
- [x] B4: `missing_report` 明确声明「不能据此断定 MCAR/MAR/MNAR」
- [x] B5: `impute` 默认 MICE、m=20，插补后指定列无缺失且行列数不变
- [x] B6: `y=2x+ε` 置空 20% 后插补，恢复值与真实值相关 >0.8
- [x] B7: 无缺失时 `between_imputation_variance` 为 0；有缺失时 >0
- [x] B8: m<20 输出 warning 仍执行；m>50 截断到 50 并提示
- [x] B9: 单列缺失 >50% 时拒绝该列并给可读错误
- [x] B10: `method=median/mean/locf` 时 `sensitivity_only=true` 且不产出 `imputed_dataset`
- [x] B11: 传 `delta` 时输出三行扫描表，均值随 delta 线性偏移
- [x] B12: 插补数据集写出 CSV 到 `_artifact_dir`，文件名稳定
- [x] B13: `execute_step` 注入 `_artifact_dir`，不影响既有方法
- [x] B14: service 执行含 `impute` 的计划后 `datasets` 增一项，`active_dataset_id` 不变
- [x] B15: 推送 `dataset_added` 事件，含 dataset_id/name/profile/imputed/source_dataset_id
- [x] B16: 前端收到 `dataset_added` 追加工作区标签页且不切换 active
- [x] B17: 工作区画像表显示「已插补」角标
- [x] B18: `/capabilities` 中 `impute` 进入 tools，planned 的 multiple_imputation 说明改为「完整 MI 未实现」

## 验收标准

- [硬门] B1–B18 均有确定性测试，先确认 RED 再最小实现
- [硬门] MICE 插补后指定列无缺失、行列数不变、非目标列不被改动
- [硬门] 插补间方差在无缺失时为 0，有缺失时 >0
- [硬门] `sensitivity_only` 方法绝不产出 `imputed_dataset`
- [硬门] 插补数据集注册后 `active_dataset_id` 保持不变
- [硬门] 后端 `pytest` 全绿且覆盖率 ≥83%；前端 `vitest`/`build`/`lint` 全绿；E2E 2 项不回归
- [软标] `method_note` 能让非统计专业用户理解「单数据集插补的标准误偏小」

## 契约与测试映射

| 行为 | 公共接口 | 测试文件 |
|---|---|---|
| B1–B4 | `methods.missing_report` | `test_missing_report.py` |
| B5–B11 | `stats.impute.impute` | `test_impute.py` |
| B12/B13 | `registry.execute_step` | `test_impute.py::test_writes_csv_to_artifact_dir` |
| B14/B15 | `service._execute_plan` | `test_imputed_dataset_flow.py` |
| B16/B17 | `App.tsx` / `WorkspacePanel` | `App.imputed.test.tsx` / `WorkspacePanel.imputed.test.tsx` |
| B18 | `GET /capabilities` | `test_capabilities.py` |

## 关键字段

| 字段 | 说明 |
|---|---|
| `imputed_dataset` | `path`/`name`/`rows`/`columns`/`missing_before`/`missing_after`/`method`/`m` |
| `between_imputation_variance` | m 次插补间逐元素方差均值；无缺失时为 0 |
| `sensitivity_only` | median/mean/locf 为 true，不产出数据集 |
| `delta_scan` | `rows[{delta, mean, sd}]`，未传 delta 时为 None |
| `warnings` | m<20、缺失>50%、完整行<10% 等 |
| `mechanism_hint` | `kind`/`detail`/`disclaimer` |

## 依赖与影响

- `backend/pyproject.toml`：dependencies 加 `scikit-learn>=1.3`（**必需依赖**，非 extra）。
- `stats/impute.py`（新增）：`missing_pattern`、`mechanism_hint`、`impute_mice`、`impute_simple`、`delta_scan`、`impute`。
- `stats/methods.py`：`missing_report` 增强。
- `stats/registry.py`：注册 `impute`；`execute_step` 注入 `_artifact_dir`。
- `stats/notes.py`：新增 `impute` 说明（外部依据 + 单数据集≠MI）。
- `session/service.py`：`_execute_plan` 扫描 `imputed_dataset` → `attach_dataset` → 推 `dataset_added`。
- `agents/discussion.py`：`MethodType` 增 `impute`。
- `agents/interpretation.py`：`_SIMPLE_KEYS` 增 `impute`。
- `api/routes_capabilities.py`：planned 描述修正。
- 前端：`types.ts`、`App.tsx`、`WorkspacePanel.tsx`。
- 文档：`statistics-methods.md`、`design-notes.md`、`timeline.md`、`TO_DO.md`、`CODEBUDDY.md`、`spec/done/006-session-api.md`。

## 备注

- `IterativeImputer` 需 `from sklearn.experimental import enable_iterative_imputer`（sklearn 1.3+ 仍需）。
- 固定 `random_state=20261023`，保证同数据同结果。
- `between_imputation_variance` 量纲随列变化，只能作相对指示，不能当标准误。
- LOCF 按时间列排序后前向填充；无时间列时按原顺序。
- 插补数据集名称：`<原名>（MICE 插补）`。
