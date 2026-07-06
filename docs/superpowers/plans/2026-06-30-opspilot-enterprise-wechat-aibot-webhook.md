# OpsPilot 企微智能机器人短连接入口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 OpsPilot workflow 中新增 `enterprise_wechat_aibot` 入口节点，支持企业微信智能机器人短连接 URL 回调、文本消息异步执行 workflow，并通过 `response_url` 主动回复 markdown。

**Architecture:** 后端新增一个独立的智能机器人短连接通道，复用现有外部渠道的快速 ACK、Celery 异步执行和两阶段 `msgid` 去重模式；短连接加解密单独封装，避免混用现有企业微信应用 XML 回调工具。前端新增一个入口节点和配置面板，默认写入 `connectionMode=webhook`，保留 `websocket` 凭据结构但不展示、不校验、不执行。

**Tech Stack:** Python 3.12、Django 4.2、Celery、pytest、Next.js 16、React 19、TypeScript、Ant Design、pnpm。

---

## 工作区约束

本次实现只允许在以下 worktree 中进行：

```powershell
D:\app\github\bk-lite\.claude\worktrees\opspilot-wechat-aibot-webhook
```

当前分支：

```powershell
feat/opspilot-wechat-aibot-webhook
```

主工作区 `D:\app\github\bk-lite` 存在与本需求无关的用户改动：

```text
 M .husky/pre-commit
?? server/apps/opspilot/tests/test_agent_execute_timeout.py
```

实现过程中不读取为“待处理变更”，不回滚，不移动，不提交这些文件。

## 文件职责图

### 后端

- Create: `server/apps/opspilot/utils/enterprise_wechat_aibot_crypto.py`
  - 企业微信智能机器人短连接 JSON 加解密适配器。
  - 对外提供 `verify_url(...)` 和 `decrypt_callback(...)`。
- Create: `server/apps/opspilot/utils/enterprise_wechat_aibot_chat_flow_utils.py`
  - 智能机器人短连接入口工具类。
  - 负责节点配置解析、GET URL 校验、POST 解密、消息清洗、去重、Celery 投递和主动回复。
- Modify: `server/apps/opspilot/enum.py`
  - 新增 `WorkFlowExecuteType.ENTERPRISE_WECHAT_AIBOT`。
- Modify: `server/apps/opspilot/views.py`
  - 新增 `execute_chat_flow_enterprise_wechat_aibot(request, bot_id)`。
- Modify: `server/apps/opspilot/urls.py`
  - 新增短连接回调路由。
- Modify: `server/apps/opspilot/tasks.py`
  - 新增 `process_enterprise_wechat_aibot_message` Celery 任务。
- Modify: `server/apps/opspilot/utils/chat_flow_utils/engine/node_registry.py`
  - 注册 `enterprise_wechat_aibot` 为入口节点。
- Create: `server/apps/opspilot/tests/test_enterprise_wechat_aibot_crypto.py`
  - 覆盖 URL 校验和 JSON 回调解密。
- Create: `server/apps/opspilot/tests/test_enterprise_wechat_aibot_views.py`
  - 覆盖 GET/POST 视图行为、重复消息、模式未启用、aibotid 不匹配。
- Create: `server/apps/opspilot/tests/test_enterprise_wechat_aibot_tasks.py`
  - 覆盖 Celery 任务执行、主动回复、失败重试和去重状态。

### 前端

- Modify: `web/src/app/opspilot/constants/chatflow.ts`
  - 新增节点元数据、触发器列表、默认配置。
- Modify: `web/src/app/opspilot/components/chatflow/types.ts`
  - 扩展 `NodeType`。
- Modify: `web/src/app/opspilot/components/chatflow/nodes/index.tsx`
  - 新增节点展示组件并导出。
- Modify: `web/src/app/opspilot/components/chatflow/ChatflowEditor.tsx`
  - 注册 React Flow node type 和无输入节点类型。
- Modify: `web/src/app/opspilot/components/chatflow/hooks/useNodeDrop.ts`
  - 新增拖拽落点标签。
- Create: `web/src/app/opspilot/components/chatflow/components/nodeConfigs/EnterpriseWechatAibotNodeConfig.tsx`
  - 新增短连接配置表单。
- Modify: `web/src/app/opspilot/components/chatflow/components/nodeConfigs/types.ts`
  - 为新配置组件复用节点配置 props。
- Modify: `web/src/app/opspilot/components/chatflow/components/nodeConfigs/index.ts`
  - 导出新配置组件。
- Modify: `web/src/app/opspilot/components/chatflow/NodeConfigForm.tsx`
  - 将新节点映射到配置组件。
- Modify: `web/src/app/opspilot/locales/zh.json`
  - 新增中文文案。
- Modify: `web/src/app/opspilot/locales/en.json`
  - 新增英文文案。

## Task 0: 校验隔离工作区

**Files:**
- No code changes.

- [ ] **Step 1: 确认当前位置是指定 worktree**

Run:

```powershell
pwd
git branch --show-current
git status --short
```

Expected:

```text
Path
----
D:\app\github\bk-lite\.claude\worktrees\opspilot-wechat-aibot-webhook

feat/opspilot-wechat-aibot-webhook
```

`git status --short` 允许仅出现本计划文件或后续任务产生的本需求文件，不允许出现主工作区的 `.husky/pre-commit` 和 `test_agent_execute_timeout.py`。

- [ ] **Step 2: 确认设计规格在当前分支可读**

Run:

```powershell
Get-Content -Raw docs\superpowers\specs\2026-06-30-opspilot-enterprise-wechat-aibot-webhook-design.md | Select-String "状态：设计已确认"
```

Expected:

```text
- 状态：设计已确认，待实现计划
```

## Task 1: 后端加解密适配器

**Files:**
- Create: `server/apps/opspilot/tests/test_enterprise_wechat_aibot_crypto.py`
- Create: `server/apps/opspilot/utils/enterprise_wechat_aibot_crypto.py`

- [ ] **Step 1: 写 URL 校验和回调解密失败测试**

Create `server/apps/opspilot/tests/test_enterprise_wechat_aibot_crypto.py`:

```python
import base64
import json
import struct

import pytest

from apps.opspilot.utils.enterprise_wechat_aibot_crypto import (
    EnterpriseWechatAibotCrypto,
    EnterpriseWechatAibotCryptoError,
)


def _encoding_aes_key() -> str:
    return base64.b64encode(b"0" * 32).decode("utf-8").rstrip("=")


def test_decrypt_callback_rejects_missing_encrypt():
    crypto = EnterpriseWechatAibotCrypto(token="token", encoding_aes_key=_encoding_aes_key())

    with pytest.raises(EnterpriseWechatAibotCryptoError, match="encrypt"):
        crypto.decrypt_callback(
            msg_signature="invalid",
            timestamp="1",
            nonce="nonce",
            body=json.dumps({"msgtype": "text"}).encode("utf-8"),
        )


def test_verify_url_rejects_invalid_signature():
    crypto = EnterpriseWechatAibotCrypto(token="token", encoding_aes_key=_encoding_aes_key())

    with pytest.raises(EnterpriseWechatAibotCryptoError, match="signature"):
        crypto.verify_url(
            msg_signature="invalid",
            timestamp="1",
            nonce="nonce",
            echostr="encrypted",
        )
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
cd server
uv run pytest apps/opspilot/tests/test_enterprise_wechat_aibot_crypto.py -q
```

Expected: FAIL，错误中包含 `ModuleNotFoundError` 或无法导入 `EnterpriseWechatAibotCrypto`。

- [ ] **Step 3: 实现加解密适配器骨架和签名校验**

Create `server/apps/opspilot/utils/enterprise_wechat_aibot_crypto.py`:

```python
import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class EnterpriseWechatAibotCryptoError(ValueError):
    pass


@dataclass(frozen=True)
class EnterpriseWechatAibotCrypto:
    token: str
    encoding_aes_key: str

    def verify_url(self, msg_signature: str, timestamp: str, nonce: str, echostr: str) -> str:
        if not self._signature_matches(msg_signature, timestamp, nonce, echostr):
            raise EnterpriseWechatAibotCryptoError("invalid signature")
        return self._decrypt(echostr)

    def decrypt_callback(self, msg_signature: str, timestamp: str, nonce: str, body: bytes) -> dict[str, Any]:
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EnterpriseWechatAibotCryptoError("invalid json body") from exc

        encrypted = payload.get("encrypt")
        if not isinstance(encrypted, str) or not encrypted:
            raise EnterpriseWechatAibotCryptoError("missing encrypt")
        if not self._signature_matches(msg_signature, timestamp, nonce, encrypted):
            raise EnterpriseWechatAibotCryptoError("invalid signature")

        try:
            return json.loads(self._decrypt(encrypted))
        except json.JSONDecodeError as exc:
            raise EnterpriseWechatAibotCryptoError("invalid decrypted json") from exc

    def _signature_matches(self, msg_signature: str, timestamp: str, nonce: str, encrypted: str) -> bool:
        raw = "".join(sorted([self.token, timestamp, nonce, encrypted]))
        expected = hashlib.sha1(raw.encode("utf-8")).hexdigest()
        return expected == msg_signature

    def _aes_key(self) -> bytes:
        try:
            return base64.b64decode(f"{self.encoding_aes_key}=")
        except Exception as exc:
            raise EnterpriseWechatAibotCryptoError("invalid encoding aes key") from exc

    def _decrypt(self, encrypted: str) -> str:
        try:
            key = self._aes_key()
            cipher = Cipher(algorithms.AES(key), modes.CBC(key[:16]))
            decryptor = cipher.decryptor()
            plain = decryptor.update(base64.b64decode(encrypted)) + decryptor.finalize()
            plain = self._pkcs7_unpad(plain)
            content_length = int.from_bytes(plain[16:20], "big")
            content = plain[20 : 20 + content_length]
            return content.decode("utf-8")
        except EnterpriseWechatAibotCryptoError:
            raise
        except Exception as exc:
            raise EnterpriseWechatAibotCryptoError("decrypt failed") from exc

    @staticmethod
    def _pkcs7_unpad(value: bytes) -> bytes:
        if not value:
            raise EnterpriseWechatAibotCryptoError("empty plaintext")
        pad = value[-1]
        if pad < 1 or pad > 32:
            raise EnterpriseWechatAibotCryptoError("invalid padding")
        return value[:-pad]
```

- [ ] **Step 4: 补成功路径测试**

Append to `server/apps/opspilot/tests/test_enterprise_wechat_aibot_crypto.py`:

```python
import hashlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def _signature(token: str, timestamp: str, nonce: str, encrypted: str) -> str:
    raw = "".join(sorted([token, timestamp, nonce, encrypted]))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _encrypt_json(encoding_aes_key: str, payload: dict) -> str:
    key = base64.b64decode(f"{encoding_aes_key}=")
    content = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    plain = b"1" * 16 + struct.pack("!I", len(content)) + content
    pad = 32 - (len(plain) % 32)
    plain = plain + bytes([pad]) * pad
    cipher = Cipher(algorithms.AES(key), modes.CBC(key[:16]))
    encryptor = cipher.encryptor()
    return base64.b64encode(encryptor.update(plain) + encryptor.finalize()).decode("utf-8")


def test_verify_url_decrypts_echostr():
    token = "token"
    timestamp = "1"
    nonce = "nonce"
    encoding_aes_key = _encoding_aes_key()
    encrypted = _encrypt_json(encoding_aes_key, {"ok": True})
    crypto = EnterpriseWechatAibotCrypto(token=token, encoding_aes_key=encoding_aes_key)

    result = crypto.verify_url(_signature(token, timestamp, nonce, encrypted), timestamp, nonce, encrypted)

    assert result == '{"ok":true}'


def test_decrypt_callback_returns_message_dict():
    token = "token"
    timestamp = "1"
    nonce = "nonce"
    encoding_aes_key = _encoding_aes_key()
    message = {"msgid": "m1", "msgtype": "text", "text": {"content": "hello"}}
    encrypted = _encrypt_json(encoding_aes_key, message)
    crypto = EnterpriseWechatAibotCrypto(token=token, encoding_aes_key=encoding_aes_key)

    result = crypto.decrypt_callback(
        msg_signature=_signature(token, timestamp, nonce, encrypted),
        timestamp=timestamp,
        nonce=nonce,
        body=json.dumps({"encrypt": encrypted}).encode("utf-8"),
    )

    assert result == message
```

- [ ] **Step 5: 运行加解密测试**

Run:

```powershell
cd server
uv run pytest apps/opspilot/tests/test_enterprise_wechat_aibot_crypto.py -q
```

Expected:

```text
4 passed
```

- [ ] **Step 6: 提交加解密适配器**

Run:

```powershell
git add server/apps/opspilot/tests/test_enterprise_wechat_aibot_crypto.py server/apps/opspilot/utils/enterprise_wechat_aibot_crypto.py
git commit -m "feat: 添加企微智能机器人短连接加解密"
```

## Task 2: 后端入口工具类

**Files:**
- Create: `server/apps/opspilot/tests/test_enterprise_wechat_aibot_views.py`
- Create: `server/apps/opspilot/utils/enterprise_wechat_aibot_chat_flow_utils.py`

- [ ] **Step 1: 写工具类纯函数测试**

Create `server/apps/opspilot/tests/test_enterprise_wechat_aibot_views.py` with initial utility tests:

```python
from unittest.mock import ANY, Mock, patch

import pytest

from apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils import EnterpriseWechatAibotChatFlowUtils


def test_clean_text_message_removes_leading_robot_mention():
    result = EnterpriseWechatAibotChatFlowUtils.clean_text_message("@运维机器人   查询 CPU")

    assert result == "查询 CPU"


def test_clean_text_message_keeps_regular_text():
    result = EnterpriseWechatAibotChatFlowUtils.clean_text_message("查询 CPU")

    assert result == "查询 CPU"


def test_build_flow_input_uses_chatid_as_session_id():
    message = {
        "msgid": "m1",
        "aibotid": "bot-a",
        "chatid": "chat-1",
        "from": {"userid": "user-1"},
        "response_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=abc",
        "msgtype": "text",
        "text": {"content": "查询 CPU"},
    }

    result = EnterpriseWechatAibotChatFlowUtils.build_flow_input(
        bot_id=10,
        node_id="node-1",
        message=message,
        clean_text="查询 CPU",
    )

    assert result == {
        "last_message": "查询 CPU",
        "user_id": "user-1",
        "bot_id": 10,
        "node_id": "node-1",
        "channel": "enterprise_wechat_aibot",
        "is_third_party": True,
        "session_id": "chat-1",
        "response_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=abc",
    }
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
cd server
uv run pytest apps/opspilot/tests/test_enterprise_wechat_aibot_views.py -q
```

Expected: FAIL，错误中包含 `ModuleNotFoundError` 或无法导入 `EnterpriseWechatAibotChatFlowUtils`。

- [ ] **Step 3: 实现工具类纯函数和基础属性**

Create `server/apps/opspilot/utils/enterprise_wechat_aibot_chat_flow_utils.py`:

```python
import logging
import re
from typing import Any

import requests
from django.http import HttpRequest, HttpResponse

from apps.opspilot.utils.base_chat_flow_utils import BaseChatFlowUtils
from apps.opspilot.utils.enterprise_wechat_aibot_crypto import (
    EnterpriseWechatAibotCrypto,
    EnterpriseWechatAibotCryptoError,
)

logger = logging.getLogger(__name__)


class EnterpriseWechatAibotChatFlowUtils(BaseChatFlowUtils):
    channel_name = "企微智能机器人"
    channel_code = "enterprise_wechat_aibot"
    cache_key_prefix = "enterprise_wechat_aibot_msg"

    @staticmethod
    def clean_text_message(content: str) -> str:
        return re.sub(r"^@\S+\s*", "", content or "").strip()

    @staticmethod
    def build_flow_input(bot_id: int, node_id: str, message: dict[str, Any], clean_text: str) -> dict[str, Any]:
        sender_id = (message.get("from") or {}).get("userid") or ""
        session_id = message.get("chatid") or sender_id
        return {
            "last_message": clean_text,
            "user_id": sender_id,
            "bot_id": bot_id,
            "node_id": node_id,
            "channel": EnterpriseWechatAibotChatFlowUtils.channel_code,
            "is_third_party": True,
            "session_id": session_id,
            "response_url": message.get("response_url") or "",
        }

    @classmethod
    def get_aibot_node_config(cls, workflow) -> tuple[str, dict[str, Any]] | tuple[None, None]:
        for node in workflow.graph.get("nodes", []):
            if node.get("type") == cls.channel_code:
                config = (node.get("data") or {}).get("config") or {}
                return node.get("id"), config
        return None, None

    @classmethod
    def get_webhook_config(cls, config: dict[str, Any]) -> dict[str, Any] | None:
        if config.get("connectionMode", "webhook") != "webhook":
            return None
        webhook = config.get("webhook") or {}
        if not webhook.get("token") or not webhook.get("encodingAESKey"):
            return None
        return webhook

    @classmethod
    def handle_url_verification(cls, request: HttpRequest, config: dict[str, Any]) -> HttpResponse:
        webhook = cls.get_webhook_config(config)
        if webhook is None:
            return HttpResponse("fail", status=400)
        crypto = EnterpriseWechatAibotCrypto(
            token=webhook["token"],
            encoding_aes_key=webhook["encodingAESKey"],
        )
        try:
            plaintext = crypto.verify_url(
                msg_signature=request.GET.get("msg_signature", ""),
                timestamp=request.GET.get("timestamp", ""),
                nonce=request.GET.get("nonce", ""),
                echostr=request.GET.get("echostr", ""),
            )
        except EnterpriseWechatAibotCryptoError:
            logger.warning("企微智能机器人 URL 校验失败", exc_info=True)
            return HttpResponse("fail", status=400)
        return HttpResponse(plaintext, content_type="text/plain")

    @classmethod
    def send_markdown_reply(cls, response_url: str, content: str) -> None:
        if not response_url:
            return
        final_content = cls.truncate_markdown(content or "处理完成，但未产生可展示内容")
        response = requests.post(
            response_url,
            json={"msgtype": "markdown", "markdown": {"content": final_content}},
            timeout=10,
        )
        response.raise_for_status()

    @staticmethod
    def truncate_markdown(content: str) -> str:
        raw = content.encode("utf-8")
        if len(raw) <= 20480:
            return content
        suffix = "\n\n内容过长，已截断"
        limit = 20480 - len(suffix.encode("utf-8"))
        truncated = raw[:limit].decode("utf-8", errors="ignore")
        return f"{truncated}{suffix}"
```

- [ ] **Step 4: 运行工具类测试**

Run:

```powershell
cd server
uv run pytest apps/opspilot/tests/test_enterprise_wechat_aibot_views.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 5: 提交工具类基础能力**

Run:

```powershell
git add server/apps/opspilot/tests/test_enterprise_wechat_aibot_views.py server/apps/opspilot/utils/enterprise_wechat_aibot_chat_flow_utils.py
git commit -m "feat: 添加企微智能机器人入口工具类"
```

## Task 3: 后端视图、URL、枚举和节点注册

**Files:**
- Modify: `server/apps/opspilot/enum.py`
- Modify: `server/apps/opspilot/views.py`
- Modify: `server/apps/opspilot/urls.py`
- Modify: `server/apps/opspilot/utils/chat_flow_utils/engine/node_registry.py`
- Modify: `server/apps/opspilot/utils/enterprise_wechat_aibot_chat_flow_utils.py`
- Modify: `server/apps/opspilot/tests/test_enterprise_wechat_aibot_views.py`

- [ ] **Step 1: 补视图行为测试**

Append to `server/apps/opspilot/tests/test_enterprise_wechat_aibot_views.py`:

```python
from django.test import RequestFactory


@pytest.fixture
def request_factory():
    return RequestFactory()


def test_enterprise_wechat_aibot_get_delegates_to_url_verification(request_factory):
    from apps.opspilot.views import execute_chat_flow_enterprise_wechat_aibot

    request = request_factory.get(
        "/api/opspilot/bot_mgmt/execute_chat_flow_enterprise_wechat_aibot/1/",
        {"msg_signature": "s", "timestamp": "1", "nonce": "n", "echostr": "e"},
    )

    with patch(
        "apps.opspilot.views.EnterpriseWechatAibotChatFlowUtils.handle_request",
        return_value=Mock(status_code=200, content=b"ok"),
    ) as mocked:
        response = execute_chat_flow_enterprise_wechat_aibot(request, 1)

    assert response.status_code == 200
    assert response.content == b"ok"
    mocked.assert_called_once_with(request, 1)


def test_enterprise_wechat_aibot_post_delegates_to_handler(request_factory):
    from apps.opspilot.views import execute_chat_flow_enterprise_wechat_aibot

    request = request_factory.post(
        "/api/opspilot/bot_mgmt/execute_chat_flow_enterprise_wechat_aibot/1/",
        data=b'{"encrypt":"abc"}',
        content_type="application/json",
        QUERY_STRING="msg_signature=s&timestamp=1&nonce=n",
    )

    with patch(
        "apps.opspilot.views.EnterpriseWechatAibotChatFlowUtils.handle_request",
        return_value=Mock(status_code=200, content=b"success"),
    ) as mocked:
        response = execute_chat_flow_enterprise_wechat_aibot(request, 1)

    assert response.status_code == 200
    assert response.content == b"success"
    mocked.assert_called_once_with(request, 1)
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
cd server
uv run pytest apps/opspilot/tests/test_enterprise_wechat_aibot_views.py::test_enterprise_wechat_aibot_get_delegates_to_url_verification apps/opspilot/tests/test_enterprise_wechat_aibot_views.py::test_enterprise_wechat_aibot_post_delegates_to_handler -q
```

Expected: FAIL，错误中包含 `cannot import name 'execute_chat_flow_enterprise_wechat_aibot'`。

- [ ] **Step 3: 增加枚举值**

Modify `server/apps/opspilot/enum.py` in `WorkFlowExecuteType`:

```python
ENTERPRISE_WECHAT_AIBOT = "enterprise_wechat_aibot", _("Enterprise WeChat AI Bot")
```

- [ ] **Step 4: 增加视图入口**

Modify `server/apps/opspilot/views.py` imports:

```python
from apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils import EnterpriseWechatAibotChatFlowUtils
```

Add function near existing external channel entrypoints:

```python
@api_exempt
def execute_chat_flow_enterprise_wechat_aibot(request, bot_id):
    return EnterpriseWechatAibotChatFlowUtils.handle_request(request, bot_id)
```

- [ ] **Step 5: 增加 URL 路由**

Modify `server/apps/opspilot/urls.py`:

```python
path(
    "bot_mgmt/execute_chat_flow_enterprise_wechat_aibot/<int:bot_id>/",
    views.execute_chat_flow_enterprise_wechat_aibot,
    name="execute_chat_flow_enterprise_wechat_aibot",
),
```

- [ ] **Step 6: 注册入口节点**

Modify `server/apps/opspilot/utils/chat_flow_utils/engine/node_registry.py` in `_register_builtin_nodes`, next to `enterprise_wechat`:

```python
self.register_node_class("enterprise_wechat_aibot", EntryNode)
```

- [ ] **Step 7: 实现 `handle_request` 基础骨架**

Modify `server/apps/opspilot/utils/enterprise_wechat_aibot_chat_flow_utils.py`:

```python
from django.http import HttpResponse

from apps.opspilot.models import Bot


    @classmethod
    def handle_request(cls, request: HttpRequest, bot_id: int) -> HttpResponse:
        try:
            bot = Bot.objects.get(id=bot_id, is_online=True)
        except Bot.DoesNotExist:
            logger.warning("企微智能机器人回调 bot 不存在或未上线: %s", bot_id)
            return HttpResponse("success", content_type="text/plain")

        workflow = getattr(bot, "workflow", None)
        if workflow is None:
            logger.warning("企微智能机器人回调缺少 workflow: %s", bot_id)
            return HttpResponse("success", content_type="text/plain")

        node_id, config = cls.get_aibot_node_config(workflow)
        if not node_id or not config:
            logger.warning("企微智能机器人入口节点不存在: %s", bot_id)
            return HttpResponse("success", content_type="text/plain")

        if request.method == "GET":
            return cls.handle_url_verification(request, config)
        if request.method == "POST":
            return cls.handle_aibot_message(request, bot_id, node_id, config)
        return HttpResponse("method not allowed", status=405)
```

- [ ] **Step 8: 运行视图委托测试**

Run:

```powershell
cd server
uv run pytest apps/opspilot/tests/test_enterprise_wechat_aibot_views.py::test_enterprise_wechat_aibot_get_delegates_to_url_verification apps/opspilot/tests/test_enterprise_wechat_aibot_views.py::test_enterprise_wechat_aibot_post_delegates_to_handler -q
```

Expected:

```text
2 passed
```

- [ ] **Step 9: 提交路由和入口注册**

Run:

```powershell
git add server/apps/opspilot/enum.py server/apps/opspilot/views.py server/apps/opspilot/urls.py server/apps/opspilot/utils/chat_flow_utils/engine/node_registry.py server/apps/opspilot/utils/enterprise_wechat_aibot_chat_flow_utils.py server/apps/opspilot/tests/test_enterprise_wechat_aibot_views.py
git commit -m "feat: 注册企微智能机器人工作流入口"
```

## Task 4: POST 消息处理、去重和 Celery 投递

**Files:**
- Modify: `server/apps/opspilot/utils/enterprise_wechat_aibot_chat_flow_utils.py`
- Modify: `server/apps/opspilot/tasks.py`
- Modify: `server/apps/opspilot/tests/test_enterprise_wechat_aibot_views.py`

- [ ] **Step 1: 写 POST 消息处理测试**

Append to `server/apps/opspilot/tests/test_enterprise_wechat_aibot_views.py`:

```python
def test_handle_aibot_message_dispatches_text_message(request_factory):
    request = request_factory.post(
        "/callback",
        data=b'{"encrypt":"abc"}',
        content_type="application/json",
        QUERY_STRING="msg_signature=s&timestamp=1&nonce=n",
    )
    config = {
        "connectionMode": "webhook",
        "webhook": {"token": "token", "encodingAESKey": "key", "aibotid": "bot-a"},
    }
    message = {
        "msgid": "m1",
        "aibotid": "bot-a",
        "chatid": "chat-1",
        "from": {"userid": "user-1"},
        "response_url": "https://example.com/response",
        "msgtype": "text",
        "text": {"content": "@机器人 查询 CPU"},
    }

    with patch(
        "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotCrypto.decrypt_callback",
        return_value=message,
    ), patch(
        "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotChatFlowUtils.set_message_processing",
        return_value=True,
    ), patch(
        "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.process_enterprise_wechat_aibot_message.delay"
    ) as delay:
        response = EnterpriseWechatAibotChatFlowUtils.handle_aibot_message(request, 10, "node-1", config)

    assert response.status_code == 200
    assert response.content == b"success"
    delay.assert_called_once()
    args = delay.call_args.args
    assert args[0] == 10
    assert args[1] == "m1"
    assert args[2]["last_message"] == "查询 CPU"
    assert args[2]["user_id"] == "user-1"


def test_handle_aibot_message_skips_aibotid_mismatch(request_factory):
    request = request_factory.post("/callback", data=b'{"encrypt":"abc"}', content_type="application/json")
    config = {
        "connectionMode": "webhook",
        "webhook": {"token": "token", "encodingAESKey": "key", "aibotid": "expected"},
    }
    message = {"msgid": "m1", "aibotid": "actual", "msgtype": "text", "text": {"content": "hi"}}

    with patch(
        "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotCrypto.decrypt_callback",
        return_value=message,
    ), patch(
        "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.process_enterprise_wechat_aibot_message.delay"
    ) as delay:
        response = EnterpriseWechatAibotChatFlowUtils.handle_aibot_message(request, 10, "node-1", config)

    assert response.status_code == 200
    assert response.content == b"success"
    delay.assert_not_called()


def test_handle_aibot_message_does_not_dispatch_duplicate(request_factory):
    request = request_factory.post("/callback", data=b'{"encrypt":"abc"}', content_type="application/json")
    config = {"connectionMode": "webhook", "webhook": {"token": "token", "encodingAESKey": "key"}}
    message = {"msgid": "m1", "msgtype": "text", "text": {"content": "hi"}}

    with patch(
        "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotCrypto.decrypt_callback",
        return_value=message,
    ), patch(
        "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotChatFlowUtils.set_message_processing",
        return_value=False,
    ), patch(
        "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.process_enterprise_wechat_aibot_message.delay"
    ) as delay:
        response = EnterpriseWechatAibotChatFlowUtils.handle_aibot_message(request, 10, "node-1", config)

    assert response.status_code == 200
    assert response.content == b"success"
    delay.assert_not_called()
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
cd server
uv run pytest apps/opspilot/tests/test_enterprise_wechat_aibot_views.py::test_handle_aibot_message_dispatches_text_message apps/opspilot/tests/test_enterprise_wechat_aibot_views.py::test_handle_aibot_message_skips_aibotid_mismatch apps/opspilot/tests/test_enterprise_wechat_aibot_views.py::test_handle_aibot_message_does_not_dispatch_duplicate -q
```

Expected: FAIL，错误中包含 `has no attribute 'handle_aibot_message'` 或无法 patch `process_enterprise_wechat_aibot_message`。

- [ ] **Step 3: 在 tasks 中添加任务占位导入目标**

Modify `server/apps/opspilot/tasks.py`:

```python
@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def process_enterprise_wechat_aibot_message(self, bot_id, msg_id, message, sender_id, config):
    from apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils import EnterpriseWechatAibotChatFlowUtils

    return _run_channel_message(
        self,
        EnterpriseWechatAibotChatFlowUtils,
        bot_id,
        msg_id,
        message,
        sender_id,
        config,
        "企微智能机器人",
    )
```

- [ ] **Step 4: 实现 `handle_aibot_message`**

Modify `server/apps/opspilot/utils/enterprise_wechat_aibot_chat_flow_utils.py` imports:

```python
from apps.opspilot.tasks import process_enterprise_wechat_aibot_message
```

Add method:

```python
    @classmethod
    def handle_aibot_message(cls, request: HttpRequest, bot_id: int, node_id: str, config: dict[str, Any]) -> HttpResponse:
        webhook = cls.get_webhook_config(config)
        if webhook is None:
            logger.warning("企微智能机器人短连接配置无效: %s", bot_id)
            return HttpResponse("success", content_type="text/plain")

        crypto = EnterpriseWechatAibotCrypto(
            token=webhook["token"],
            encoding_aes_key=webhook["encodingAESKey"],
        )
        try:
            message = crypto.decrypt_callback(
                msg_signature=request.GET.get("msg_signature", ""),
                timestamp=request.GET.get("timestamp", ""),
                nonce=request.GET.get("nonce", ""),
                body=request.body,
            )
        except EnterpriseWechatAibotCryptoError:
            logger.warning("企微智能机器人消息解密失败: %s", bot_id, exc_info=True)
            return HttpResponse("success", content_type="text/plain")

        msg_id = message.get("msgid")
        if not msg_id:
            logger.warning("企微智能机器人消息缺少 msgid: %s", bot_id)
            return HttpResponse("success", content_type="text/plain")

        expected_aibotid = webhook.get("aibotid")
        if expected_aibotid and message.get("aibotid") != expected_aibotid:
            logger.warning("企微智能机器人 aibotid 不匹配: bot_id=%s msg_id=%s", bot_id, msg_id)
            return HttpResponse("success", content_type="text/plain")

        if not cls.set_message_processing(bot_id, msg_id):
            return HttpResponse("success", content_type="text/plain")

        if message.get("msgtype") != "text":
            cls.send_markdown_reply(message.get("response_url") or "", "当前仅支持文本消息")
            cls.mark_message_completed(bot_id, msg_id)
            return HttpResponse("success", content_type="text/plain")

        clean_text = cls.clean_text_message((message.get("text") or {}).get("content") or "")
        flow_input = cls.build_flow_input(bot_id=bot_id, node_id=node_id, message=message, clean_text=clean_text)
        task_config = {**config, "node_id": node_id, "response_url": message.get("response_url") or ""}
        process_enterprise_wechat_aibot_message.delay(
            bot_id,
            msg_id,
            flow_input,
            flow_input.get("user_id", ""),
            task_config,
        )
        return HttpResponse("success", content_type="text/plain")
```

- [ ] **Step 5: 运行 POST 消息测试**

Run:

```powershell
cd server
uv run pytest apps/opspilot/tests/test_enterprise_wechat_aibot_views.py -q
```

Expected: all tests in file pass。

- [ ] **Step 6: 提交 POST 处理**

Run:

```powershell
git add server/apps/opspilot/utils/enterprise_wechat_aibot_chat_flow_utils.py server/apps/opspilot/tasks.py server/apps/opspilot/tests/test_enterprise_wechat_aibot_views.py
git commit -m "feat: 处理企微智能机器人短连接消息"
```

## Task 5: Celery 执行和主动回复

**Files:**
- Create: `server/apps/opspilot/tests/test_enterprise_wechat_aibot_tasks.py`
- Modify: `server/apps/opspilot/utils/enterprise_wechat_aibot_chat_flow_utils.py`
- Modify: `server/apps/opspilot/tasks.py`

- [ ] **Step 1: 写任务成功和失败测试**

Create `server/apps/opspilot/tests/test_enterprise_wechat_aibot_tasks.py`:

```python
from unittest.mock import ANY, Mock, patch

import pytest

from apps.opspilot.tasks import process_enterprise_wechat_aibot_message
from apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils import EnterpriseWechatAibotChatFlowUtils


def test_process_enterprise_wechat_aibot_message_replies_and_marks_completed():
    task = Mock()
    flow_input = {
        "last_message": "查询 CPU",
        "user_id": "user-1",
        "response_url": "https://example.com/response",
        "session_id": "chat-1",
    }

    with patch(
        "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotChatFlowUtils.async_process_and_reply"
    ) as async_process:
        process_enterprise_wechat_aibot_message.run(
            task,
            10,
            "m1",
            flow_input,
            "user-1",
            {"node_id": "node-1", "response_url": "https://example.com/response"},
        )

    async_process.assert_called_once_with(
        ANY,
        {"node_id": "node-1", "response_url": "https://example.com/response"},
        flow_input,
        "user-1",
        "m1",
    )


def test_send_markdown_reply_posts_markdown_payload():
    with patch("apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.requests.post") as post:
        post.return_value.raise_for_status.return_value = None

        EnterpriseWechatAibotChatFlowUtils.send_markdown_reply("https://example.com/response", "hello")

    post.assert_called_once_with(
        "https://example.com/response",
        json={"msgtype": "markdown", "markdown": {"content": "hello"}},
        timeout=10,
    )
```

- [ ] **Step 2: 运行任务测试**

Run:

```powershell
cd server
uv run pytest apps/opspilot/tests/test_enterprise_wechat_aibot_tasks.py -q
```

Expected: PASS。如果 `process_enterprise_wechat_aibot_message.run(...)` 调用方式与现有 Celery 测试风格不一致，参考 `server/apps/opspilot/tests/react_agent/cases/test_channel_message_dedup_async_fix.py` 调整为项目已有调用方式。

- [ ] **Step 3: 确认 `async_process_and_reply` 能使用子类 `send_reply`**

Modify `server/apps/opspilot/utils/enterprise_wechat_aibot_chat_flow_utils.py` to add:

```python
    def send_reply(self, reply_text: str, sender_id: str, config: dict[str, Any]) -> None:
        self.send_markdown_reply(config.get("response_url") or "", reply_text)
```

- [ ] **Step 4: 运行任务测试和外部渠道去重回归**

Run:

```powershell
cd server
uv run pytest apps/opspilot/tests/test_enterprise_wechat_aibot_tasks.py apps/opspilot/tests/react_agent/cases/test_external_channel_message_dedup.py apps/opspilot/tests/react_agent/cases/test_channel_message_dedup_async_fix.py -q
```

Expected: PASS。

- [ ] **Step 5: 提交 Celery 任务和主动回复**

Run:

```powershell
git add server/apps/opspilot/tests/test_enterprise_wechat_aibot_tasks.py server/apps/opspilot/utils/enterprise_wechat_aibot_chat_flow_utils.py server/apps/opspilot/tasks.py
git commit -m "feat: 添加企微智能机器人异步回复任务"
```

## Task 6: 前端节点注册和默认配置

**Files:**
- Modify: `web/src/app/opspilot/constants/chatflow.ts`
- Modify: `web/src/app/opspilot/components/chatflow/types.ts`
- Modify: `web/src/app/opspilot/components/chatflow/nodes/index.tsx`
- Modify: `web/src/app/opspilot/components/chatflow/ChatflowEditor.tsx`
- Modify: `web/src/app/opspilot/components/chatflow/hooks/useNodeDrop.ts`

- [ ] **Step 1: 定位现有入口节点写法**

Run:

```powershell
rg "enterprise_wechat|wechat_official|dingtalk" web/src/app/opspilot/constants/chatflow.ts web/src/app/opspilot/components/chatflow -n
```

Expected: 输出现有入口节点注册、默认配置、节点组件和拖拽标签位置。

- [ ] **Step 2: 新增默认配置**

Modify `web/src/app/opspilot/constants/chatflow.ts`:

```ts
enterprise_wechat_aibot: {
  label: 'chatflow.enterpriseWechatAibot',
  icon: 'qiwei2',
  color: 'green',
  type: 'trigger',
},
```

Add to `TRIGGER_NODE_TYPES`:

```ts
'enterprise_wechat_aibot',
```

Add branch in `getDefaultConfig`:

```ts
if (type === 'enterprise_wechat_aibot') {
  return {
    connectionMode: 'webhook',
    webhook: {
      token: '',
      encodingAESKey: '',
      aibotid: '',
    },
    websocket: {
      botId: '',
      secret: '',
    },
    inputParams: 'last_message',
    outputParams: 'last_message',
  };
}
```

- [ ] **Step 3: 扩展节点类型**

Modify `web/src/app/opspilot/components/chatflow/types.ts`:

```ts
| 'enterprise_wechat_aibot'
```

Add it next to existing `enterprise_wechat` entry.

- [ ] **Step 4: 新增节点展示组件**

Modify `web/src/app/opspilot/components/chatflow/nodes/index.tsx`:

```tsx
export const EnterpriseWechatAibotNode = (props: NodeProps) => (
  <BaseNode {...props} nodeType="enterprise_wechat_aibot" />
);
```

- [ ] **Step 5: 注册 React Flow node type**

Modify `web/src/app/opspilot/components/chatflow/ChatflowEditor.tsx`:

```ts
enterprise_wechat_aibot: EnterpriseWechatAibotNode,
```

Add `enterprise_wechat_aibot` to the same `noInputTypes` list as `enterprise_wechat`、`wechat_official`、`dingtalk`。

- [ ] **Step 6: 注册拖拽标签**

Modify `web/src/app/opspilot/components/chatflow/hooks/useNodeDrop.ts`:

```ts
enterprise_wechat_aibot: t('chatflow.enterpriseWechatAibot'),
```

- [ ] **Step 7: 运行前端类型检查**

Run:

```powershell
cd web
pnpm type-check
```

Expected: PASS。如果失败为缺少导入，按 TypeScript 报错补齐 `EnterpriseWechatAibotNode` import。

- [ ] **Step 8: 提交前端节点注册**

Run:

```powershell
git add web/src/app/opspilot/constants/chatflow.ts web/src/app/opspilot/components/chatflow/types.ts web/src/app/opspilot/components/chatflow/nodes/index.tsx web/src/app/opspilot/components/chatflow/ChatflowEditor.tsx web/src/app/opspilot/components/chatflow/hooks/useNodeDrop.ts
git commit -m "feat: 注册企微智能机器人工作流节点"
```

## Task 7: 前端配置表单、回调 URL 和国际化

**Files:**
- Create: `web/src/app/opspilot/components/chatflow/components/nodeConfigs/EnterpriseWechatAibotNodeConfig.tsx`
- Modify: `web/src/app/opspilot/components/chatflow/components/nodeConfigs/types.ts`
- Modify: `web/src/app/opspilot/components/chatflow/components/nodeConfigs/index.ts`
- Modify: `web/src/app/opspilot/components/chatflow/NodeConfigForm.tsx`
- Modify: `web/src/app/opspilot/locales/zh.json`
- Modify: `web/src/app/opspilot/locales/en.json`

- [ ] **Step 1: 新增配置组件**

Create `web/src/app/opspilot/components/chatflow/components/nodeConfigs/EnterpriseWechatAibotNodeConfig.tsx`:

```tsx
import React from 'react';
import { Button, Form, Input, message } from 'antd';
import { CopyOutlined } from '@ant-design/icons';
import type { EnterpriseWechatAibotNodeConfigProps } from './types';

export const EnterpriseWechatAibotNodeConfig: React.FC<EnterpriseWechatAibotNodeConfigProps> = ({ t, botId }) => {
  const callbackPath = `/api/v1/opspilot/bot_mgmt/execute_chat_flow_enterprise_wechat_aibot/${botId}/`;
  const callbackUrl = `${typeof window !== 'undefined' ? window.location.origin : ''}${callbackPath}`;

  const copyCallbackUrl = async () => {
    try {
      await navigator.clipboard.writeText(callbackUrl);
      message.success(t('chatflow.nodeConfig.apiLinkCopied'));
    } catch {
      const textArea = document.createElement('textarea');
      textArea.value = callbackUrl;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      message.success(t('chatflow.nodeConfig.apiLinkCopied'));
    }
  };

  return (
    <div className="p-4 bg-[var(--color-fill-1)] border border-[var(--color-border-2)] rounded-md">
      <h4 className="text-sm font-medium mb-3">{t('chatflow.nodeConfig.enterpriseWechatAibotParams')}</h4>
      <Form.Item name="connectionMode" initialValue="webhook" hidden>
        <Input />
      </Form.Item>
      <Form.Item name={['websocket', 'botId']} initialValue="" hidden>
        <Input />
      </Form.Item>
      <Form.Item name={['websocket', 'secret']} initialValue="" hidden>
        <Input />
      </Form.Item>
      <Form.Item label={t('chatflow.nodeConfig.callbackUrl')}>
        <Input
          readOnly
          value={callbackUrl}
          addonAfter={<Button type="text" size="small" icon={<CopyOutlined />} onClick={copyCallbackUrl} />}
        />
      </Form.Item>
      <Form.Item
        label="Token"
        name={['webhook', 'token']}
        rules={[{ required: true, message: t('chatflow.nodeConfig.enterToken') }]}
      >
        <Input.Password autoComplete="new-password" />
      </Form.Item>
      <Form.Item
        label="EncodingAESKey"
        name={['webhook', 'encodingAESKey']}
        rules={[{ required: true, message: t('chatflow.nodeConfig.enterEncodingAESKey') }]}
      >
        <Input.Password autoComplete="new-password" />
      </Form.Item>
      <Form.Item label={t('chatflow.nodeConfig.aibotId')} name={['webhook', 'aibotid']}>
        <Input placeholder={t('chatflow.nodeConfig.enterAibotId')} />
      </Form.Item>
    </div>
  );
};
```

- [ ] **Step 2: 导出配置组件**

Modify `web/src/app/opspilot/components/chatflow/components/nodeConfigs/index.ts`:

```ts
export { EnterpriseWechatAibotNodeConfig } from './EnterpriseWechatAibotNodeConfig';
```

- [ ] **Step 3: 映射配置表单**

Modify `web/src/app/opspilot/components/chatflow/NodeConfigForm.tsx` import section:

```ts
EnterpriseWechatAibotNodeConfig,
```

Add render branch next to `enterprise_wechat`:

```tsx
{nodeType === 'enterprise_wechat_aibot' && <EnterpriseWechatAibotNodeConfig t={t} botId={botId} />}
```

- [ ] **Step 4: 补 Props 类型**

Modify `web/src/app/opspilot/components/chatflow/components/nodeConfigs/types.ts` so `NodeConfigProps` includes the fields actually passed by `NodeConfigForm`:

```ts
export interface EnterpriseWechatAibotNodeConfigProps extends BaseNodeConfigProps {
  botId: string;
}
```

- [ ] **Step 5: 增加中文文案**

Modify `web/src/app/opspilot/locales/zh.json`:

```json
"enterpriseWechatAibot": "企微智能机器人",
"nodeConfig": {
  "callbackUrl": "回调地址",
  "enterToken": "请输入 Token",
  "enterEncodingAESKey": "请输入 EncodingAESKey",
  "aibotId": "智能机器人 ID",
  "enterAibotId": "请输入智能机器人 ID（可选）"
}
```

Merge into existing `chatflow` and `chatflow.nodeConfig` object，不要覆盖已有 key。

- [ ] **Step 6: 增加英文文案**

Modify `web/src/app/opspilot/locales/en.json`:

```json
"enterpriseWechatAibot": "WeCom AI Bot",
"nodeConfig": {
  "callbackUrl": "Callback URL",
  "enterToken": "Enter Token",
  "enterEncodingAESKey": "Enter EncodingAESKey",
  "aibotId": "AI Bot ID",
  "enterAibotId": "Enter AI Bot ID (optional)"
}
```

Merge into existing `chatflow` and `chatflow.nodeConfig` object，不要覆盖已有 key。

- [ ] **Step 7: 运行前端 lint 和类型检查**

Run:

```powershell
cd web
pnpm lint
pnpm type-check
```

Expected: PASS。

- [ ] **Step 8: 提交配置表单**

Run:

```powershell
git add web/src/app/opspilot/components/chatflow/components/nodeConfigs/EnterpriseWechatAibotNodeConfig.tsx web/src/app/opspilot/components/chatflow/components/nodeConfigs/types.ts web/src/app/opspilot/components/chatflow/components/nodeConfigs/index.ts web/src/app/opspilot/components/chatflow/NodeConfigForm.tsx web/src/app/opspilot/locales/zh.json web/src/app/opspilot/locales/en.json
git commit -m "feat: 添加企微智能机器人短连接配置表单"
```

## Task 8: 最小集成验证

**Files:**
- No new files unless previous tasks reveal missing imports.

- [ ] **Step 1: 后端定向测试**

Run:

```powershell
cd server
uv run pytest apps/opspilot/tests/test_enterprise_wechat_aibot_crypto.py apps/opspilot/tests/test_enterprise_wechat_aibot_views.py apps/opspilot/tests/test_enterprise_wechat_aibot_tasks.py -q
```

Expected: PASS。

- [ ] **Step 2: 后端外部渠道回归**

Run:

```powershell
cd server
uv run pytest apps/opspilot/tests/react_agent/cases/test_external_channel_message_dedup.py apps/opspilot/tests/react_agent/cases/test_channel_message_dedup_async_fix.py -q
```

Expected: PASS。

- [ ] **Step 3: 后端门禁**

Run:

```powershell
cd server
make test
```

Expected: PASS。

- [ ] **Step 4: 前端门禁**

Run:

```powershell
cd web
pnpm lint
pnpm type-check
```

Expected: PASS。

- [ ] **Step 5: 检查没有误带主工作区改动**

Run:

```powershell
git status --short
```

Expected: 只显示本需求相关文件；不显示根工作区的 `.husky/pre-commit` 和 `server/apps/opspilot/tests/test_agent_execute_timeout.py`。

- [ ] **Step 6: 提交最终验证记录**

When Task 8 changes files because verification exposes missing imports or wiring issues, commit those files:

```powershell
git add <fixed-files>
git commit -m "fix: 完善企微智能机器人入口联调"
```

When Task 8 only runs commands and no files change, leave the working tree clean and do not create an empty commit。

## 自检结果

- 规格覆盖：设计中的短连接 URL 校验、JSON 解密、文本消息、`response_url` markdown 回复、`msgid` 去重、`aibotid` 校验、非文本提示、`connectionMode=webhook` 默认、`websocket` 后门结构、前端节点和配置表单均有对应任务。
- 占位符扫描：计划不包含待填充事项；所有改动路径、函数名、测试名和命令均已给出。
- 类型一致性：后端统一使用 `enterprise_wechat_aibot`、`EnterpriseWechatAibotChatFlowUtils`、`EnterpriseWechatAibotCrypto`；前端统一使用 `enterprise_wechat_aibot`、`EnterpriseWechatAibotNodeConfig`。
