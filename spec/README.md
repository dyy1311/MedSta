# Spec 生命周期规范

MedSta 采用 spec 驱动 + TDD 开发：**spec 敲定功能 → 按功能写测试 → 测试通过才能进入下一个周期。**

## 目录即状态

```
spec/
├── draft/        # 草稿：初步想法、目标、粗略行为列表
├── designing/    # 设计中：细化行为列表、验收标准、契约与测试映射
├── implementing/ # 实施中：spec 已敲定，按行为列表逐条 RED-GREEN
├── done/         # 完成：全部行为测试通过，spec 与时间线记录保留于此
├── archived/     # 废弃：放弃或被替代的 spec（含未实施即放弃）
└── templates/    # spec 模板
```

**用目录移动表达状态流转**，文件名保持不变（命名：`NNN-kebab-case-name.md`，NNN 为三位递增序号）。

## 流转规则

1. **draft → designing**：功能目标明确、值得做时移入 designing。
2. **designing → implementing**：满足以下全部条件才算"敲定"：
   - 行为列表完整且可测（每条是可观察的外部行为）；
   - 验收标准明确（含确定性测试可验证项与语义质量项的分类）；
   - 测试映射完成（每条行为对应哪个公共接口测试）；
   - 若涉模型输出：结构化输出契约（字段、类型、语义、可空性、约束）已声明。
3. **implementing → done**：行为列表全部 GREEN，且重构后仍全绿；在文件头更新完成日期，并在 `docs/timeline.md` 追加记录。
4. **任意状态 → archived**：放弃时在文件头写明废弃原因与日期，并记录时间线。
5. **禁止跳步**：未进入 implementing 不得写实现代码；implementing 中未 GREEN 不得声称功能完成。

## 实施中的 TDD 循环

- 取行为列表第一条：写测试 → 运行确认 RED（失败原因正确）→ 最小实现 → 运行确认 GREEN。
- 逐条循环，直到列表清空；随后做重构（每步保持全绿）。
- 测试走公共接口；仅在模型调用与文件系统边界 mock。

## 模板

新 spec 一律从 `templates/spec-template.md` 复制。
