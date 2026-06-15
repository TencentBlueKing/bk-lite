# Anthropic 兼容运行时统一修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 DeepSeek 的 Anthropic 兼容对话链路，让测试连接与运行时调用复用同一套适配规则，并补齐 thinking + tool choice 兼容。

**Architecture:** 保留原生 Anthropic 供应商走 `ChatAnthropic` / 原生 SDK 路径，为 `vendor_type=deepseek` 且 `protocol_type=anthropic` 新增一层 Anthropic 兼容适配器。运行时路由、测试连接、tool choice 降级都改为读取统一能力模型，避免“测试通过、运行失败”的双轨实现。

**Tech Stack:** Python 3.12、Django、LangChain、Anthropic/OpenAI SDK、pytest

---

## 文件结构

### 新建文件

- `server/apps/opspilot/metis/llm/common/anthropic_capabilities.py`
  - 负责根据 `vendor_type + protocol_type + model` 解析运行时能力。
  - 提供 thinking 模式下 `tool_choice` 兼容降级辅助函数。

- `server/apps/opspilot/metis/llm/common/anthropic_compatible_adapter.py`
  - 负责 Anthropic 兼容模式下的 `base_url` 规范化、headers/payload 构造、同步/异步最小请求发送。
  - 提供一个薄运行时客户端，满足 `LLMClientFactory` 当前 graph 链路需要的最小接口。

### 修改文件

- `server/apps/opspilot/metis/llm/common/llm_client_factory.py:16-241`
  - 改造 `protocol_type=anthropic` 的路由逻辑。
  - 原生 Anthropic 供应商保留原路径，DeepSeek Anthropic 兼容模式切到适配器客户端。

- `server/apps/opspilot/services/model_vendor_sync_service.py:16-140`
  - 让 `test_anthropic_connection()` 复用适配器，不再手写 HTTP 请求。

- `server/apps/opspilot/metis/llm/chain/node.py:2501-2546`
  - 让 thinking + `tool_choice` 兼容逻辑读取统一能力模型，而不是只看 `llm.extra_body`。

- `server/apps/opspilot/tests/react_agent/cases/test_anthropic_protocol.py:1-498`
  - 扩展已有协议测试，覆盖能力解析、适配器委派、运行时路由、tool choice 降级和错误归一。

---

### Task 1: 建立能力模型并锁定回归边界

**Files:**
- Create: `server/apps/opspilot/metis/llm/common/anthropic_capabilities.py`
- Test: `server/apps/opspilot/tests/react_agent/cases/test_anthropic_protocol.py`

- [ ] **Step 1: 先写 failing tests，定义能力模型与 tool choice 降级行为**

```python
from apps.opspilot.metis.llm.common.anthropic_capabilities import (
    AnthropicRuntimeCapabilities,
    build_anthropic_runtime_capabilities,
    normalize_tool_choice_for_capabilities,
)


class TestAnthropicRuntimeCapabilities:
    def test_native_anthropic_vendor_uses_native_sdk(self):
        caps = build_anthropic_runtime_capabilities(
            vendor_type="anthropic",
            protocol_type="anthropic",
            model="claude-3-haiku-20240307",
        )
        assert caps.use_native_anthropic_sdk is True
        assert caps.use_anthropic_compatible_adapter is False

    def test_deepseek_anthropic_vendor_uses_adapter(self):
        caps = build_anthropic_runtime_capabilities(
            vendor_type="deepseek",
            protocol_type="anthropic",
            model="deepseek-v4-flash",
        )
        assert caps.use_native_anthropic_sdk is False
        assert caps.use_anthropic_compatible_adapter is True
        assert caps.thinking_requires_auto_tool_choice is True

    def test_non_anthropic_protocol_returns_default_capabilities(self):
        caps = build_anthropic_runtime_capabilities(
            vendor_type="deepseek",
            protocol_type="openai",
            model="deepseek-v4-flash",
        )
        assert caps.use_native_anthropic_sdk is False
        assert caps.use_anthropic_compatible_adapter is False

    def test_tool_choice_any_downgrades_to_auto_when_thinking_required(self):
        caps = AnthropicRuntimeCapabilities(thinking_requires_auto_tool_choice=True)
        assert normalize_tool_choice_for_capabilities("any", caps) == "auto"

    def test_tool_choice_none_kept_as_is(self):
        caps = AnthropicRuntimeCapabilities(thinking_requires_auto_tool_choice=True)
        assert normalize_tool_choice_for_capabilities("none", caps) == "none"
```

- [ ] **Step 2: 运行测试，确认它先红**

Run:

```powershell
Set-Location D:\app\github\bk-lite\server
uv run pytest apps/opspilot/tests/react_agent/cases/test_anthropic_protocol.py -k "AnthropicRuntimeCapabilities" -v
```

Expected: `ModuleNotFoundError` 或 `ImportError`，因为 `anthropic_capabilities.py` 还不存在。

- [ ] **Step 3: 写最小实现，先把能力模型落地**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class AnthropicRuntimeCapabilities:
    use_native_anthropic_sdk: bool = False
    use_anthropic_compatible_adapter: bool = False
    thinking_requires_auto_tool_choice: bool = False
    supports_direct_messages_api: bool = False
    requires_normalized_base_url: bool = False


def build_anthropic_runtime_capabilities(vendor_type: str, protocol_type: str, model: str) -> AnthropicRuntimeCapabilities:
    if protocol_type != "anthropic":
        return AnthropicRuntimeCapabilities()

    if vendor_type == "anthropic":
        return AnthropicRuntimeCapabilities(
            use_native_anthropic_sdk=True,
            supports_direct_messages_api=True,
            requires_normalized_base_url=True,
        )

    if vendor_type == "deepseek":
        return AnthropicRuntimeCapabilities(
            use_anthropic_compatible_adapter=True,
            thinking_requires_auto_tool_choice=True,
            supports_direct_messages_api=True,
            requires_normalized_base_url=True,
        )

    return AnthropicRuntimeCapabilities(
        supports_direct_messages_api=True,
        requires_normalized_base_url=True,
    )


def normalize_tool_choice_for_capabilities(tool_choice: str, capabilities: AnthropicRuntimeCapabilities) -> str:
    if capabilities.thinking_requires_auto_tool_choice and tool_choice in {"any", "required"}:
        return "auto"
    return tool_choice
```

- [ ] **Step 4: 再跑测试，确认转绿**

Run:

```powershell
Set-Location D:\app\github\bk-lite\server
uv run pytest apps/opspilot/tests/react_agent/cases/test_anthropic_protocol.py -k "AnthropicRuntimeCapabilities" -v
```

Expected: `PASS`

- [ ] **Step 5: 提交这一小步**

```powershell
git add server/apps/opspilot/metis/llm/common/anthropic_capabilities.py server/apps/opspilot/tests/react_agent/cases/test_anthropic_protocol.py
git commit -m "feat(opspilot): add anthropic runtime capabilities"
```

---

### Task 2: 引入 Anthropic 兼容适配器并让测试连接先复用它

**Files:**
- Create: `server/apps/opspilot/metis/llm/common/anthropic_compatible_adapter.py`
- Modify: `server/apps/opspilot/services/model_vendor_sync_service.py:84-121`
- Test: `server/apps/opspilot/tests/react_agent/cases/test_anthropic_protocol.py`

- [ ] **Step 1: 先写 failing tests，锁定 test_connection 统一适配行为**

```python
class TestAnthropicCompatibleAdapter:
    def test_normalize_base_url_appends_messages_endpoint(self):
        from apps.opspilot.metis.llm.common.anthropic_compatible_adapter import normalize_messages_url

        assert normalize_messages_url("https://api.deepseek.com/anthropic") == "https://api.deepseek.com/anthropic/v1/messages"

    def test_build_headers_uses_x_api_key(self):
        from apps.opspilot.metis.llm.common.anthropic_compatible_adapter import build_anthropic_headers

        headers = build_anthropic_headers("sk-key")
        assert headers["x-api-key"] == "sk-key"
        assert headers["anthropic-version"] == "2023-06-01"


class TestAnthropicConnectionDelegation:
    @patch("apps.opspilot.services.model_vendor_sync_service.AnthropicCompatibleAdapter.validate_minimal_connection")
    def test_test_connection_delegates_to_adapter(self, mock_validate):
        ModelVendorSyncService.test_anthropic_connection(
            "https://api.deepseek.com/anthropic",
            "sk-key",
            model="deepseek-v4-flash",
        )
        mock_validate.assert_called_once()
```

- [ ] **Step 2: 运行测试，确认它失败在适配器缺失或未接线**

Run:

```powershell
Set-Location D:\app\github\bk-lite\server
uv run pytest apps/opspilot/tests/react_agent/cases/test_anthropic_protocol.py -k "AnthropicCompatibleAdapter or AnthropicConnectionDelegation" -v
```

Expected: 失败原因应为适配器模块不存在，或 `test_anthropic_connection()` 仍未委派。

- [ ] **Step 3: 写最小实现，先让适配器和服务接起来**

```python
from apps.core.utils.safe_requests import safe_post_llm_endpoint


def normalize_messages_url(api_base: str) -> str:
    normalized = (api_base or "https://api.anthropic.com").rstrip("/")
    return f"{normalized}/v1/messages"


def build_anthropic_headers(api_key: str) -> dict[str, str]:
    return {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }


class AnthropicCompatibleAdapter:
    @classmethod
    def validate_minimal_connection(cls, api_base: str, api_key: str, model: str) -> None:
        response = safe_post_llm_endpoint(
            normalize_messages_url(api_base),
            headers=build_anthropic_headers(api_key),
            json={
                "model": model,
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "hi"}],
            },
            timeout=15,
        )
        return cls.raise_for_error(response)

    @staticmethod
    def raise_for_error(response) -> None:
        if response.status_code == 401:
            raise ValueError("API Key 无效")
        if response.status_code >= 400:
            raise ValueError(f"API 连接失败: {response.text[:200] if response.text else f'HTTP {response.status_code}'}")
```

并把服务改成：

```python
test_model = model or "claude-3-haiku-20240307"
AnthropicCompatibleAdapter.validate_minimal_connection(api_base, api_key, test_model)
```

- [ ] **Step 4: 再跑测试，确认连接链路转绿**

Run:

```powershell
Set-Location D:\app\github\bk-lite\server
uv run pytest apps/opspilot/tests/react_agent/cases/test_anthropic_protocol.py -k "AnthropicCompatibleAdapter or AnthropicConnectionDelegation" -v
```

Expected: `PASS`

- [ ] **Step 5: 提交这一小步**

```powershell
git add server/apps/opspilot/metis/llm/common/anthropic_compatible_adapter.py server/apps/opspilot/services/model_vendor_sync_service.py server/apps/opspilot/tests/react_agent/cases/test_anthropic_protocol.py
git commit -m "fix(opspilot): unify anthropic connection validation"
```

---

### Task 3: 改造 `LLMClientFactory`，让 DeepSeek Anthropic 兼容运行时走适配器

**Files:**
- Modify: `server/apps/opspilot/metis/llm/common/llm_client_factory.py:16-241`
- Modify: `server/apps/opspilot/metis/llm/common/anthropic_compatible_adapter.py`
- Modify: `server/apps/opspilot/tests/react_agent/cases/test_anthropic_protocol.py:40-303`

- [ ] **Step 1: 先写 failing tests，锁定运行时路由**

```python
class TestCreateClientProtocolDispatch:
    @patch("apps.opspilot.metis.llm.common.llm_client_factory.AnthropicCompatibleChatClient")
    @patch("apps.opspilot.metis.llm.common.llm_client_factory.ChatAnthropic")
    def test_deepseek_anthropic_uses_adapter_client(self, mock_chat_anthropic, mock_adapter):
        request = BasicLLMRequest(
            protocol_type="anthropic",
            openai_api_key="sk-key",
            openai_api_base="https://api.deepseek.com/anthropic",
            model="deepseek-v4-flash",
            extra_config={"vendor_type": "deepseek", "show_think": True},
        )
        LLMClientFactory.create_client(request)
        mock_adapter.assert_called_once()
        mock_chat_anthropic.assert_not_called()

    @patch("apps.opspilot.metis.llm.common.llm_client_factory.ChatAnthropic")
    def test_native_anthropic_still_uses_chat_anthropic(self, mock_chat_anthropic):
        request = BasicLLMRequest(
            protocol_type="anthropic",
            openai_api_key="sk-ant-key",
            openai_api_base="https://api.anthropic.com",
            model="claude-3-haiku-20240307",
            extra_config={"vendor_type": "anthropic"},
        )
        LLMClientFactory.create_client(request)
        mock_chat_anthropic.assert_called_once()
```

- [ ] **Step 2: 运行测试，确认它先红**

Run:

```powershell
Set-Location D:\app\github\bk-lite\server
uv run pytest apps/opspilot/tests/react_agent/cases/test_anthropic_protocol.py -k "deepseek_anthropic_uses_adapter_client or native_anthropic_still_uses_chat_anthropic" -v
```

Expected: `AnthropicCompatibleChatClient` 不存在，或 DeepSeek 仍错误走 `ChatAnthropic`。

- [ ] **Step 3: 写最小实现，接通工厂路由**

```python
class AnthropicCompatibleChatClient:
    def __init__(self, request: BasicLLMRequest, disable_stream: bool = False):
        self.request = request
        self.disable_stream = disable_stream
        self.runtime_capabilities = build_anthropic_runtime_capabilities(
            vendor_type=(request.extra_config or {}).get("vendor_type", ""),
            protocol_type=request.protocol_type,
            model=request.model,
        )

    def bind_tools(self, tools, **kwargs):
        self.bound_tools = tools
        self.bound_kwargs = kwargs
        return self

    async def ainvoke(self, messages):
        raise NotImplementedError("在本任务先完成路由，下一任务再补完整调用")
```

工厂路由改成：

```python
vendor_type = (request.extra_config or {}).get("vendor_type", "")
capabilities = build_anthropic_runtime_capabilities(vendor_type, request.protocol_type, request.model)
if capabilities.use_anthropic_compatible_adapter:
    llm = AnthropicCompatibleChatClient(request, disable_stream=disable_stream)
elif request.protocol_type == "anthropic":
    llm = LLMClientFactory._create_anthropic_client(request, disable_stream)
else:
    llm = LLMClientFactory._create_openai_client(request, disable_stream)
```

- [ ] **Step 4: 再跑测试，确认路由转绿**

Run:

```powershell
Set-Location D:\app\github\bk-lite\server
uv run pytest apps/opspilot/tests/react_agent/cases/test_anthropic_protocol.py -k "deepseek_anthropic_uses_adapter_client or native_anthropic_still_uses_chat_anthropic" -v
```

Expected: `PASS`

- [ ] **Step 5: 提交这一小步**

```powershell
git add server/apps/opspilot/metis/llm/common/llm_client_factory.py server/apps/opspilot/metis/llm/common/anthropic_compatible_adapter.py server/apps/opspilot/tests/react_agent/cases/test_anthropic_protocol.py
git commit -m "fix(opspilot): route deepseek anthropic runtime through adapter"
```

---

### Task 4: 补齐适配器运行时调用与错误归一

**Files:**
- Modify: `server/apps/opspilot/metis/llm/common/anthropic_compatible_adapter.py`
- Modify: `server/apps/opspilot/metis/llm/common/llm_client_factory.py:149-241`
- Modify: `server/apps/opspilot/tests/react_agent/cases/test_anthropic_protocol.py:206-498`

- [ ] **Step 1: 先写 failing tests，锁定最小运行时调用与鉴权错误归一**

```python
class TestAnthropicCompatibleRuntimeInvoke:
    @patch("apps.opspilot.metis.llm.common.anthropic_compatible_adapter.safe_post_llm_endpoint")
    def test_runtime_client_builds_expected_payload(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"content": [{"type": "text", "text": "ok"}]})
        request = BasicLLMRequest(
            protocol_type="anthropic",
            openai_api_key="sk-key",
            openai_api_base="https://api.deepseek.com/anthropic",
            model="deepseek-v4-flash",
            temperature=0.1,
            extra_config={"vendor_type": "deepseek", "show_think": True},
        )
        client = AnthropicCompatibleChatClient(request)
        client.invoke_messages([{"role": "user", "content": "hi"}])
        call_json = mock_post.call_args[1]["json"]
        assert call_json["model"] == "deepseek-v4-flash"
        assert call_json["messages"] == [{"role": "user", "content": "hi"}]

    @patch("apps.opspilot.metis.llm.common.anthropic_compatible_adapter.safe_post_llm_endpoint")
    def test_runtime_client_maps_401_to_value_error(self, mock_post):
        mock_post.return_value = MagicMock(status_code=401, text="bad key")
        request = BasicLLMRequest(
            protocol_type="anthropic",
            openai_api_key="bad-key",
            openai_api_base="https://api.deepseek.com/anthropic",
            model="deepseek-v4-flash",
            extra_config={"vendor_type": "deepseek"},
        )
        client = AnthropicCompatibleChatClient(request)
        with pytest.raises(ValueError, match="API Key 无效"):
            client.invoke_messages([{"role": "user", "content": "hi"}])
```

- [ ] **Step 2: 运行测试，确认它先红**

Run:

```powershell
Set-Location D:\app\github\bk-lite\server
uv run pytest apps/opspilot/tests/react_agent/cases/test_anthropic_protocol.py -k "AnthropicCompatibleRuntimeInvoke" -v
```

Expected: 因 `invoke_messages()` 未实现或错误未归一而失败。

- [ ] **Step 3: 写最小实现，补齐适配器最小运行时调用**

```python
def build_messages_payload(model: str, messages: list, temperature: float, thinking: dict | None = None) -> dict:
    payload = {
        "model": model,
        "max_tokens": 4096,
        "messages": messages,
        "temperature": temperature,
    }
    if thinking:
        payload["thinking"] = thinking
    return payload


class AnthropicCompatibleChatClient:
    def invoke_messages(self, messages: list):
        thinking_cfg = {"type": "enabled"} if (self.request.extra_config or {}).get("show_think", True) else {"type": "disabled"}
        response = safe_post_llm_endpoint(
            normalize_messages_url(self.request.openai_api_base),
            headers=build_anthropic_headers(self.request.openai_api_key),
            json=build_messages_payload(self.request.model, messages, self.request.temperature, thinking=thinking_cfg),
            timeout=60,
        )
        AnthropicCompatibleAdapter.raise_for_error(response)
        return response
```

- [ ] **Step 4: 再跑测试，确认最小运行时调用转绿**

Run:

```powershell
Set-Location D:\app\github\bk-lite\server
uv run pytest apps/opspilot/tests/react_agent/cases/test_anthropic_protocol.py -k "AnthropicCompatibleRuntimeInvoke" -v
```

Expected: `PASS`

- [ ] **Step 5: 提交这一小步**

```powershell
git add server/apps/opspilot/metis/llm/common/anthropic_compatible_adapter.py server/apps/opspilot/metis/llm/common/llm_client_factory.py server/apps/opspilot/tests/react_agent/cases/test_anthropic_protocol.py
git commit -m "fix(opspilot): normalize anthropic-compatible runtime invoke"
```

---

### Task 5: 让 `node.py` 基于能力模型降级 tool choice，并跑完整回归

**Files:**
- Modify: `server/apps/opspilot/metis/llm/chain/node.py:2503-2546`
- Modify: `server/apps/opspilot/tests/react_agent/cases/test_anthropic_protocol.py`

- [ ] **Step 1: 先写 failing test，锁定 thinking 模式下降级行为**

```python
class TestThinkingToolChoiceCompatibility:
    def test_capability_driven_tool_choice_downgrade(self):
        caps = AnthropicRuntimeCapabilities(thinking_requires_auto_tool_choice=True)
        bind_kwargs = {"tool_choice": "any"}
        bind_kwargs["tool_choice"] = normalize_tool_choice_for_capabilities(bind_kwargs["tool_choice"], caps)
        assert bind_kwargs["tool_choice"] == "auto"
```

- [ ] **Step 2: 跑测试，确认当前逻辑还没接线**

Run:

```powershell
Set-Location D:\app\github\bk-lite\server
uv run pytest apps/opspilot/tests/react_agent/cases/test_anthropic_protocol.py -k "ThinkingToolChoiceCompatibility" -v
```

Expected: 测试先红，或者 helper 通过但 `node.py` 尚未改用它；此时继续补一条集成断言：

```python
assert normalize_tool_choice_for_capabilities("any", caps) == "auto"
```

并在实现后通过针对性回归确认 `node.py` 已接线。

- [ ] **Step 3: 写最小实现，把 `node.py` 的降级逻辑改为读取能力标记**

```python
runtime_capabilities = getattr(llm, "runtime_capabilities", None)
if bind_kwargs.get("tool_choice") in ("any", "required") and runtime_capabilities is not None:
    bind_kwargs["tool_choice"] = normalize_tool_choice_for_capabilities(
        bind_kwargs["tool_choice"],
        runtime_capabilities,
    )
elif bind_kwargs.get("tool_choice") in ("any", "required"):
    extra_body = getattr(llm, "extra_body", None) or {}
    deepseek_thinking = extra_body.get("thinking", {}).get("type") == "enabled"
    qwen_thinking = extra_body.get("enable_thinking") is True
    if deepseek_thinking or qwen_thinking:
        bind_kwargs["tool_choice"] = "auto"
```

- [ ] **Step 4: 跑本次回归相关测试并确认全绿**

Run:

```powershell
Set-Location D:\app\github\bk-lite\server
uv run pytest apps/opspilot/tests/react_agent/cases/test_anthropic_protocol.py -v
```

Expected: `PASS`

再跑一次更接近模块门禁的组合：

```powershell
Set-Location D:\app\github\bk-lite\server
uv run pytest apps/opspilot/tests/react_agent/cases/test_anthropic_protocol.py apps/opspilot/tests/workflow/cases/test_ssrf_high_risk_components.py -v
```

Expected: `PASS`

- [ ] **Step 5: 提交最终实现**

```powershell
git add server/apps/opspilot/metis/llm/chain/node.py server/apps/opspilot/tests/react_agent/cases/test_anthropic_protocol.py
git commit -m "fix(opspilot): align anthropic-compatible runtime behavior"
```

---

## 实施顺序说明

1. 先锁定能力模型与降级规则，避免后面继续用 `extra_body` 写死兼容逻辑。
2. 再让测试连接先复用适配器，先消除“测试链路和运行时链路不同构”的根问题。
3. 然后改运行时工厂路由，把 DeepSeek Anthropic 兼容模式切出 `ChatAnthropic`。
4. 最后接上 `node.py`，把 thinking + tool choice 的兼容点补齐。

这样每一步都能独立提交、独立回滚、独立验证。

## 自检结果

### Spec 覆盖检查

- “测试连接与运行时复用同一套适配规则” -> Task 2、Task 3、Task 4
- “恢复 DeepSeek Anthropic 兼容真实对话” -> Task 3、Task 4、Task 5
- “保留原生 Anthropic 支持” -> Task 1、Task 3
- “集中管理 thinking / tool choice / endpoint 规范化能力判断” -> Task 1、Task 2、Task 5
- “补齐回归测试” -> Task 1 到 Task 5

### 占位符检查

- 无 `TODO`、`TBD`、`implement later`
- 每个代码步骤都给了明确代码块
- 每个验证步骤都给了明确命令与预期结果

### 命名一致性检查

- 能力模型统一使用 `AnthropicRuntimeCapabilities`
- 能力解析统一使用 `build_anthropic_runtime_capabilities`
- tool choice 降级统一使用 `normalize_tool_choice_for_capabilities`
- 兼容运行时客户端统一使用 `AnthropicCompatibleChatClient`
