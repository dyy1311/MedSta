---
name: medsta-config-fix
overview: 修复 config.py 真实模型接入的三个缺陷（.env 未自动加载、timeout dict 不完整、settings model 覆盖丢失插件默认值），补契约测试后复跑真实模型冒烟与端到端讨论链路验证。
design:
  architecture:
    framework: react
    component: shadcn
  styleKeywords:
    - 数据专业感
    - 双栏工作台
    - 清爽克制
    - 微动效
  fontSystem:
    fontFamily: PingFang SC
    heading:
      size: 24px
      weight: 600
    subheading:
      size: 16px
      weight: 500
    body:
      size: 14px
      weight: 400
  colorSystem:
    primary:
      - "#1E2A5A"
      - "#3B5BDB"
      - "#22B8CF"
    background:
      - "#F7F8FB"
      - "#FFFFFF"
    text:
      - "#1A1D2B"
      - "#6B7280"
      - "#FFFFFF"
    functional:
      - "#2F9E44"
      - "#E03131"
      - "#F08C00"
todos:
  - id: fix-config-env-timeout-merge
    content: 修复 config.py：from_env 加载 .env、timeout 补全四参数、build_settings 改逐键点路径合并保留插件默认值
    status: completed
  - id: update-config-tests
    content: 更新 tests/test_config.py：timeout 四参数断言、path_mapping/content_mapping 默认值保留断言、dotenv 加载测试
    status: completed
    dependencies:
      - fix-config-env-timeout-merge
  - id: real-model-e2e-verify
    content: 复跑全部 pytest（应 36+ 全绿）并用当前 .env 真实冒烟：ModelGateway 结构化请求 + 启动后端验证 WS 讨论不再报模型未配置
    status: completed
    dependencies:
      - update-config-tests
  - id: update-governance-docs
    content: 更新 docs/timeline.md 与 CODEBUDDY.md（.env 自动加载说明、deepseek-flash 为推理模型备注）
    status: completed
    dependencies:
      - real-model-e2e-verify
---

## 产品概述

修复 MedSta 后端真实模型接入的三个缺陷并完成真实模型验证，使 `.env`（DeepSeek，model=deepseek-flash）配置后即可开箱使用：讨论智能体、结果解释等模型功能无需手工 export 环境变量。

## 核心功能

- `.env` 自动加载：未手动 export 时 `build_gateway()` 能读取项目根目录 `.env`（python-dotenv 已在依赖中，未启用）
- 超时配置完整：timeout dict 包含 connect/read/write/pool 四参数，消除 httpx "Timeout must either include a default" 错误
- Agently settings 正确合并：保留 `plugins.ModelRequester.OpenAICompatible` 插件默认值（path_mapping/content_mapping 等），只覆盖显式配置项，消除 KeyError 'chat' 与 response_adapter 'NoneType' 错误
- 回归验证：既有 34 项测试全绿 + 真实模型冒烟（连通性结构化请求）通过 + 端到端讨论链路（无模型配置错误提示消失）

## 验收标准

- pytest 全绿（含新增的 settings 合并保留默认值断言、dotenv 加载测试）
- 真实模型冒烟脚本返回结构化结果（已在研究阶段验证修复方案可行：`REAL MODEL OK: ok=True`）
- 后端以当前 .env 配置启动后，WS 讨论不再返回"模型未配置”错误

## 技术方案

### 修改文件（均为已定位的确切目标）

- `backend/src/medsta/config.py`
- `from_env()`：入口处调用 `load_dotenv()`（默认搜索 cwd 向上找 .env；显式传入项目根路径更稳：从 `Path(__file__)` 上溯到仓库根加载 `.env`），保持显式参数优先、env 兜底的现有语义
- `build_settings()`：timeout 补全为 `{"connect": 10.0, "read": cfg.timeout, "write": cfg.timeout, "pool": 10.0}`；改为 `overrides = OpenAICompatibleSettings(...).to_settings_dict()` 后逐键 `facade.set_settings(f"plugins.ModelRequester.OpenAICompatible.{k}", v)` 点路径合并（保留插件默认 path_mapping/content_mapping；已在真实环境验证此写法成功返回）
- `backend/tests/test_config.py`
- 更新 B4 断言：补 timeout 四参数断言；新增断言：调用 `build_settings` 后插件默认 `path_mapping["chat"]`、`content_mapping` 仍存在（合并不覆盖）
- 新增 dotenv 加载行为测试：monkeypatch 清空 env → 临时写入 .env → `from_env()` 成功读取（或以 monkeypatch.setenv 模拟，不落盘）
- `docs/timeline.md`：追加 007 真实模型验证与缺陷修复记录

### 关键技术点

- Agently `set_settings` 语义：传 settings model 时经 `settings_model_to_pair` 整体替换命名空间（`to_settings_dict()` 只含显式字段，插件 DEFAULT_SETTINGS 全丢）；点路径 `set_settings(f"{ns}.{k}", v)` 为逐键合并。此结论经源码阅读（base.py:310、Settings.py:218、types/config.py:133）与真实调用双重验证
- `.env` 加载位置：放在 `from_env()` 而非模块顶层，避免 import 副作用；`load_dotenv(override=False)` 不覆盖已显式 export 的变量
- 不改 ModelGateway 契约与 DiscussionAgent；变更收敛在 config.py 单文件 + 测试

### 性能与可靠性

- 逐键 set_settings 为 O(n) n=显式配置项数（≤5），无性能影响
- 保留 `request_factory` 测试注入路径不变，模拟模型测试不受影响