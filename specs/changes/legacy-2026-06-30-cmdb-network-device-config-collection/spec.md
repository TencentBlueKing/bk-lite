# Historical Superpowers change: 2026-06-30-cmdb-network-device-config-collection

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-30-cmdb-network-device-config-collection-plan.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build CMDB network device configuration collection for existing `switch/router/firewall/loadbalance` instances using Stargazer Netmiko execution and the existing config-file version callback path.

**Architecture:** CMDB validates supported network-device instances and derives Netmiko `device_type` from each instance `brand`, then dispatches tasks through the existing `/api/collect/collect_info` route with `callback_subject=receive_config_file_result`. Stargazer adds a focused `network_config_file` plugin that validates commands, executes them one by one with Netmiko, merges successful output, and returns the existing `ConfigFileService` payload shape. The web console adds a dedicated task form that only allows supported branded network device instances and explains supported brands.

**Tech Stack:** Django 4.2, DRF serializers, existing CMDB NodeParams dispatch, Sanic Stargazer plugin framework, Netmiko, Next.js 16, React 19, Ant Design, pytest, pnpm lint/type-check.

---

## File Structure

### CMDB Server

- Create: `server/apps/cmdb/services/network_config_file_policy.py`
  - Owns supported model IDs, brand normalization, brand-to-Netmiko mapping, command splitting, dangerous-command validation, and error-summary truncation.
- Create: `server/apps/cmdb/node_configs/network_config_file.py`
  - Builds headers/env for network device config collection and registers `model_id="network_config_file"` with driver type `protocol`.
- Modify: `server/apps/cmdb/constants/constants.py`
  - Adds collect-tree entry and encrypted fields for `network_config_file`.
- Modify: `server/apps/cmdb/serializers/collect_serializer.py`
  - Adds validation branch for network device config collection.
- Modify: `server/apps/cmdb/views/collect.py`
  - Adds readonly endpoint/action for supported network config brands so the frontend can render tip and disable unsupported instances.
- Test: `server/apps/cmdb/tests/test_network_config_file_policy.py`
- Test: `server/apps/cmdb/tests/test_network_config_file_serializer.py`
- Test: `server/apps/cmdb/tests/test_network_config_file_node_params.py`

### Stargazer

- Add dependency: `agents/stargazer/pyproject.toml`
  - Add `netmiko` with a pinned version compatible with Python 3.12.
- Create: `agents/stargazer/plugins/inputs/network_config_file/plugin.yml`
- Create: `agents/stargazer/plugins/inputs/network_config_file/__init__.py`
- Create: `agents/stargazer/plugins/inputs/network_config_file/constants.py`
- Create: `agents/stargazer/plugins/inputs/network_config_file/network_config_file_info.py`
  - Netmiko plugin implementation.
- Test: `agents/stargazer/tests/test_network_config_file_info.py`

### Web

- Modify: `web/src/app/cmdb/api/collect.ts`
  - Add `getNetworkConfigBrands`.
- Modify: `web/src/app/cmdb/types/autoDiscovery.ts`
  - Add optional `enable_password`, `config_name`, `commands`, `need_enable`, `brand`, and `device_type` fields to the existing task/credential instance types used by professional collection forms.
- Modify: `web/src/app/cmdb/constants/professCollection.ts`
  - Add initial values and command validation helpers if local constants are already used there.
- Create: `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/networkConfigFileTask.tsx`
  - Dedicated form for network device config collection.
- Modify: `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/page.tsx`
  - Route `model_id="network_config_file"` to `NetworkConfigFileTask`.
- Test: place focused unit tests beside helpers if the existing web test setup has colocated test patterns; otherwise rely on lint/type-check and server-side behavior tests for MVP.

---

## Task 1: CMDB Policy Helpers

**Files:**
- Create: `server/apps/cmdb/services/network_config_file_policy.py`
- Test: `server/apps/cmdb/tests/test_network_config_file_policy.py`

- [ ] **Step 1: Write failing tests for brand mapping and supported models**

```python
# server/apps/cmdb/tests/test_network_config_file_policy.py
import pytest

from apps.cmdb.services.network_config_file_policy import (
    SUPPORTED_NETWORK_CONFIG_MODELS,
    get_supported_brand_options,
    resolve_device_type,
    validate_network_config_instance,
)
from apps.core.exceptions.base_app_exception import BaseAppException


def test_supported_models_are_only_mvp_network_models():
    assert SUPPORTED_NETWORK_CONFIG_MODELS == {"switch", "router", "firewall", "loadbalance"}


@pytest.mark.parametrize(
    ("brand", "expected"),
    [
        ("华为", "huawei"),
        ("Huawei", "huawei"),
        ("H3C", "hp_comware"),
        ("HP Comware", "hp_comware"),
        ("Cisco", "cisco_ios"),
        ("Juniper", "juniper_junos"),
        ("F5", "f5_tmsh"),
        ("Fortinet", "fortinet"),
    ],
)
def test_resolve_device_type_normalizes_supported_brand_aliases(brand, expected):
    assert resolve_device_type(brand) == expected


def test_resolve_device_type_rejects_empty_brand():
    with pytest.raises(BaseAppException, match="缺少厂商"):
        resolve_device_type("")


def test_resolve_device_type_rejects_unsupported_brand():
    with pytest.raises(BaseAppException, match="暂不支持"):
        resolve_device_type("UnknownVendor")


def test_validate_network_config_instance_requires_supported_model_and_brand():
    instance = {"_id": 11, "model_id": "switch", "brand": "Cisco", "ip_addr": "10.0.0.1"}

    result = validate_network_config_instance(instance)

    assert result["device_type"] == "cisco_ios"
    assert result["host"] == "10.0.0.1"


def test_validate_network_config_instance_rejects_non_mvp_model():
    with pytest.raises(BaseAppException, match="仅支持"):
        validate_network_config_instance({"model_id": "host", "brand": "Cisco", "ip_addr": "10.0.0.1"})


def test_get_supported_brand_options_is_frontend_friendly():
    options = get_supported_brand_options()

    assert {"label": "Cisco", "device_type": "cisco_ios"} in options
    assert any("华为" in item["label"] for item in options)
```

- [ ] **Step 2: Run policy tests to verify RED**

Run:

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_network_config_file_policy.py
```

Expected: FAIL with `ModuleNotFoundError: No module named 'apps.cmdb.services.network_config_file_policy'`.

- [ ] **Step 3: Implement minimal policy helper**

Create `server/apps/cmdb/services/network_config_file_policy.py`:

```python
from __future__ import annotations

import re
from typing import Iterable

from apps.core.exceptions.base_app_exception import BaseAppException

SUPPORTED_NETWORK_CONFIG_MODELS = {"switch", "router", "firewall", "loadbalance"}

BRAND_DEVICE_TYPE_ALIASES = {
    "华为": "huawei",
    "huawei": "huawei",
    "h3c": "hp_comware",
    "hp comware": "hp_comware",
    "hewlett-packard": "hp_comware",
    "hewlett packard": "hp_comware",
    "cisco": "cisco_ios",
    "juniper": "juniper_junos",
    "f5": "f5_tmsh",
    "fortinet": "fortinet",
}

SUPPORTED_BRAND_OPTIONS = [
    {"label": "华为 / Huawei", "device_type": "huawei"},
    {"label": "H3C / HP Comware", "device_type": "hp_comware"},
    {"label": "Cisco", "device_type": "cisco_ios"},
    {"label": "Juniper", "device_type": "juniper_junos"},
    {"label": "F5", "device_type": "f5_tmsh"},
    {"label": "Fortinet", "device_type": "fortinet"},
]

DANGEROUS_EXACT_COMMANDS = {"conf t", "write erase"}
DANGEROUS_COMMAND_PREFIXES = {
    "configure",
    "reload",
    "reboot",
    "reset",
    "delete",
    "erase",
    "format",
    "copy",
    "scp",
    "tftp",
    "ftp",
    "install",
    "upgrade",
    "commit",
    "save",
    "shutdown",
    "undo",
    "set",
}
MAX_ERROR_SUMMARY_LENGTH = 2000


def normalize_brand(brand: str | None) -> str:
    return " ".join(str(brand or "").strip().lower().split())


def resolve_device_type(brand: str | None) -> str:
    normalized = normalize_brand(brand)
    if not normalized:
        raise BaseAppException("网络设备缺少厂商字段，无法匹配采集驱动")
    device_type = BRAND_DEVICE_TYPE_ALIASES.get(normalized)
    if not device_type:
        raise BaseAppException(f"当前厂商暂不支持网络配置采集: {brand}")
    return device_type


def get_supported_brand_options() -> list[dict]:
    return [dict(item) for item in SUPPORTED_BRAND_OPTIONS]


def split_commands(raw_commands: str | Iterable[str] | None) -> list[str]:
    if raw_commands is None:
        return []
    if isinstance(raw_commands, str):
        lines = raw_commands.splitlines()
    else:
        lines = list(raw_commands)
    return [str(line).strip() for line in lines if str(line).strip()]


def validate_safe_command(command: str) -> str:
    normalized = " ".join(str(command or "").strip().split())
    lowered = normalized.lower()
    if not lowered:
        raise BaseAppException("采集命令不能为空")
    if lowered in DANGEROUS_EXACT_COMMANDS:
        raise BaseAppException(f"采集命令存在高危操作: {normalized}")
    first_word = re.split(r"\s+", lowered, maxsplit=1)[0]
    if first_word in DANGEROUS_COMMAND_PREFIXES:
        raise BaseAppException(f"采集命令存在高危操作: {normalized}")
    return normalized


def validate_commands(raw_commands: str | Iterable[str] | None) -> list[str]:
    commands = split_commands(raw_commands)
    if not commands:
        raise BaseAppException("采集命令不能为空")
    return [validate_safe_command(command) for command in commands]


def truncate_error_summary(error: str) -> str:
    value = str(error or "")
    if len(value) <= MAX_ERROR_SUMMARY_LENGTH:
        return value
    return value[:MAX_ERROR_SUMMARY_LENGTH] + "...[truncated]"


def validate_network_config_instance(instance: dict) -> dict:
    model_id = str(instance.get("model_id") or "").strip()
    if model_id not in SUPPORTED_NETWORK_CONFIG_MODELS:
        raise BaseAppException("网络配置采集仅支持 switch/router/firewall/loadbalance")
    host = str(instance.get("ip_addr") or instance.get("host") or "").strip()
    if not host:
        raise BaseAppException("网络设备缺少管理IP")
    device_type = resolve_device_type(instance.get("brand"))
    return {**instance, "host": host, "device_type": device_type}
```

- [ ] **Step 4: Run policy tests to verify GREEN**

Run the same `pytest` command from Step 2.

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add server/apps/cmdb/services/network_config_file_policy.py server/apps/cmdb/tests/test_network_config_file_policy.py
git commit -m "feat: 添加网络配置采集策略校验"
```

---

## Task 2: CMDB Serializer Validation and Collect Tree Entry

**Files:**
- Modify: `server/apps/cmdb/constants/constants.py`
- Modify: `server/apps/cmdb/serializers/collect_serializer.py`
- Test: `server/apps/cmdb/tests/test_network_config_file_serializer.py`

- [ ] **Step 1: Write failing serializer tests**

```python
# server/apps/cmdb/tests/test_network_config_file_serializer.py
import pytest

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes
from apps.cmdb.serializers.collect_serializer import CollectModelSerializer


def _payload(instances, params=None, credential=None):
    return {
        "name": "network-config",
        "task_type": CollectPluginTypes.CONFIG_FILE,
        "driver_type": CollectDriverTypes.PROTOCOL,
        "model_id": "network_config_file",
        "access_point": [{"id": 1}],
        "instances": instances,
        "params": {
            "config_name": "running-config",
            "commands": "show running-config\nshow version",
            "need_enable": False,
            **(params or {}),
        },
        "credential": credential or [{"username": "admin", "password": "secret", "port": 22}],
    }


def test_network_config_file_serializer_accepts_supported_branded_device():
    serializer = CollectModelSerializer(
        data=_payload([{"_id": "1", "model_id": "switch", "brand": "Cisco", "ip_addr": "10.0.0.1"}])
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["driver_type"] == CollectDriverTypes.PROTOCOL
    assert serializer.validated_data["params"]["commands"] == "show running-config\nshow version"


def test_network_config_file_serializer_rejects_empty_brand():
    serializer = CollectModelSerializer(
        data=_payload([{"_id": "1", "model_id": "switch", "brand": "", "ip_addr": "10.0.0.1"}])
    )

    assert not serializer.is_valid()
    assert "厂商" in str(serializer.errors)


def test_network_config_file_serializer_rejects_dangerous_command():
    serializer = CollectModelSerializer(
        data=_payload(
            [{"_id": "1", "model_id": "switch", "brand": "Cisco", "ip_addr": "10.0.0.1"}],
            params={"commands": "show version\nreload"},
        )
    )

    assert not serializer.is_valid()
    assert "高危" in str(serializer.errors)


def test_network_config_file_serializer_requires_enable_password_when_enable_is_true():
    serializer = CollectModelSerializer(
        data=_payload(
            [{"_id": "1", "model_id": "switch", "brand": "Cisco", "ip_addr": "10.0.0.1"}],
            params={"need_enable": True},
            credential=[{"username": "admin", "password": "secret", "port": 22}],
        )
    )

    assert not serializer.is_valid()
    assert "特权密码" in str(serializer.errors)
```

- [ ] **Step 2: Run serializer tests to verify RED**

Run:

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_network_config_file_serializer.py
```

Expected: FAIL because `network_config_file` validation is not implemented.

- [ ] **Step 3: Add collect-tree entry**

In `server/apps/cmdb/constants/constants.py`, add a child entry near the existing `config_file` entry:

```python
{
    "id": "network_config_file",
    "model_id": "network_config_file",
    "name": "网络设备配置文件",
    "task_type": CollectPluginTypes.CONFIG_FILE,
    "type": CollectDriverTypes.PROTOCOL,
    "tag": ["Netmiko", "Network"],
    "desc": "通过 Netmiko 采集网络设备配置命令输出并归档为配置文件版本",
    "icon": "config_file",
    "encrypted_fields": ["password", "enable_password"],
},
```

- [ ] **Step 4: Add serializer branch**

In `server/apps/cmdb/serializers/collect_serializer.py`, import helpers:

```python
from apps.cmdb.services.network_config_file_policy import (
    validate_commands,
    validate_network_config_instance,
)
```

Then add a branch before the existing `CONFIG_FILE` path validation:

```python
        if task_type == CollectPluginTypes.CONFIG_FILE and model_id == "network_config_file":
            params = dict(self._get_effective_params(attrs) or {})
            raw_instances = attrs.get("instances")
            if raw_instances is None and self.instance is not None:
                raw_instances = self.instance.instances
            if not raw_instances:
                raise serializers.ValidationError("请选择网络设备")

            validated_instances = []
            for instance in raw_instances:
                try:
                    validated_instances.append(validate_network_config_instance(instance))
                except Exception as err:
                    raise serializers.ValidationError({"instances": str(err)}) from err

            config_name = (params.get("config_name") or "").strip()
            if not config_name:
                raise serializers.ValidationError({"params": "请输入配置名称"})
            try:
                commands = validate_commands(params.get("commands"))
            except Exception as err:
                raise serializers.ValidationError({"params": str(err)}) from err

            need_enable = bool(params.get("need_enable"))
            credential_items = attrs.get("credential")
            if credential_items is None and self.instance is not None:
                credential_items = self.instance.credential
            credential_pool = CollectCredentialPoolService.normalize_pool(copy.deepcopy(credential_items))
            if need_enable and not any(item.get("enable_password") for item in credential_pool if isinstance(item, dict)):
                raise serializers.ValidationError({"credential": "启用特权模式时必须配置特权密码"})

            attrs["instances"] = validated_instances
            attrs["ip_range"] = ""
            attrs["driver_type"] = CollectDriverTypes.PROTOCOL
            attrs["params"] = {
                **params,
                "config_name": config_name,
                "commands": "\n".join(commands),
                "need_enable": need_enable,
            }
            return attrs
```

- [ ] **Step 5: Run serializer tests to verify GREEN**

Run the same `pytest` command from Step 2.

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add server/apps/cmdb/constants/constants.py server/apps/cmdb/serializers/collect_serializer.py server/apps/cmdb/tests/test_network_config_file_serializer.py
git commit -m "feat: 校验网络设备配置采集任务"
```

---

## Task 3: CMDB Node Params Dispatch

**Files:**
- Create: `server/apps/cmdb/node_configs/network_config_file.py`
- Test: `server/apps/cmdb/tests/test_network_config_file_node_params.py`

- [ ] **Step 1: Write failing node params tests**

```python
# server/apps/cmdb/tests/test_network_config_file_node_params.py
from types import SimpleNamespace

from apps.cmdb.node_configs.network_config_file import NetworkConfigFileNodeParams


def _task():
    return SimpleNamespace(
        id=42,
        model_id="network_config_file",
        driver_type="protocol",
        timeout=30,
        params={
            "config_name": "running-config",
            "commands": "show running-config\nshow version",
            "need_enable": True,
        },
        instances=[
            {
                "_id": "101",
                "model_id": "switch",
                "inst_name": "10.0.0.1-switch",
                "ip_addr": "10.0.0.1",
                "brand": "Cisco",
                "device_type": "cisco_ios",
            }
        ],
        ip_range="",
        access_point=[{"id": 9}],
        decrypt_credentials={
            "username": "admin",
            "password": "secret",
            "enable_password": "enable-secret",
            "port": 2222,
        },
    )


def test_custom_headers_include_network_config_callback_and_device_type():
    params = NetworkConfigFileNodeParams(_task())

    headers = params.custom_headers()

    assert headers["cmdbplugin_name"] == "network_config_file_info"
    assert headers["cmdbmodel_id"] == "network_config_file"
    assert headers["cmdbtarget_model_id"] == "switch"
    assert headers["cmdbtarget_instance_id"] == "101"
    assert headers["cmdbdevice_type"] == "cisco_ios"
    assert headers["cmdbcallback_subject"] == "receive_config_file_result"
    assert headers["cmdbconfig_name"] == "running-config"
    assert headers["cmdbcommands"] == "show running-config\nshow version"


def test_env_config_contains_password_and_enable_password_without_plain_headers():
    params = NetworkConfigFileNodeParams(_task())

    headers = params.custom_headers()
    env = params.env_config()

    assert headers["cmdbpassword"].startswith("${PASSWORD_password_cmdb_42")
    assert headers["cmdbenable_password"].startswith("${PASSWORD_enable_password_cmdb_42")
    assert any(value == "secret" for value in env.values())
    assert any(value == "enable-secret" for value in env.values())
```

- [ ] **Step 2: Run node params tests to verify RED**

Run:

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_network_config_file_node_params.py
```

Expected: FAIL because `apps.cmdb.node_configs.network_config_file` does not exist.

- [ ] **Step 3: Implement node params**

Create `server/apps/cmdb/node_configs/network_config_file.py`:

```python
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.services.network_config_file_policy import validate_network_config_instance


class NetworkConfigFileNodeParams(BaseNodeParams):
    supported_model_id = "network_config_file"
    supported_driver_type = "protocol"
    plugin_name = "network_config_file_info"
    interval = 10 * 60

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executor_type = "protocol"

    def _single_instance(self):
        instances = self.instance.instances or []
        return instances[0] if instances and isinstance(instances[0], dict) else {}

    def get_hosts(self):
        hosts = ",".join(
            validate_network_config_instance(instance)["host"]
            for instance in (self.instance.instances or [])
            if isinstance(instance, dict)
        )
        return "hosts", hosts

    def _secret_env_name(self, field_name, index=None):
        if index is None:
            return f"PASSWORD_{field_name}_{self._instance_id}"
        return f"PASSWORD_{field_name}_{self._instance_id}_{index}"

    def set_credential(self, *args, **kwargs):
        params = self.instance.params or {}
        target_instance = validate_network_config_instance(self._single_instance())
        credential = self.credential or {}
        data = {
            "username": credential.get("username", credential.get("user", "")),
            "password": "${" + self._secret_env_name("password") + "}",
            "port": credential.get("port") or target_instance.get("port") or 22,
            "config_name": params.get("config_name", ""),
            "commands": params.get("commands", ""),
            "need_enable": params.get("need_enable", False),
            "collect_task_id": self.instance.id,
            "target_model_id": target_instance.get("model_id"),
            "target_instance_id": target_instance.get("_id") or target_instance.get("id") or "",
            "device_type": target_instance.get("device_type"),
            "callback_subject": "receive_config_file_result",
        }
        if params.get("need_enable"):
            data["enable_password"] = "${" + self._secret_env_name("enable_password") + "}"
        if credential.get("credential_id"):
            data["credential_id"] = credential.get("credential_id")
        return data

    def env_config(self, *args, **kwargs):
        if not self.credential:
            return {}
        env = {self._secret_env_name("password"): self.credential.get("password", "")}
        if (self.instance.params or {}).get("need_enable"):
            env[self._secret_env_name("enable_password")] = self.credential.get("enable_password", "")
        return env
```

- [ ] **Step 4: Run node params tests to verify GREEN**

Run the same `pytest` command from Step 2.

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add server/apps/cmdb/node_configs/network_config_file.py server/apps/cmdb/tests/test_network_config_file_node_params.py
git commit -m "feat: 下发网络设备配置采集参数"
```

---

## Task 4: Supported Brands API

**Files:**
- Modify: `server/apps/cmdb/views/collect.py`
- Test: `server/apps/cmdb/tests/test_network_config_file_views.py`

- [ ] **Step 1: Write failing API test**

```python
# server/apps/cmdb/tests/test_network_config_file_views.py
from rest_framework.test import APIRequestFactory

from apps.cmdb.views.collect import CollectModelViewSet


def test_network_config_file_supported_brands_returns_options():
    request = APIRequestFactory().get("/cmdb/api/collect/network_config_file_supported_brands/")
    view = CollectModelViewSet.as_view({"get": "network_config_file_supported_brands"})

    response = view(request)

    assert response.status_code == 200
    assert {"label": "Cisco", "device_type": "cisco_ios"} in response.data["items"]
```

- [ ] **Step 2: Run view test to verify RED**

Run:

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_network_config_file_views.py
```

Expected: FAIL because the action does not exist.

- [ ] **Step 3: Add DRF action**

In `server/apps/cmdb/views/collect.py`, import:

```python
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.cmdb.services.network_config_file_policy import get_supported_brand_options
```

Add to `CollectModelViewSet`:

```python
    @action(methods=["get"], detail=False, url_path="network_config_file_supported_brands")
    def network_config_file_supported_brands(self, request):
        return Response({"items": get_supported_brand_options()})
```

- [ ] **Step 4: Run view test to verify GREEN**

Run the same `pytest` command from Step 2.

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

```bash
git add server/apps/cmdb/views/collect.py server/apps/cmdb/tests/test_network_config_file_views.py
git commit -m "feat: 提供网络配置采集支持品牌接口"
```

---

## Task 5: Stargazer Netmiko Plugin Policy

**Files:**
- Create: `agents/stargazer/plugins/inputs/network_config_file/constants.py`
- Test: `agents/stargazer/tests/test_network_config_file_info.py`

- [ ] **Step 1: Write failing tests for command validation and output merge**

```python
# agents/stargazer/tests/test_network_config_file_info.py
import pytest

from plugins.inputs.network_config_file.network_config_file_info import (
    NetworkConfigFileInfo,
    validate_safe_command,
)


def test_validate_safe_command_allows_display_saved_configuration():
    assert validate_safe_command("display saved-configuration") == "display saved-configuration"


@pytest.mark.parametrize("command", ["reload", "configure terminal", "write erase", "delete flash:/x"])
def test_validate_safe_command_rejects_dangerous_commands(command):
    with pytest.raises(ValueError, match="高危"):
        validate_safe_command(command)


def test_merge_outputs_keeps_command_boundaries():
    merged = NetworkConfigFileInfo.merge_command_outputs(
        [
            {"command": "show running-config", "output": "line1"},
            {"command": "show version", "output": "line2"},
        ]
    )

    assert "===== command: show running-config =====" in merged
    assert "line1" in merged
    assert "===== command: show version =====" in merged
    assert "line2" in merged
```

- [ ] **Step 2: Run Stargazer test to verify RED**

Run:

```bash
cd agents/stargazer && uv run pytest -q tests/test_network_config_file_info.py
```

Expected: FAIL because plugin module does not exist.

- [ ] **Step 3: Implement constants and pure helpers**

Create `agents/stargazer/plugins/inputs/network_config_file/constants.py`:

```python
DANGEROUS_EXACT_COMMANDS = {"conf t", "write erase"}
DANGEROUS_COMMAND_PREFIXES = {
    "configure",
    "reload",
    "reboot",
    "reset",
    "delete",
    "erase",
    "format",
    "copy",
    "scp",
    "tftp",
    "ftp",
    "install",
    "upgrade",
    "commit",
    "save",
    "shutdown",
    "undo",
    "set",
}

SUPPORTED_DEVICE_TYPES = {"huawei", "hp_comware", "cisco_ios", "juniper_junos", "f5_tmsh", "fortinet"}

DEVICE_TYPE_DISABLE_PAGING = {
    "cisco_ios": "terminal length 0",
    "hp_comware": "screen-length disable",
    "huawei": "screen-length 0 temporary",
}

LARGE_OUTPUT_COMMANDS = (
    "display current-configuration",
    "display saved-configuration",
    "display version",
    "show running-config",
    "show startup-config",
    "show tech",
    "show version",
)

PAGER_PROMPT_PATTERNS = (
    r"----\s*[Mm]ore\s*----",
    r"----more----",
    r"--[Mm]ore--",
    r"\(q\s+to\s+quit\)",
)

COMMAND_ERROR_PATTERNS = (
    "invalid input",
    "unknown command",
    "ambiguous command",
    "incomplete command",
    "unrecognized command",
)
```

Create `agents/stargazer/plugins/inputs/network_config_file/__init__.py` as an empty file.

Create the initial helper section in `agents/stargazer/plugins/inputs/network_config_file/network_config_file_info.py`:

```python
import re

from plugins.inputs.network_config_file.constants import (
    DANGEROUS_COMMAND_PREFIXES,
    DANGEROUS_EXACT_COMMANDS,
)


def validate_safe_command(command: str) -> str:
    normalized = " ".join(str(command or "").strip().split())
    lowered = normalized.lower()
    if not lowered:
        raise ValueError("采集命令不能为空")
    if lowered in DANGEROUS_EXACT_COMMANDS:
        raise ValueError(f"采集命令存在高危操作: {normalized}")
    first_word = re.split(r"\s+", lowered, maxsplit=1)[0]
    if first_word in DANGEROUS_COMMAND_PREFIXES:
        raise ValueError(f"采集命令存在高危操作: {normalized}")
    return normalized


class NetworkConfigFileInfo:
    @staticmethod
    def merge_command_outputs(results: list[dict]) -> str:
        sections = []
        for item in results:
            sections.append(f"===== command: {item.get('command', '')} =====\n{item.get('output', '')}")
        return "\n\n".join(sections)
```

- [ ] **Step 4: Run pure plugin tests to verify GREEN**

Run the same `pytest` command from Step 2.

Expected: PASS.

- [ ] **Step 5: Commit Task 5**

```bash
git add agents/stargazer/plugins/inputs/network_config_file agents/stargazer/tests/test_network_config_file_info.py
git commit -m "feat: 添加网络配置采集命令策略"
```

---

## Task 6: Stargazer Netmiko Execution and Callback Payload

**Files:**
- Modify: `agents/stargazer/pyproject.toml`
- Modify: `agents/stargazer/plugins/inputs/network_config_file/plugin.yml`
- Modify: `agents/stargazer/plugins/inputs/network_config_file/network_config_file_info.py`
- Test: `agents/stargazer/tests/test_network_config_file_info.py`

- [ ] **Step 1: Add failing tests with fake Netmiko connection**

Append to `agents/stargazer/tests/test_network_config_file_info.py`:

```python
import base64


class FakeNetConnect:
    def __init__(self):
        self.enabled = False
        self.commands = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def enable(self):
        self.enabled = True

    def disable_paging(self, command=None):
        self.commands.append(command)

    def send_command(self, command, **kwargs):
        self.commands.append(command)
        return f"output for {command}"


def test_collect_builds_success_payload(monkeypatch):
    fake = FakeNetConnect()
    monkeypatch.setattr(
        "plugins.inputs.network_config_file.network_config_file_info.ConnectHandler",
        lambda **kwargs: fake,
    )
    plugin = NetworkConfigFileInfo(
        {
            "host": "10.0.0.1",
            "username": "admin",
            "password": "secret",
            "enable_password": "enable-secret",
            "need_enable": "true",
            "device_type": "cisco_ios",
            "commands": "show running-config\nshow version",
            "config_name": "running-config",
            "collect_task_id": "42",
            "target_model_id": "switch",
            "target_instance_id": "101",
        }
    )

    result = plugin.list_all_resources()

    assert result["success"] is True
    payload = result["result"]
    assert payload["status"] == "success"
    assert payload["file_name"] == "running-config"
    decoded = base64.b64decode(payload["content_base64"]).decode()
    assert "output for show running-config" in decoded
    assert "output for show version" in decoded
    assert fake.enabled is True


def test_collect_returns_error_when_one_command_fails(monkeypatch):
    class FailingNetConnect(FakeNetConnect):
        def send_command(self, command, **kwargs):
            if command == "show bad":
                return "Invalid input detected"
            return "ok"

    fake = FailingNetConnect()
    monkeypatch.setattr(
        "plugins.inputs.network_config_file.network_config_file_info.ConnectHandler",
        lambda **kwargs: fake,
    )
    plugin = NetworkConfigFileInfo(
        {
            "host": "10.0.0.1",
            "username": "admin",
            "password": "secret",
            "device_type": "cisco_ios",
            "commands": "show version\nshow bad",
            "config_name": "running-config",
            "collect_task_id": "42",
            "target_model_id": "switch",
            "target_instance_id": "101",
        }
    )

    result = plugin.list_all_resources()

    assert result["success"] is False
    assert "show bad" in result["result"]["cmdb_collect_error"]
    assert "Invalid input" in result["result"]["cmdb_collect_error"]
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
cd agents/stargazer && uv run pytest -q tests/test_network_config_file_info.py
```

Expected: FAIL because `list_all_resources` and Netmiko import are incomplete.

- [ ] **Step 3: Add dependency and plugin.yml**

In `agents/stargazer/pyproject.toml`, add:

```toml
    "netmiko==4.5.0",
```

Create `agents/stargazer/plugins/inputs/network_config_file/plugin.yml`:

```yaml
name: network_config_file
version: "1.0.0"
category: network

metadata:
  display_name: "网络设备配置文件"
  description: "通过 Netmiko 采集网络设备配置命令输出"
  author: "WeOps"
  tags: [network, config-file, netmiko]
  cloud_protocol: false
  model_id: network_config_file

executors:
  protocol:
    type: protocol
    timeout: 60
    collector:
      module: plugins.inputs.network_config_file.network_config_file_info
      class: NetworkConfigFileInfo

default_executor: protocol
```

- [ ] **Step 4: Implement Netmiko collection**

Extend `network_config_file_info.py`:

```python
import base64
import time

try:
    from netmiko import ConnectHandler
except Exception:  # tests may monkeypatch this symbol
    ConnectHandler = None

from plugins.inputs.network_config_file.constants import (
    COMMAND_ERROR_PATTERNS,
    DEVICE_TYPE_DISABLE_PAGING,
    SUPPORTED_DEVICE_TYPES,
)


class NetworkConfigFileInfo:
    def __init__(self, params):
        self.params = params or {}

    @staticmethod
    def merge_command_outputs(results: list[dict]) -> str:
        sections = []
        for item in results:
            sections.append(f"===== command: {item.get('command', '')} =====\n{item.get('output', '')}")
        return "\n\n".join(sections)

    @staticmethod
    def _truthy(value) -> bool:
        if isinstance(value, bool):
            return value
        return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _has_command_error(output: str) -> bool:
        lowered = str(output or "").lower()
        return any(pattern in lowered for pattern in COMMAND_ERROR_PATTERNS)

    def _commands(self) -> list[str]:
        return [validate_safe_command(line) for line in str(self.params.get("commands") or "").splitlines() if line.strip()]

    def _connect_params(self) -> dict:
        device_type = str(self.params.get("device_type") or "").strip()
        if device_type not in SUPPORTED_DEVICE_TYPES:
            raise ValueError(f"不支持的 Netmiko 驱动: {device_type}")
        return {
            "device_type": device_type,
            "ip": self.params.get("host") or self.params.get("connect_ip"),
            "username": self.params.get("username"),
            "password": self.params.get("password"),
            "secret": self.params.get("enable_password") or "",
            "port": int(self.params.get("port") or 22),
            "allow_agent": False,
            "use_keys": False,
            "conn_timeout": int(self.params.get("conn_timeout") or 30),
            "timeout": int(self.params.get("timeout") or 60),
        }

    def _success_payload(self, merged_output: str) -> dict:
        encoded = base64.b64encode(merged_output.encode()).decode()
        config_name = str(self.params.get("config_name") or "").strip()
        return {
            "collect_task_id": self.params.get("collect_task_id"),
            "instance_id": self.params.get("target_instance_id") or self.params.get("host") or "",
            "instance_name": self.params.get("instance_name") or self.params.get("host") or "",
            "model_id": self.params.get("target_model_id"),
            "file_path": f"network://{config_name}",
            "file_name": config_name,
            "version": str(int(time.time() * 1000)),
            "status": "success",
            "size": len(merged_output.encode()),
            "error": "",
            "content_base64": encoded,
        }

    def list_all_resources(self, need_raw=False):
        del need_raw
        command_results = []
        failures = []
        try:
            commands = self._commands()
            connect_params = self._connect_params()
            if ConnectHandler is None:
                raise RuntimeError("netmiko is required for network config file collection")
            with ConnectHandler(**connect_params) as net_connect:
                if self._truthy(self.params.get("need_enable")):
                    net_connect.enable()
                paging_command = DEVICE_TYPE_DISABLE_PAGING.get(connect_params["device_type"])
                if paging_command:
                    net_connect.disable_paging(command=paging_command)
                for command in commands:
                    started = time.monotonic()
                    try:
                        output = net_connect.send_command(command)
                        duration_ms = int((time.monotonic() - started) * 1000)
                        if self._has_command_error(output):
                            failures.append(f"{command}: {output[:200]}")
                            command_results.append({"command": command, "status": "error", "error": output[:200], "duration_ms": duration_ms})
                            continue
                        command_results.append({"command": command, "status": "success", "output": output, "duration_ms": duration_ms})
                    except Exception as err:
                        duration_ms = int((time.monotonic() - started) * 1000)
                        failures.append(f"{command}: {err}")
                        command_results.append({"command": command, "status": "error", "error": str(err), "duration_ms": duration_ms})

            if failures:
                return {"success": False, "result": {"cmdb_collect_error": "; ".join(failures)[:2000]}}
            return {"success": True, "result": self._success_payload(self.merge_command_outputs(command_results))}
        except Exception as err:
            return {"success": False, "result": {"cmdb_collect_error": str(err)[:2000]}}
```

- [ ] **Step 5: Run plugin tests to verify GREEN**

Run the same `pytest` command from Step 2.

Expected: PASS.

- [ ] **Step 6: Run dependency sync**

Run:

```bash
cd agents/stargazer && uv sync
```

Expected: lockfile updates include Netmiko and dependencies.

- [ ] **Step 7: Commit Task 6**

```bash
git add agents/stargazer/pyproject.toml agents/stargazer/uv.lock agents/stargazer/plugins/inputs/network_config_file agents/stargazer/tests/test_network_config_file_info.py
git commit -m "feat: 实现 Stargazer 网络配置采集插件"
```

---

## Task 7: Web Form and Instance Selection Rules

**Files:**
- Modify: `web/src/app/cmdb/api/collect.ts`
- Modify: `web/src/app/cmdb/constants/professCollection.ts`
- Create: `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/networkConfigFileTask.tsx`
- Modify: `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/page.tsx`

- [ ] **Step 1: Add API helper**

In `web/src/app/cmdb/api/collect.ts`, add:

```typescript
  const getNetworkConfigBrands = () =>
    get('/cmdb/api/collect/network_config_file_supported_brands/');
```

and return it from the hook.

- [ ] **Step 2: Add form constants and command validator**

In `web/src/app/cmdb/constants/professCollection.ts`, add:

```typescript
export const NETWORK_CONFIG_FILE_FORM_INITIAL_VALUES = {
  cycle: CYCLE_OPTIONS.INTERVAL,
  intervalValue: 60,
  timeout: 60,
  needEnable: false,
  credentialPool: [{ port: '22' }],
};

const DANGEROUS_EXACT_COMMANDS = new Set(['conf t', 'write erase']);
const DANGEROUS_COMMAND_PREFIXES = new Set([
  'configure',
  'reload',
  'reboot',
  'reset',
  'delete',
  'erase',
  'format',
  'copy',
  'scp',
  'tftp',
  'ftp',
  'install',
  'upgrade',
  'commit',
  'save',
  'shutdown',
  'undo',
  'set',
]);

export const validateNetworkConfigCommands = (value: string) => {
  const commands = (value || '').split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
  if (!commands.length) {
    return '请输入采集命令';
  }
  const badCommand = commands.find((command) => {
    const lowered = command.toLowerCase().replace(/\s+/g, ' ');
    const firstWord = lowered.split(' ')[0];
    return DANGEROUS_EXACT_COMMANDS.has(lowered) || DANGEROUS_COMMAND_PREFIXES.has(firstWord);
  });
  return badCommand ? `命令存在高危操作：${badCommand}` : '';
};
```

- [ ] **Step 3: Create dedicated form**

Create `networkConfigFileTask.tsx` by adapting `configFileTask.tsx`:

```tsx
'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Checkbox, Form, Input, Spin, Tooltip } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
import { useLocale } from '@/context/locale';
import { useUserInfoContext } from '@/context/userInfo';
import BaseTaskForm, { BaseTaskRef } from './baseTask';
import CredentialPoolEditor from './credentialPoolEditor';
import { useTaskForm, getCleanupFormValues, getCycleFormValues } from '../hooks/useTaskForm';
import { TreeNode, ModelItem } from '@/app/cmdb/types/autoDiscovery';
import {
  NETWORK_CONFIG_FILE_FORM_INITIAL_VALUES,
  PASSWORD_PLACEHOLDER,
  validateNetworkConfigCommands,
} from '@/app/cmdb/constants/professCollection';
import { buildCredentialPool, formatTaskValues, normalizeCredentialPool, trimFormString } from '../hooks/formatTaskValues';
import useAssetManageStore from '@/app/cmdb/store/useAssetManage';
import { useCollectApi } from '@/app/cmdb/api';

interface Props {
  onClose: () => void;
  onSuccess?: () => void;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  editId?: number | null;
}

const NetworkConfigFileTask: React.FC<Props> = ({ onClose, onSuccess, selectedNode, modelItem, editId }) => {
  const localeContext = useLocale();
  const { selectedGroup } = useUserInfoContext();
  const baseRef = useRef<BaseTaskRef>(null as any);
  const copyTaskData = useAssetManageStore((state) => state.copyTaskData);
  const collectApi = useCollectApi();
  const [brandTip, setBrandTip] = useState('当前支持厂商：华为/Huawei、H3C/HP Comware、Cisco、Juniper、F5、Fortinet');
  const { model_id: modelId } = modelItem;
  const initialFormValues = useMemo(() => ({
    ...NETWORK_CONFIG_FILE_FORM_INITIAL_VALUES,
    organization: selectedGroup ? [Number(selectedGroup.id)] : [],
  }), [selectedGroup]);

  useEffect(() => {
    collectApi.getNetworkConfigBrands?.().then((data: any) => {
      const labels = (data?.items || []).map((item: any) => item.label).filter(Boolean);
      if (labels.length) {
        setBrandTip(`当前支持厂商：${labels.join('、')}`);
      }
    });
  }, [collectApi]);

  const { form, loading, submitLoading, fetchTaskDetail, formatCycleValue, onFinish } = useTaskForm({
    modelId,
    editId,
    initialValues: initialFormValues,
    onSuccess,
    onClose,
    formatValues: (values) => {
      const baseData = formatTaskValues({ values, baseRef, selectedNode, modelItem, modelId, formatCycleValue });
      const selectedData = baseRef.current?.selectedData || [];
      return {
        ...baseData,
        ip_range: '',
        instances: selectedData,
        credential: buildCredentialPool(values.credentialPool, (item) => {
          const credential: Record<string, any> = {};
          const username = trimFormString(item.username);
          const password = trimFormString(item.password);
          const enablePassword = trimFormString(item.enable_password);
          if (item.credential_id) credential.credential_id = item.credential_id;
          if (username !== undefined) credential.username = username;
          if (password && password !== PASSWORD_PLACEHOLDER) credential.password = password;
          if (values.needEnable && enablePassword && enablePassword !== PASSWORD_PLACEHOLDER) credential.enable_password = enablePassword;
          if (item.port !== undefined && item.port !== null && item.port !== '') credential.port = item.port;
          return credential;
        }),
        params: {
          config_name: values.configName?.trim(),
          commands: values.commands,
          need_enable: Boolean(values.needEnable),
        },
      };
    },
  });

  useEffect(() => {
    const initForm = async () => {
      if (copyTaskData) {
        baseRef.current?.initCollectionType(copyTaskData.instances, 'asset');
        form.setFieldsValue({ ...initialFormValues, ...copyTaskData, taskName: '', configName: copyTaskData.params?.config_name, commands: copyTaskData.params?.commands, needEnable: copyTaskData.params?.need_enable });
      } else if (editId) {
        const values = await fetchTaskDetail(editId);
        if (!values) return;
        baseRef.current?.initCollectionType(values.instances, 'asset');
        form.setFieldsValue({
          ...values,
          ...getCleanupFormValues(values),
          ...getCycleFormValues(values),
          taskName: values.name,
          accessPointId: values.access_point?.[0]?.id,
          organization: values.team || [],
          configName: values.params?.config_name,
          commands: values.params?.commands,
          needEnable: values.params?.need_enable,
          credentialPool: normalizeCredentialPool(values.credential).map((item) => ({ ...item, password: PASSWORD_PLACEHOLDER, enable_password: PASSWORD_PLACEHOLDER })),
        });
      } else {
        baseRef.current?.initCollectionType([], 'asset');
        form.setFieldsValue(initialFormValues);
      }
    };
    initForm();
  }, [copyTaskData, editId, fetchTaskDetail, form, initialFormValues]);

  return (
    <Spin spinning={loading}>
      <Form form={form} layout="horizontal" labelCol={{ span: localeContext.locale === 'en' ? 6 : 5 }} onFinish={onFinish} initialValues={initialFormValues}>
        <BaseTaskForm ref={baseRef} nodeId={selectedNode.id} modelItem={modelItem} onClose={onClose} submitLoading={submitLoading} instPlaceholder="选择网络设备" assetOptionLabel="选择网络设备" timeoutProps={{ min: 1, defaultValue: 60, addonAfter: '秒' }}>
          <Alert type="info" showIcon className="mb-4" message={<span>{brandTip} <Tooltip title="缺少厂商或厂商不支持的实例不可选择"><InfoCircleOutlined /></Tooltip></span>} />
          <Form.Item label="配置名称" name="configName" rules={[{ required: true, message: '请输入配置名称' }]}>
            <Input autoComplete="off" placeholder="例如 running-config" />
          </Form.Item>
          <Form.Item label="采集命令" name="commands" rules={[{ validator: async (_, value) => { const error = validateNetworkConfigCommands(value); if (error) throw new Error(error); } }]}>
            <Input.TextArea autoComplete="off" rows={6} placeholder={'每行一条命令，例如：\nshow running-config\nshow version'} />
          </Form.Item>
          <Form.Item name="needEnable" valuePropName="checked">
            <Checkbox>需要特权模式</Checkbox>
          </Form.Item>
          <Form.Item name="credentialPool">
            <CredentialPoolEditor credentialShape="network_config_file" editMode={Boolean(editId)} />
          </Form.Item>
        </BaseTaskForm>
      </Form>
    </Spin>
  );
};

export default NetworkConfigFileTask;
```

- [ ] **Step 4: Add form routing**

In `collection/profess/page.tsx`, import and render `NetworkConfigFileTask` when `modelItem.model_id === 'network_config_file'`.

- [ ] **Step 5: Update instance disabling in BaseTaskForm**

Extend `BaseTaskForm` selection table row logic so when `modelItem.model_id === 'network_config_file'`, rows are disabled if `brand` is empty or unsupported. Use `modelItem.supported_brands` if available, otherwise rely on backend validation and show the tip.

- [ ] **Step 6: Run web lint/type-check**

Run:

```bash
cd web && PATH=/Users/windyzhao/.nvm/versions/node/v24.15.0/bin:$PATH pnpm lint && PATH=/Users/windyzhao/.nvm/versions/node/v24.15.0/bin:$PATH pnpm type-check
```

Expected: PASS.

- [ ] **Step 7: Commit Task 7**

```bash
git add web/src/app/cmdb/api/collect.ts web/src/app/cmdb/constants/professCollection.ts 'web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/networkConfigFileTask.tsx' 'web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/page.tsx' 'web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/baseTask.tsx'
git commit -m "feat: 添加网络配置采集前端表单"
```

---

## Task 8: Integration Verification and Hardening

**Files:**
- Any files touched by Tasks 1-7.

- [ ] **Step 1: Run focused CMDB tests**

Run:

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_network_config_file_policy.py apps/cmdb/tests/test_network_config_file_serializer.py apps/cmdb/tests/test_network_config_file_node_params.py apps/cmdb/tests/test_network_config_file_views.py apps/cmdb/tests/test_config_file_service_pure.py
```

Expected: PASS.

- [ ] **Step 2: Run Stargazer tests**

Run:

```bash
cd agents/stargazer && uv run pytest -q tests/test_network_config_file_info.py tests/test_api_http_layer.py
```

Expected: PASS.

- [ ] **Step 3: Run frontend checks**

Run:

```bash
cd web && PATH=/Users/windyzhao/.nvm/versions/node/v24.15.0/bin:$PATH pnpm lint && PATH=/Users/windyzhao/.nvm/versions/node/v24.15.0/bin:$PATH pnpm type-check
```

Expected: PASS.

- [ ] **Step 4: Verify no sensitive output logging**

Run:

```bash
rg -n "content_base64|password|enable_password|output" agents/stargazer/plugins/inputs/network_config_file server/apps/cmdb/node_configs/network_config_file.py
```

Expected: any matches are in payload construction, env placeholder construction, or explicit forbidden logging tests; there must be no logger call that writes password, enable password, full output, or base64 content.

- [ ] **Step 5: Run final git diff review**

Run:

```bash
git diff --stat
git diff --check
```

Expected: no whitespace errors; diff only includes files required by this plan and dependency lockfile updates.

- [ ] **Step 6: Final commit**

If previous task commits were not made, create one final commit:

```bash
git add server/apps/cmdb agents/stargazer web/src/app/cmdb
git commit -m "feat: 支持网络设备配置文件采集"
```

---

## Requirements Checklist

- [ ] Existing network device instances only.
- [ ] Only `switch/router/firewall/loadbalance` supported.
- [ ] Empty `brand` rejected by frontend and backend.
- [ ] Unsupported `brand` rejected by frontend and backend.
- [ ] Brand maps to Netmiko `device_type`.
- [ ] Supported brand tip displayed.
- [ ] Commands split by newline and executed one by one.
- [ ] Dangerous commands blocked in frontend, CMDB backend, and Stargazer.
- [ ] Optional enable mode is explicit and requires `enable_password`.
- [ ] Netmiko output is merged into one config file.
- [ ] Any command failure produces overall `error` and no success version.
- [ ] Successful collection uses `receive_config_file_result` payload shape.
- [ ] Logs do not expose password, enable password, full output, or base64 content.
- [ ] Final verification uses verification-before-completion before any completion claim.

## specs: 2026-06-30-cmdb-network-device-config-collection-design.md

## 背景

当前 CMDB 已支持主机配置文件采集：CMDB 创建采集任务，Stargazer 执行采集，结果通过 `receive_config_file_result` 回调进入 `ConfigFileService`，最终以 `ConfigFileVersion` 归档并支持版本比对。

本设计扩展同一条配置文件版本链路，使 CMDB 支持对网络设备执行只读配置命令，并把命令输出作为配置文件版本挂到已有网络设备实例下。驱动在 Stargazer 侧实现，优先使用 Netmiko。

## 目标

- 支持对已有网络设备实例采集配置内容。
- 复用现有配置文件版本归档、diff、订阅触发和任务闭环能力。
- Stargazer 使用 Netmiko 连接网络设备，逐条执行用户配置的只读命令。
- 支持多行命令输入：每行一条命令，空行忽略，按顺序执行，最终合并为一份配置内容。
- 支持可选 enable/特权模式，默认不提权，必须显式启用。
- 前端、CMDB 后端、Stargazer 执行端都要有命令安全校验。
- 日志不得暴露密码、enable 密码或完整命令输出。

## 非目标

- 不做网络设备发现或自动创建设备实例。
- 不支持非内置网络设备模型。
- 不承诺 Netmiko 支持所有品牌、型号和命令。
- 不执行配置变更命令，不使用 `send_config_set`。
- 不把多条命令拆成多份配置版本；第一版合并为一份配置文件内容。

## 支持范围

MVP 只支持以下 CMDB 模型下的实例：

- `switch`
- `router`
- `firewall`
- `loadbalance`

这些模型在 `server/apps/cmdb/support-files/model_config.xlsx` 中均包含统一字段：

- `ip_addr`：管理 IP
- `port`：管理端口
- `brand`：厂商
- `model`：型号
- `soid`：sysObjectID

前端实例选择器只允许选择这四类模型下的实例。实例必须满足：

- `brand` 非空。
- `brand` 可映射到受支持的 Netmiko `device_type`。

后端保存任务时必须再次校验这些条件，防止 API 绕过前端约束。

## 品牌与驱动映射

采集执行依赖 Netmiko 的 `device_type`，不是直接依赖展示用品牌。CMDB 使用实例字段 `brand` 推导 `device_type`。

第一版内置映射建议如下：

| brand 归一化值 | Netmiko device_type |
| --- | --- |
| 华为 / Huawei | `huawei` |
| H3C / HP Comware / Hewlett-Packard | `hp_comware` |
| Cisco | `cisco_ios` |
| Juniper | `juniper_junos` |
| F5 | `f5_tmsh` |
| Fortinet | `fortinet` |

前端在任务表单中展示小提示：

> 当前支持厂商：华为/Huawei、H3C/HP Comware、Cisco、Juniper、F5、Fortinet。不在支持范围内的设备暂不支持配置采集。

支持品牌映射由 CMDB 后端提供，前端通过接口获取后渲染提示和禁选逻辑，避免前后端各维护一份枚举导致不一致。Stargazer 保留同名执行端常量作为最终执行校验，CMDB 下发的 `device_type` 必须命中 Stargazer 支持列表。

如果实例 `brand` 为空，前端禁选并提示：

> 该设备缺少厂商字段，无法匹配采集驱动，请先补充厂商。

如果实例 `brand` 不在支持范围内，前端禁选并提示：

> 当前厂商暂不支持网络配置采集。

## 任务参数

网络设备配置采集任务需要以下业务参数：

- `config_name`：配置名称，用户手动填写，例如 `running-config`。
- `commands`：采集命令，多行文本，每行一条命令。
- `need_enable`：是否需要 enable/特权模式，默认 `false`。
- `collect_task_id`：CMDB 采集任务 ID。
- `target_model_id`：目标实例模型，例如 `switch`。
- `target_instance_id`：目标实例 ID。
- `callback_subject`：固定为 `receive_config_file_result`。

由 CMDB 根据实例与凭据补齐的执行参数：

- `host` 或 `hosts`：目标设备管理 IP。
- `port`：优先使用凭据端口，其次使用实例 `port`，两者都为空时默认 `22`。
- `username`：SSH 用户名。
- `password`：SSH 密码，使用现有加密字段和环境变量占位机制下发。
- `enable_password`：特权密码，仅当 `need_enable=true` 时需要和下发。
- `device_type`：由实例 `brand` 推导出的 Netmiko 驱动。

## 前端交互

任务表单沿用配置文件采集的新增任务抽屉体验，但目标对象切换为网络设备实例。

表单字段：

- 任务名称。
- 周期。
- 组织。
- 接入点。
- 选择网络设备实例。
- 配置名称。
- 采集命令，多行 textarea，每行一条命令。
- 是否需要特权模式。
- SSH 凭据；当启用特权模式时展示并要求特权密码。

选择实例时：

- 仅展示或允许选择 `switch/router/firewall/loadbalance`。
- `brand` 为空的实例置灰不可选。
- `brand` 不支持的实例置灰不可选。
- 批量选择时跳过不可选实例，并提示跳过数量和原因。

命令输入时：

- 前端按换行切分命令，空行忽略。
- 每条命令都进行危险命令提示。
- 命中危险命令时禁止保存，并明确标出问题行。

## 命令安全

命令安全必须有三层校验：

1. 前端输入提示和保存拦截。
2. CMDB 后端保存任务时校验。
3. Stargazer 执行前最终校验。

第一版采用黑名单策略，拦截明显危险命令。黑名单匹配应优先按命令首词和明确危险组合判断，避免误伤只读命令。

建议拦截示例：

- `configure`
- `conf t`
- `reload`
- `reboot`
- `reset`
- `delete`
- `erase`
- `format`
- `write erase`
- `copy`
- `scp`
- `tftp`
- `ftp`
- `install`
- `upgrade`
- `commit`
- `save`
- `shutdown`
- `undo`
- `set`

注意：不能简单按全文包含匹配。例如 `display saved-configuration` 是只读查看命令，不应因包含 `save` 字符串被拦截。

## Stargazer 执行设计

Stargazer 新增网络设备配置采集插件，例如：

- `agents/stargazer/plugins/inputs/network_config_file/plugin.yml`
- `agents/stargazer/plugins/inputs/network_config_file/network_config_file_info.py`

执行流程：

1. 校验 `device_type`、`config_name`、`commands`、凭据和目标 IP。
2. 按换行切分 `commands`，空行忽略。
3. 对每条命令执行危险命令校验。
4. 使用 Netmiko `ConnectHandler` 建立连接。
5. 如果 `need_enable=true`，调用 `net_connect.enable()`。
6. 根据 `device_type` 执行关闭分页命令。
7. 按顺序逐条执行命令。
8. 每条命令记录结构化执行结果：`command`、`status`、`output`、`error`、`duration_ms`。
9. 全部成功时合并输出，构造配置文件回调 payload。
10. 任一命令失败时整体 `status=error`，返回错误详情，不写成功版本。

分页和大输出处理可参考已有 AutoMate 项目做法：

- 为常见 `device_type` 维护关闭分页命令。
- 大输出命令或 `pattern not detected` 时，兜底使用 `send_command_timing`。
- 续页次数设置上限，例如 `MAX_PAGER_PAGES`，避免无限读取。
- 清理分页提示符后再合并内容。

建议维护常量：

- `BRAND_DEVICE_TYPE_MAP`
- `DEVICE_TYPE_DISABLE_PAGING`
- `LARGE_OUTPUT_COMMANDS`
- `PAGER_PROMPT_PATTERNS`
- `COMMAND_ERROR_PATTERNS`
- `DANGEROUS_COMMAND_RULES`

## 逐条命令结果与合并格式

每条命令独立执行，独立记录结果。采集完成后合并为一份文本内容。

合并格式：

```text
===== command: show running-config =====
<output>

===== command: show version =====
<output>
```

整体状态规则：

- 全部命令成功：`status=success`，合并内容 base64 编码后回调。
- 任一命令失败：`status=error`，错误详情包含失败命令和逐条摘要，不生成成功版本。

失败类型包括：

- 连接失败。
- 认证失败。
- enable 失败。
- 命令超时。
- Netmiko 执行异常。
- 输出命中设备错误提示，例如 `Invalid input`、`Unknown command`、`Ambiguous command`、`Incomplete command`。

## 回调与版本归档

继续复用 CMDB 现有 `receive_config_file_result` 回调和 `ConfigFileService.process_collect_result`。

成功回调建议字段：

```json
{
  "collect_task_id": 1001,
  "instance_id": "<网络设备实例标识>",
  "instance_name": "<网络设备实例名或管理IP>",
  "model_id": "switch",
  "file_path": "network://running-config",
  "file_name": "running-config",
  "version": "1780000000000",
  "status": "success",
  "size": 12345,
  "error": "",
  "content_base64": "<base64>"
}
```

其中：

- `file_name` 使用用户填写的 `config_name`。
- `file_path` 使用稳定伪路径 `network://<config_name>`，确保同一实例同一配置名称形成连续版本线。
- `model_id` 使用目标实例模型 ID。

失败回调：

- `status=error`。
- `content_base64=""`。
- `error` 包含简洁错误摘要，最大长度 2000 字符，超出后截断并追加截断标记。
- 可在错误摘要中包含逐条命令状态，但不包含完整输出。

## 日志与敏感信息

日志只能记录：

- `task_id`
- `host`
- `model_id`
- `device_type`
- `command`
- `status`
- `duration_ms`
- 错误类型和简短错误信息

日志禁止记录：

- `password`
- `enable_password`
- 完整命令输出
- `content_base64`
- 凭据池明文

完整输出只走回调 payload，最终由 CMDB 配置文件版本内容保存机制处理。

## 错误处理

CMDB 保存阶段：

- 目标模型不在支持范围内：拒绝保存。
- 实例 `brand` 为空：拒绝保存。
- 实例 `brand` 不支持：拒绝保存。
- 命令为空：拒绝保存。
- 命中危险命令：拒绝保存。
- `need_enable=true` 但未配置特权密码：拒绝保存。

Stargazer 执行阶段：

- 参数缺失：返回 `error`。
- 连接或认证失败：返回 `error`。
- enable 失败：返回 `error`。
- 单条命令失败：记录本条失败，继续执行剩余命令，最终整体返回 `error`。
- 所有命令成功：返回 `success`。

继续执行剩余命令的原因是提升诊断价值；整体仍保持严格，不把半成功结果写为成功版本。

## 测试策略

CMDB 后端测试：

- 支持模型校验：仅允许 `switch/router/firewall/loadbalance`。
- 实例 `brand` 为空时拒绝保存。
- 不支持品牌时拒绝保存。
- 支持品牌能正确映射 `device_type`。
- 多行命令切分和危险命令校验。
- `config_name` 生成稳定 `network://<config_name>` 伪路径。

Stargazer 测试：

- `brand/device_type` 支持校验。
- Netmiko 连接参数构造不泄露敏感信息。
- `need_enable=true` 时调用 enable。
- 多命令逐条执行并合并输出。
- 单条命令失败时整体失败，但保留逐条摘要。
- 分页提示清理和大输出兜底。
- 日志不包含密码、enable 密码、完整输出和 base64 内容。

前端测试：

- 实例选择器禁选 `brand` 为空实例。
- 实例选择器禁选不支持品牌实例。
- 支持品牌 tip 展示。
- 命令 textarea 按行校验危险命令。
- 启用特权模式时展示并要求特权密码。
