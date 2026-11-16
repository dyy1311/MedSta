# 032 - 会话持久化（重启恢复）

> 状态：done
> 创建：2026-11-16 ｜ 敲定：2026-11-16 ｜ 完成：2026-11-16
> 上游：TO_DO P1-1 前半（断线重连与历史回放拆至 033）

## 背景与目标

会话状态（工作区、列类型、方案、报告、交付态）目前只存内存，进程重启即全部丢失；
内部日常使用中「后端升级/崩溃后从头再来」是最痛的基础设施缺口。本 spec 让会话
具备跨重启恢复能力，同时为 033（WS 断线重连 + 历史回放）提供落盘基础。

## 范围

- 做：
  - 每会话一份 JSON 快照，原子写（临时文件 + `os.replace`）
  - 快照内容：status、active_dataset_id、数据集清单（id/name/路径/type_confirmed/逐列类型）、plan、report、version、updated_at
  - 启动恢复：`create_app(data_root=...)` 时从快照重建会话（DataFrame 从已落盘数据文件重新加载 + 列类型重放）
  - 关键节点持久化：上传、类型确认、切工作区、方案落定、报告产出、交付
- 不做（YAGNI）：
  - WS 断线重连、事件序号补发、聊天消息流回放（033）
  - `executing` 中间态恢复（重启后一律降为 `discussing`，见 B8）
  - 跨进程并发写保护（单进程部署假设）
  - 会话删除 API 与垃圾回收策略

## 行为列表（TDD 循环队列）

- [x] B1: 上传数据后，`<data_root>/<sid>/snapshot.json` 生成，含数据集 id/name/路径/type_confirmed=false
- [x] B2: 列类型敲定（WS `type_confirm` 或 REST PATCH）后快照同步更新（type_confirmed=true + 逐列类型）
- [x] B3: 快照写入为原子操作——序列化失败时旧快照不受损、无残留临时文件
- [x] B4: 以同一 data_root 重建 `create_app` 后会话恢复：会话存在、status/active_dataset_id 正确、画像列类型为修正后值（type_confirmed=true）
- [x] B5: 报告与交付态落盘：执行产出报告后快照含 report；`delivered` 后 status 正确；重启后 WS `resume` 能还原 review/delivered（`review_request` 带 report）
- [x] B6: 方案落盘：讨论产出 plan 后快照含 plan；重启后 `confirm_plan` 可直接执行（session.plan 已恢复）
- [x] B7: 损坏快照（非法 JSON）在启动恢复时被跳过，不影响其他会话恢复、不抛异常
- [x] B8: 快照 status=`executing` 时恢复为 `discussing`（未完成执行不可恢复）

## 验收标准

- [硬门] B1–B8 全部为确定性测试，走公共接口（TestClient/WS/`create_app`），不 mock 内部协作者
- [硬门] 既有 382 项测试全绿（`SessionManager.clear()` 测试接缝语义不变）
- [硬门] 快照文件不含 DataFrame 二进制/全量行数据（只有路径与类型映射），size 可控
- [软标] 快照含 `version` 字段，格式演进时可做兼容迁移
- [软标] 持久化失败不阻塞主流程（degrade 为内存模式，日志可见）

## 契约与测试映射

无模型参与（纯宿主确定性）。新增 WS/REST 契约：无（复用既有事件）。

| 行为 | 公共接口 | 测试文件 / 用例 |
|---|---|---|
| B1 | `POST /sessions/{id}/data` → `snapshot.json` | `tests/test_persistence.py::test_snapshot_written_on_upload` |
| B2 | WS `type_confirm` / `PATCH .../columns` | `test_persistence.py::test_snapshot_tracks_column_types` |
| B3 | `SessionStore.save` 原子性 | `test_persistence.py::test_snapshot_write_is_atomic` |
| B4 | 二次 `create_app(data_root=...)` | `test_persistence.py::test_session_restored_after_restart` |
| B5 | WS 执行→`resume` | `test_persistence.py::test_report_and_delivery_restored` |
| B6 | WS `chat`→`plan`→重启→`confirm_plan` | `test_persistence.py::test_plan_restored_and_executable` |
| B7 | 损坏快照文件 | `test_persistence.py::test_corrupt_snapshot_skipped` |
| B8 | `executing` 快照 | `test_persistence.py::test_executing_snapshot_downgrades_to_discussing` |

## 依赖与影响

- 依赖：`data/parser.load_table`（重建 df）、`profiler.profile_dataframe` + `apply_column_type`（重放类型）、既有 `data_root` 注入链
- 修改：`session/persistence.py`（新，SessionStore）、`session/service.py`（`_persist` 调用点 + `restore_all`）、`session/manager.py`（恢复接口）、`app.py`（启动恢复）
- 契约影响：无新 WS/REST 事件；`SessionManager.clear()` 保持「只清内存」语义（测试隔离不受快照影响——测试用 tmp data_root，天然隔离）
- 为 033 铺路：快照即回放数据源

## 备注

- 存储选 JSON+原子写而非 SQLite：会话量小、结构松散、无并发查询需求；033 若需事件日志再评估追加写文件
- 恢复的 `df` 从数据文件重新读取：上传文件本就落盘于 `data_root/<sid>/<dsid>/dataset.csv`，不重复存储
- `restored` 会话不含未完成后台任务（解释任务直接丢弃，交付态可重新 chat 触发答疑）
