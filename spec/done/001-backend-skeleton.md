# 001 - 后端骨架与会话创建

> 状态：done
> 完成日期：2026-10-17（34 项测试全绿后复审迁入）
> 创建：2026-10-17 ｜ 敲定：2026-10-17 ｜ 完成：2026-10-17

## 背景与目标

为 MedSta 后端建立可运行骨架：FastAPI 应用入口、OpenAI 兼容模型配置（Agently settings）、会话创建公共接口。这是所有后续功能（数据解析、讨论智能体、pipeline）的地基。

## 范围

- 做：健康检查端点；会话创建（返回会话 ID，状态 discussing）；Agently OpenAI 兼容 provider 配置模块（可注入模拟模型）；模型调用经 `ModelRequest` 的最小结构化契约验证（echo/ping 级别）。
- 不做：WebSocket、数据上传、讨论逻辑、持久化（后续 spec）。

## 行为列表（TDD 循环队列）

- [x] B1: GET /health 返回 200 与 `{"status": "ok"}`
- [x] B2: POST /sessions 创建会话，返回唯一 session_id 且 status 为 "discussing"
- [x] B3: 两次创建会话得到不同 session_id
- [x] B4: `build_settings` 生成的 Agently settings 使用环境变量/显式参数中的 base_url、api_key、model（OpenAI 兼容 provider）
- [x] B5: 经 `ModelRequest` 发起的最小结构化请求在使用模拟模型时返回符合声明的 output 契约

## 验收标准

- [硬门] B1–B5 全部由 pytest 走公共接口（TestClient / 直接调用模块函数）验证为 GREEN
- [硬门] 测试不依赖真实模型 API（B5 用模拟模型）
- [软标] config 模块不硬编码任何密钥，provider 参数可完全外部化

## 契约与测试映射

| 行为 | 公共接口 | 测试文件 / 用例 |
|---|---|---|
| B1 | `GET /health`（FastAPI app） | `tests/test_app.py::test_health` |
| B2 | `POST /sessions` | `tests/test_app.py::test_create_session` |
| B3 | `POST /sessions` | `tests/test_app.py::test_session_ids_unique` |
| B4 | `medsta.config.build_settings` | `tests/test_config.py::test_settings_use_provider_config` |
| B5 | `medsta.config.ModelGateway.request_structured`（封装 ModelRequest） | `tests/test_config.py::test_structured_request_with_mock_model` |

## 依赖与影响

- 无既有依赖；为 002（数据解析）、003（讨论智能体）提供 app、config、会话管理骨架。

## 备注

- B5 采用 Agently `start().chat.model(...)` settings 配置 OpenAI 兼容 provider；测试通过替换 model 层为模拟实现验证契约，不引入真实请求。
