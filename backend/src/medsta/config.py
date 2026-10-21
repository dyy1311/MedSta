"""MedSta 模型配置与 ModelRequest 网关。

Owner 划分（见 docs/design-notes.md）：
- Provider 接入：Agently settings（OpenAICompatibleSettings，OpenAI 兼容接口）
- 单次模型交互与输出契约：ModelRequest 四段式（input/info/instruct/output）
- schema 校验：宿主（pydantic）确定性验证，模型只做语义决策
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import agently
from agently.types.settings import OpenAICompatibleSettings
from dotenv import load_dotenv
from pydantic import BaseModel

_PROVIDER_NAMESPACE = "plugins.ModelRequester.OpenAICompatible"

# 项目根目录（backend/src/medsta/config.py → 上溯三级）
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class ProviderConfig:
    """OpenAI 兼容 provider 连接配置。"""

    base_url: str
    api_key: str
    model: str
    timeout: float = 120.0

    @classmethod
    def from_env(cls) -> "ProviderConfig":
        # 未手动 export 时自动加载项目根 .env；不覆盖已显式设置的变量
        load_dotenv(_PROJECT_ROOT / ".env", override=False)
        base_url = os.environ.get("LLM_BASE_URL", "")
        api_key = os.environ.get("LLM_API_KEY", "")
        model = os.environ.get("LLM_MODEL", "")
        missing = [
            name
            for name, value in (
                ("LLM_BASE_URL", base_url),
                ("LLM_API_KEY", api_key),
                ("LLM_MODEL", model),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(
                f"缺少模型配置环境变量：{', '.join(missing)}（参考 .env.example）"
            )
        return cls(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout=float(os.environ.get("LLM_TIMEOUT", "120")),
        )


def build_settings(config: ProviderConfig, agently_facade: Any | None = None) -> Any:
    """把 provider 配置写入 Agently settings（OpenAICompatible，chat 端点族）。

    必须逐键点路径合并：直接传 settings model 会经 settings_model_to_pair
    整体替换插件命名空间，丢失 path_mapping/content_mapping 等插件默认值。
    """
    facade = agently_facade if agently_facade is not None else agently.Agently
    overrides = OpenAICompatibleSettings(
        base_url=config.base_url,
        api_key=config.api_key,
        model=config.model,
        model_type="chat",
        timeout={
            "connect": 10.0,
            "read": config.timeout,
            "write": config.timeout,
            "pool": 10.0,
        },
    ).to_settings_dict()
    for key, value in overrides.items():
        facade.set_settings(f"{_PROVIDER_NAMESPACE}.{key}", value)
    return facade


class ModelGateway:
    """单次模型交互的唯一入口：四段式契约 + 宿主 schema 校验。

    request_factory 仅用于测试在模型传输边界注入模拟实现。
    """

    def __init__(
        self,
        agently_facade: Any,
        request_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._agently = agently_facade
        self._request_factory = request_factory

    def request_structured(
        self,
        schema: type[BaseModel],
        *,
        fields: dict[str, tuple],
        input: Any = None,
        info: Any = None,
        instruct: str,
    ) -> BaseModel:
        """发起一次结构化请求并返回宿主校验后的结果。

        - fields：output 契约，字段名 -> (类型, 描述)
        - 消费字段必须全部出现在 fields 中；模型不得产出契约外字段
        """
        if self._request_factory is not None:
            request = self._request_factory()
        else:
            request = self._agently.create_request()
        if input is not None:
            request.input(input)
        if info is not None:
            request.info(info)
        request.instruct(instruct)
        request.output(fields, format="json")
        raw = request.start()
        return schema.model_validate(raw)

    async def request_structured_stream(
        self,
        schema: type[BaseModel],
        *,
        fields: dict[str, tuple],
        input: Any = None,
        info: Any = None,
        instruct: str = "",
        on_delta: Callable[[str], Any] | None = None,
    ) -> BaseModel:
        """单次请求内边流式推送增量文本，边产出宿主校验后的结构化结果。

        on_delta 为 async 回调（WS 推送）；模拟模型路径退化为同步单次请求。
        """
        if self._request_factory is not None:
            request = self._request_factory()
            if input is not None:
                request.input(input)
            if info is not None:
                request.info(info)
            request.instruct(instruct)
            request.output(fields, format="json")
            return schema.model_validate(request.start())

        from medsta.errors import AppError, ErrorCode

        request = self._agently.create_request()
        if input is not None:
            request.input(input)
        if info is not None:
            request.info(info)
        request.instruct(instruct)
        request.output(fields, format="json")
        try:
            result = request.get_result()
            async for chunk in result.get_async_generator(type="original"):
                piece = _extract_delta(chunk)
                if piece and on_delta is not None:
                    awaited = on_delta(piece)
                    if hasattr(awaited, "__await__"):
                        await awaited
            data = await result.async_get_data()
        except AppError:
            raise
        except Exception as exc:  # 传输层异常统一分类，避免泄漏密钥
            raise AppError(
                ErrorCode.MODEL_REQUEST_FAILED,
                f"模型请求失败：{type(exc).__name__}",
                hint="检查网络连通性、LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 配置，以及模型服务是否可用",
                detail=str(exc)[:300],
            ) from exc
        return schema.model_validate(data)


def _extract_delta(chunk: Any) -> str:
    """从 OpenAI 兼容 SSE chunk 中提取增量文本（优先推理内容）。"""
    import json

    if not isinstance(chunk, str):
        return ""
    try:
        payload = json.loads(chunk)
        delta = payload["choices"][0]["delta"]
    except (ValueError, KeyError, IndexError, TypeError):
        return ""
    piece = delta.get("reasoning_content") or delta.get("content") or ""
    return str(piece)


def build_gateway(
    config: ProviderConfig | None = None, agently_facade: Any | None = None
) -> ModelGateway:
    """按 provider 配置构建默认网关（真实模型调用）。"""
    return ModelGateway(
        agently_facade=build_settings(config or ProviderConfig.from_env(), agently_facade)
    )
