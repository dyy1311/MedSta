"""001 后端骨架：模型配置与结构化请求网关测试；007 真实接入回归断言。"""
from pydantic import BaseModel

from medsta.config import (
    _PROVIDER_NAMESPACE,
    ModelGateway,
    ProviderConfig,
    build_settings,
)


def test_settings_use_provider_config() -> None:
    """B4: build_settings 使用显式 provider 配置（OpenAI 兼容 base_url/api_key/model）"""
    config = ProviderConfig(
        base_url="https://api.test/v1", api_key="key-1", model="test-model"
    )
    facade = build_settings(config)
    assert facade.settings.get(f"{_PROVIDER_NAMESPACE}.base_url") == "https://api.test/v1"
    assert facade.settings.get(f"{_PROVIDER_NAMESPACE}.model") == "test-model"
    assert facade.settings.get(f"{_PROVIDER_NAMESPACE}.model_type") == "chat"


def test_settings_timeout_has_all_four_params() -> None:
    """007: timeout 必须含 connect/read/write/pool 四参数（httpx 要求）"""
    config = ProviderConfig(
        base_url="https://api.test/v1", api_key="key-1", model="test-model"
    )
    facade = build_settings(config)
    timeout = facade.settings.get(f"{_PROVIDER_NAMESPACE}.timeout")
    assert set(timeout.keys()) == {"connect", "read", "write", "pool"}
    assert timeout["read"] == config.timeout == timeout["write"]


def test_settings_merge_preserves_plugin_defaults() -> None:
    """007: 逐键合并不得替换插件命名空间，path_mapping/content_mapping 等默认值保留"""
    config = ProviderConfig(
        base_url="https://api.test/v1", api_key="key-1", model="test-model"
    )
    facade = build_settings(config)
    path_mapping = facade.settings.get(f"{_PROVIDER_NAMESPACE}.path_mapping")
    content_mapping = facade.settings.get(f"{_PROVIDER_NAMESPACE}.content_mapping")
    assert isinstance(path_mapping, dict) and path_mapping.get("chat") == "/chat/completions"
    assert isinstance(content_mapping, dict)
    assert content_mapping.get("role") and content_mapping.get("delta")


class _FakeRequest:
    """模拟模型传输边界：记录契约四段式，返回预置 payload。"""

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.fields: dict | None = None

    def input(self, value) -> "_FakeRequest":
        return self

    def info(self, value) -> "_FakeRequest":
        return self

    def instruct(self, value) -> "_FakeRequest":
        return self

    def output(self, fields, **kwargs) -> "_FakeRequest":
        self.fields = fields
        return self

    def start(self) -> dict:
        return self._payload


def test_structured_request_with_mock_model() -> None:
    """B5: 模拟模型下，request_structured 返回符合声明 output 契约的校验结果"""

    class Echo(BaseModel):
        echo: str

    fake = _FakeRequest({"echo": "hello"})
    gateway = ModelGateway(agently_facade=object(), request_factory=lambda: fake)
    result = gateway.request_structured(
        Echo, input="hi", instruct="原样返回输入文本", fields={"echo": (str, "与输入相同的文本")}
    )
    assert isinstance(result, Echo)
    assert result.echo == "hello"
    # 四段式契约被传递到请求链
    assert fake.fields is not None and "echo" in fake.fields


def test_from_env_loads_dotenv(monkeypatch, tmp_path) -> None:
    """007: 未手动 export 时，from_env 自动加载项目根 .env；不覆盖已显式 export 的变量"""
    import medsta.config as config_module

    env_file = tmp_path / ".env"
    env_file.write_text(
        "LLM_BASE_URL=https://api.fromfile/v1\n"
        "LLM_API_KEY=key-file\n"
        "LLM_MODEL=file-model\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setattr(config_module, "_PROJECT_ROOT", tmp_path)

    config = config_module.ProviderConfig.from_env()
    assert config.base_url == "https://api.fromfile/v1"
    assert config.api_key == "key-file"
    assert config.model == "file-model"

    # 显式 export 优先于 .env（override=False）
    monkeypatch.setenv("LLM_MODEL", "exported-model")
    config = config_module.ProviderConfig.from_env()
    assert config.model == "exported-model"
    assert config.base_url == "https://api.fromfile/v1"
