# 012 - 多工作区（多表格分页）与能力披露修复

> 状态：done
> 创建：2026-10-19 ｜ 敲定：2026-10-19 ｜ 完成：2026-10-19

## 背景与目标

用户需同时分析多个表格：每个上传表格为独立工作区，分页切换；讨论与执行作用于当前激活工作区。另修复能力抽屉"目录加载失败"（vite proxy 缺 /capabilities）。

## 范围

- 做：Session 多数据集（datasets dict + active_dataset_id）；上传返回 dataset_id；激活接口；chat/confirm 作用于激活工作区；前端工作区 Tab 条与"+"追加上传；vite proxy 修复与 fetchCapabilities 容错
- 不做：工作区删除/重命名、跨工作区联合分析

## 行为列表（TDD 循环队列）

- [x] B1: 同一会话两次上传得到两个不同 dataset_id，均可取回画像
- [x] B2: activate 切换激活工作区；chat/confirm 使用激活数据集的画像与数据
- [x] B3: 未上传数据时 chat 返回 DATA_REQUIRED；激活不存在的 dataset 返回错误
- [x] B4: dev 代理修复后 fetch /capabilities 返回 JSON（httpx 冒烟）

## 验收标准

- [硬门] B1–B4 测试 GREEN，既有测试不回归
- [软标] 切换 Tab 有过渡动画

## 契约与测试映射

| 行为 | 公共接口 | 测试 |
|---|---|---|
| B1/B2/B3 | `SessionManager.attach_dataset/activate`、`SessionService` | `tests/test_workspace.py` |
| B4 | vite proxy | dev 冒烟（curl 5173→/capabilities） |

## 依赖与影响

`Session.data` 字段变更为 `datasets`/`active_dataset_id`（兼容读取 `active_data` 属性）；routes_data 返回结构扩展。
