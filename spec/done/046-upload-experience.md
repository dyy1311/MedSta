# 046 上传体验：行数限额与数据去向选择

## 背景

TO_DO P1 两项上传体验欠账：① 50MB 大小限额已有，但超大行数表仍会同步画像
（画像耗时未治理，宽扁表 50MB 可达数百万行）；② 已绑定数据的会话再上传时
被强制新建会话（`handleUpload` 检测到 `datasetId` 即开新会话），用户无法
选择「把新表加入当前工作区作为新数据集」——后端上传本就支持同会话多数据集，
纯前端缺一个选择入口。

## 行为列表（可测）

- B1 行数上限：数据行数超过 `MEDSTA_MAX_ROWS`（默认 200000）→ 400，
  文案含实际行数、上限值与调整途径；已写文件清理（不留孤儿）。
- B2 无绑定会话上传：行为不变（直接上传 / 无会话则先建会话）。
- B3 已绑定会话上传：任何入口（chat「+」、工作区「+」、全局拖拽）统一先弹
  「数据去向」选择，不直接执行。
- B4 选择「加入当前工作区」：上传到当前会话（同会话新增数据集标签，
  活跃切换沿用既有 data_profile 语义）；显式指定目标时不再强制新建。
- B5 选择「新建会话」：旧行为（新建会话 Tab 并绑定新表）。
- B6 取消：关闭弹层，不发起上传。

## 验收标准

- 硬门（确定性测试）：
  - `tests/test_upload_contract.py::test_upload_row_limit_rejected`（B1）；
  - `frontend/src/components/UploadChoiceDialog.test.tsx`（B3–B6 按钮语义：
  current/new/cancel 三回调精确触发）；
  - 既有上传/工作区/会话回归全绿（B2 不回归）。
- 软标：弹层与 042 拖拽遮罩同风格（深色主题、primary-cyan 令牌）；
  超限文案引导用户在样本上分析而非只报错。

## 测试映射

| 行为 | 测试 |
|---|---|
| B1 | test_upload_contract.py::test_upload_row_limit_rejected |
| B2 | 既有 test_upload_contract.py 全组回归 |
| B3–B6 | UploadChoiceDialog.test.tsx（组件级）+ App 接线由 tsc/vitest 全量回归守护 |

## 模型输出契约声明

零模型参与：本批为宿主边界校验与前端交互；无新增 ModelRequest 契约。
