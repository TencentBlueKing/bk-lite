# CMDB 长周期任务首次采集加速 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为循环周期不小于 15 分钟的 CMDB Telegraf 采集任务增加一次服务端主动 Stargazer 触发，使正常链路下任务详情在保存后 5 分钟内出现真实执行结果和原始数据。

**Architecture:** 用纯策略组件判断资格、语义变更并生成基于服务端密钥的 HMAC-SHA256 配置指纹；用独立客户端把节点参数工厂生成的同源参数提交给 Stargazer；由绑定式 Celery 任务完成最新配置复核和有界重试。`CollectModelService` 仅在事务提交后投递快速触发，并继续安排原有约 4 分钟延迟同步，Telegraf 的长期周期不变。

**Tech Stack:** Python 3.12、Django 4.2、Celery、requests、pytest/pytest-django、现有 `NodeParamsFactory`、Stargazer `/api/collect/collect_info`。

## Global Constraints

- 只处理循环周期不小于 15 分钟的非 K8S、非配置文件专用 Telegraf/Stargazer 采集任务。
- 新建任务，以及采集对象、凭据、插件参数、超时或长周期语义变化时触发；名称、组织、过期天数和清理策略变化不触发。
- 本期不新增数据库字段、迁移、前端状态或新的节点侧执行入口。
- 快速触发发生在事务提交后，失败不得回滚任务、删除 Telegraf 配置或改变用户周期。
- 单次保存最多投递一个快速触发任务；网络异常、超时和 5xx 最多执行 3 次请求，4xx 不重试。
- 请求、日志、Celery 参数和错误消息不得包含密码、Token、完整凭据或完整响应正文。
- 数据库访问统一使用 Django ORM，禁止 raw SQL、`.raw()`、`RawSQL` 和 `cursor.execute`。
- 新功能按 TDD 红—绿—重构推进；触及代码覆盖率不低于 75%。
- 设计依据：`docs/superpowers/specs/2026-07-17-cmdb-first-collection-design.md`。

## File Structure

- Create: `server/apps/cmdb/services/first_collection_policy.py` — 资格、规范化、变更分类和指纹。
- Create: `server/apps/cmdb/services/stargazer_collect_trigger.py` — 单次 HTTP 提交和错误分类。
- Create: `server/apps/cmdb/tests/test_first_collection_policy.py`
- Create: `server/apps/cmdb/tests/test_stargazer_collect_trigger.py`
- Create: `server/apps/cmdb/tests/test_first_collection_task.py`
- Create: `server/apps/cmdb/tests/test_collect_service_first_collection.py`
- Modify: `server/apps/cmdb/constants/constants.py:802-805`
- Modify: `server/envs/.env.example`
- Modify: `server/apps/cmdb/tasks/celery_tasks.py:1-130`
- Modify: `server/apps/cmdb/tasks/__init__.py:6-20`
- Modify: `server/apps/cmdb/services/collect_service.py:30-41,365-411,438-540`

---

### Task 1: 首次采集资格、变更判断与配置指纹

**Files:**
- Create: `server/apps/cmdb/services/first_collection_policy.py`
- Create: `server/apps/cmdb/tests/test_first_collection_policy.py`
- Modify: `server/apps/cmdb/constants/constants.py:802-805`
- Modify: `server/envs/.env.example`

**Interfaces:**
- Consumes: `CollectPluginTypes` 和任务的调度、对象、凭据、插件字段。
- Produces: `FirstCollectionPolicy.is_eligible(task) -> bool`、`fingerprint(task) -> str`、`changed_fields(old_task, new_task) -> tuple[str, ...]`、`should_trigger_update(old_task, new_task) -> bool`。

- [ ] **Step 1: 写失败测试**

创建 `server/apps/cmdb/tests/test_first_collection_policy.py`：

```python
import types

import pytest

from apps.cmdb.constants.constants import CollectPluginTypes
from apps.cmdb.services.first_collection_policy import FirstCollectionPolicy

pytestmark = pytest.mark.unit


def task(**overrides):
    values = {
        "id": 7,
        "is_interval": True,
        "cycle_value_type": "cycle",
        "cycle_value": "30",
        "task_type": CollectPluginTypes.HOST,
        "driver_type": "snmp",
        "model_id": "host",
        "instances": [{"inst_name": "host-1", "ip_addr": "10.0.0.1"}],
        "ip_range": "",
        "access_point": [{"id": "node-1"}],
        "plugin_id": "host_info",
        "params": {"port": 22},
        "timeout": 60,
        "decrypt_credentials": {"username": "root", "password": "secret"},
        "name": "任务",
        "team": [1],
        "expire_days": 7,
        "data_cleanup_strategy": "no_cleanup",
    }
    values.update(overrides)
    return types.SimpleNamespace(**values)


@pytest.mark.parametrize(
    "overrides",
    [
        {"is_interval": False},
        {"cycle_value_type": "timing"},
        {"cycle_value": "14"},
        {"cycle_value": "bad"},
        {"task_type": CollectPluginTypes.K8S},
        {"task_type": CollectPluginTypes.CONFIG_FILE},
    ],
)
def test_ineligible_tasks_are_rejected(overrides):
    assert FirstCollectionPolicy.is_eligible(task(**overrides)) is False


def test_threshold_task_is_eligible():
    assert FirstCollectionPolicy.is_eligible(task(cycle_value="15")) is True


def test_equivalent_dict_order_has_same_fingerprint():
    first = task(params={"port": 22, "options": {"b": 2, "a": 1}})
    second = task(params={"options": {"a": 1, "b": 2}, "port": 22})
    assert FirstCollectionPolicy.fingerprint(first) == FirstCollectionPolicy.fingerprint(second)


def test_fingerprint_is_irreversible():
    result = FirstCollectionPolicy.fingerprint(task())
    assert len(result) == 64
    assert "secret" not in result


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("instances", [{"inst_name": "host-2"}]),
        ("access_point", [{"id": "node-2"}]),
        ("plugin_id", "host_info_v2"),
        ("params", {"port": 2222}),
        ("timeout", 90),
        ("cycle_value", "60"),
        ("decrypt_credentials", {"username": "root", "password": "new-secret"}),
    ],
)
def test_source_change_triggers(field, value):
    old = task()
    new = task(**{field: value})
    assert field in FirstCollectionPolicy.changed_fields(old, new)
    assert FirstCollectionPolicy.should_trigger_update(old, new) is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "新名称"),
        ("team", [2]),
        ("expire_days", 30),
        ("data_cleanup_strategy", "delete"),
    ],
)
def test_governance_change_does_not_trigger(field, value):
    assert FirstCollectionPolicy.should_trigger_update(task(), task(**{field: value})) is False


def test_update_to_short_cycle_does_not_trigger():
    assert FirstCollectionPolicy.should_trigger_update(task(), task(cycle_value="5")) is False
```

- [ ] **Step 2: 运行测试确认红灯**

```bash
cd server && .venv/bin/pytest apps/cmdb/tests/test_first_collection_policy.py -q
```

Expected: FAIL，包含 `ModuleNotFoundError: No module named 'apps.cmdb.services.first_collection_policy'`。

- [ ] **Step 3: 实现最小策略组件**

创建 `server/apps/cmdb/services/first_collection_policy.py`：

```python
import hashlib
import hmac
import json
from typing import Any

from django.conf import settings

from apps.cmdb.constants.constants import CollectPluginTypes


class FirstCollectionPolicy:
    THRESHOLD_MINUTES = 15
    FINGERPRINT_FIELDS = (
        "instances",
        "ip_range",
        "access_point",
        "plugin_id",
        "params",
        "task_type",
        "driver_type",
        "model_id",
        "timeout",
        "is_interval",
        "cycle_value_type",
        "cycle_value",
    )

    @classmethod
    def _normalize(cls, value: Any):
        if isinstance(value, dict):
            return {str(key): cls._normalize(value[key]) for key in sorted(value, key=str)}
        if isinstance(value, (list, tuple)):
            return [cls._normalize(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    @staticmethod
    def _field_value(task, field):
        if field == "decrypt_credentials":
            return getattr(task, "decrypt_credentials", None)
        return getattr(task, field, None)

    @classmethod
    def _payload(cls, task):
        payload = {
            field: cls._normalize(cls._field_value(task, field))
            for field in cls.FINGERPRINT_FIELDS
        }
        payload["decrypt_credentials"] = cls._normalize(
            cls._field_value(task, "decrypt_credentials")
        )
        return payload

    @classmethod
    def is_eligible(cls, task):
        if not task or not bool(getattr(task, "is_interval", False)):
            return False
        if getattr(task, "cycle_value_type", "") != "cycle":
            return False
        if getattr(task, "task_type", "") in {
            CollectPluginTypes.K8S,
            CollectPluginTypes.CONFIG_FILE,
        }:
            return False
        try:
            cycle_minutes = int(getattr(task, "cycle_value", 0) or 0)
        except (TypeError, ValueError):
            return False
        return cycle_minutes >= cls.THRESHOLD_MINUTES

    @classmethod
    def fingerprint(cls, task):
        serialized = json.dumps(
            cls._payload(task),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            serialized.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @classmethod
    def changed_fields(cls, old_task, new_task):
        fields = (*cls.FINGERPRINT_FIELDS, "decrypt_credentials")
        return tuple(
            field
            for field in fields
            if cls._normalize(cls._field_value(old_task, field))
            != cls._normalize(cls._field_value(new_task, field))
        )

    @classmethod
    def should_trigger_update(cls, old_task, new_task):
        return cls.is_eligible(new_task) and bool(cls.changed_fields(old_task, new_task))
```

在 `server/apps/cmdb/constants/constants.py` 的 `STARGAZER_URL` 旁增加：

```python
CMDB_FIRST_COLLECTION_ENABLED = (
    os.getenv("CMDB_FIRST_COLLECTION_ENABLED", "true").strip().lower()
    in {"1", "true", "yes", "on"}
)
```

在 `server/envs/.env.example` 增加：

```dotenv
# 长周期 CMDB 任务保存后主动触发一次 Stargazer；false 时退回 Telegraf 原周期
CMDB_FIRST_COLLECTION_ENABLED=true
```

- [ ] **Step 4: 运行测试确认绿灯**

```bash
cd server && .venv/bin/pytest apps/cmdb/tests/test_first_collection_policy.py -q
```

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add server/apps/cmdb/services/first_collection_policy.py server/apps/cmdb/tests/test_first_collection_policy.py server/apps/cmdb/constants/constants.py server/envs/.env.example
git commit -m "功能：增加 CMDB 首次采集触发策略"
```

---

### Task 2: Stargazer 单次触发客户端

**Files:**
- Create: `server/apps/cmdb/services/stargazer_collect_trigger.py`
- Create: `server/apps/cmdb/tests/test_stargazer_collect_trigger.py`

**Interfaces:**
- Consumes: `NodeParamsFactory.get_node_params(task)`、`STARGAZER_URL`、`requests.get`。
- Produces: `StargazerCollectTriggerClient.trigger(task) -> TriggerResult`、`StargazerCollectRetryableError`、`StargazerCollectPermanentError`。

- [ ] **Step 1: 写失败测试**

创建 `server/apps/cmdb/tests/test_stargazer_collect_trigger.py`：

```python
import types

import pytest
import requests

from apps.cmdb.services.stargazer_collect_trigger import (
    StargazerCollectPermanentError,
    StargazerCollectRetryableError,
    StargazerCollectTriggerClient,
)

pytestmark = pytest.mark.unit


class Response:
    def __init__(self, status_code=200, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


def task():
    return types.SimpleNamespace(id=7, model_id="host", driver_type="snmp")


def node_params():
    return types.SimpleNamespace(
        custom_headers=lambda: {
            "cmdbplugin_name": "host_info",
            "cmdbpassword": "secret",
            "instance_id": "cmdb_7",
        },
        tags={
            "instance_id": "cmdb_7",
            "instance_type": "cmdb_host",
            "collect_type": "http",
            "config_type": "host",
        },
    )


def patch_node_params(mocker):
    mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.NodeParamsFactory.get_node_params",
        return_value=node_params(),
    )


def test_queued_builds_same_source_request(mocker):
    patch_node_params(mocker)
    get = mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.requests.get",
        return_value=Response(headers={"X-Task-Status": "queued"}),
    )
    result = StargazerCollectTriggerClient().trigger(task())
    assert result.status == "accepted"
    _, kwargs = get.call_args
    assert kwargs["params"]["plugin_name"] == "host_info"
    assert kwargs["params"]["password"] == "secret"
    assert "instance_id" not in kwargs["params"]
    assert kwargs["headers"]["X-Instance-ID"] == "cmdb_7"
    assert kwargs["timeout"] == 15


def test_skipped_is_deduplicated(mocker):
    patch_node_params(mocker)
    mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.requests.get",
        return_value=Response(headers={"X-Task-Status": "skipped"}),
    )
    assert StargazerCollectTriggerClient().trigger(task()).status == "deduplicated"


def test_complete_batch_is_accepted(mocker):
    patch_node_params(mocker)
    mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.requests.get",
        return_value=Response(headers={"X-Task-Count": "3", "X-Success-Count": "3"}),
    )
    result = StargazerCollectTriggerClient().trigger(task())
    assert (result.status, result.total, result.accepted) == ("accepted", 3, 3)


def test_partial_batch_is_permanent(mocker):
    patch_node_params(mocker)
    mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.requests.get",
        return_value=Response(headers={"X-Task-Count": "3", "X-Success-Count": "2"}),
    )
    with pytest.raises(StargazerCollectPermanentError, match="accepted=2, total=3"):
        StargazerCollectTriggerClient().trigger(task())


@pytest.mark.parametrize("status_code", [500, 502, 503])
def test_5xx_is_retryable(mocker, status_code):
    patch_node_params(mocker)
    mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.requests.get",
        return_value=Response(status_code=status_code),
    )
    with pytest.raises(StargazerCollectRetryableError, match=str(status_code)):
        StargazerCollectTriggerClient().trigger(task())


def test_timeout_error_does_not_leak_secret(mocker):
    patch_node_params(mocker)
    mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.requests.get",
        side_effect=requests.Timeout("secret"),
    )
    with pytest.raises(StargazerCollectRetryableError) as exc:
        StargazerCollectTriggerClient().trigger(task())
    assert "secret" not in str(exc.value)
    assert exc.value.__cause__ is None


def test_4xx_is_permanent(mocker):
    patch_node_params(mocker)
    mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.requests.get",
        return_value=Response(status_code=400),
    )
    with pytest.raises(StargazerCollectPermanentError, match="HTTP 400"):
        StargazerCollectTriggerClient().trigger(task())
```

- [ ] **Step 2: 运行测试确认红灯**

```bash
cd server && .venv/bin/pytest apps/cmdb/tests/test_stargazer_collect_trigger.py -q
```

Expected: FAIL，包含模块不存在错误。

- [ ] **Step 3: 实现客户端**

创建 `server/apps/cmdb/services/stargazer_collect_trigger.py`：

```python
from dataclasses import dataclass

import requests

from apps.cmdb.constants.constants import STARGAZER_URL
from apps.cmdb.node_configs.config_factory import NodeParamsFactory


class StargazerCollectTriggerError(RuntimeError):
    pass


class StargazerCollectRetryableError(StargazerCollectTriggerError):
    pass


class StargazerCollectPermanentError(StargazerCollectTriggerError):
    pass


@dataclass(frozen=True)
class TriggerResult:
    status: str
    total: int = 1
    accepted: int = 1


class StargazerCollectTriggerClient:
    REQUEST_TIMEOUT_SECONDS = 15

    @staticmethod
    def _positive_int(value, field_name):
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise StargazerCollectPermanentError(
                f"Stargazer 响应缺少有效的 {field_name}"
            ) from exc
        if parsed <= 0:
            raise StargazerCollectPermanentError(
                f"Stargazer 响应中的 {field_name} 必须大于 0"
            )
        return parsed

    def _build_request(self, task):
        node_params = NodeParamsFactory.get_node_params(task)
        raw_headers = node_params.custom_headers()
        params = {
            key.split("cmdb", 1)[-1]: value
            for key, value in raw_headers.items()
            if key.startswith("cmdb")
        }
        tags = getattr(node_params, "tags", {}) or {}
        headers = {
            "X-Instance-ID": str(tags.get("instance_id") or ""),
            "X-Instance-Type": str(tags.get("instance_type") or ""),
            "X-Collect-Type": str(tags.get("collect_type") or "http"),
            "X-Config-Type": str(tags.get("config_type") or task.model_id),
        }
        url = f"{STARGAZER_URL.rstrip('/')}/api/collect/collect_info"
        return url, params, headers

    def _parse_success(self, response):
        task_count = response.headers.get("X-Task-Count")
        if task_count is not None:
            total = self._positive_int(task_count, "X-Task-Count")
            try:
                accepted = int(response.headers.get("X-Success-Count") or 0)
            except (TypeError, ValueError) as exc:
                raise StargazerCollectPermanentError(
                    "Stargazer 响应缺少有效的 X-Success-Count"
                ) from exc
            if accepted != total:
                raise StargazerCollectPermanentError(
                    f"Stargazer 批量接收不完整: accepted={accepted}, total={total}"
                )
            return TriggerResult("accepted", total, accepted)

        status = str(response.headers.get("X-Task-Status") or "").lower()
        if status == "queued":
            return TriggerResult("accepted")
        if status == "skipped":
            return TriggerResult("deduplicated")
        raise StargazerCollectPermanentError(
            f"Stargazer 未接受采集任务: status={status or 'unknown'}"
        )

    def trigger(self, task):
        url, params, headers = self._build_request(task)
        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=self.REQUEST_TIMEOUT_SECONDS,
            )
        except (requests.Timeout, requests.ConnectionError):
            raise StargazerCollectRetryableError(
                "Stargazer 首次采集请求发生可重试网络错误"
            ) from None
        except requests.RequestException:
            raise StargazerCollectPermanentError(
                "Stargazer 首次采集请求失败"
            ) from None

        if response.status_code >= 500:
            raise StargazerCollectRetryableError(
                f"Stargazer 首次采集请求返回 HTTP {response.status_code}"
            )
        if response.status_code != 200:
            raise StargazerCollectPermanentError(
                f"Stargazer 首次采集请求返回 HTTP {response.status_code}"
            )
        return self._parse_success(response)
```

- [ ] **Step 4: 运行测试确认绿灯**

```bash
cd server && .venv/bin/pytest apps/cmdb/tests/test_stargazer_collect_trigger.py -q
```

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add server/apps/cmdb/services/stargazer_collect_trigger.py server/apps/cmdb/tests/test_stargazer_collect_trigger.py
git commit -m "功能：封装 Stargazer 首次采集触发客户端"
```

---

### Task 3: Celery 协调任务和有界重试

**Files:**
- Modify: `server/apps/cmdb/tasks/celery_tasks.py:1-130`
- Modify: `server/apps/cmdb/tasks/__init__.py:6-20`
- Create: `server/apps/cmdb/tests/test_first_collection_task.py`

**Interfaces:**
- Consumes: Tasks 1—2。
- Produces: `trigger_first_collection(task_id: int, expected_fingerprint: str, reason: str) -> dict`，任务名 `apps.cmdb.tasks.celery_tasks.trigger_first_collection`。

- [ ] **Step 1: 写失败测试**

创建 `server/apps/cmdb/tests/test_first_collection_task.py`：

```python
import pytest

from apps.cmdb.constants.constants import CollectPluginTypes
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.tasks import celery_tasks as ct

pytestmark = pytest.mark.django_db


def create_task(**overrides):
    values = {
        "name": "first-collect",
        "task_type": CollectPluginTypes.HOST,
        "driver_type": "snmp",
        "model_id": "host",
        "is_interval": True,
        "cycle_value_type": "cycle",
        "cycle_value": "30",
        "instances": [{"inst_name": "host-1", "ip_addr": "10.0.0.1"}],
        "access_point": [{"id": "node-1"}],
        "params": {},
        "team": [1],
    }
    values.update(overrides)
    return CollectModels.objects.create(**values)


def test_current_fingerprint_triggers_client(mocker):
    task = create_task()
    mocker.patch(
        "apps.cmdb.services.first_collection_policy.FirstCollectionPolicy.is_eligible",
        return_value=True,
    )
    mocker.patch(
        "apps.cmdb.services.first_collection_policy.FirstCollectionPolicy.fingerprint",
        return_value="fp",
    )
    trigger = mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.StargazerCollectTriggerClient.trigger",
        return_value=mocker.Mock(status="accepted", total=1, accepted=1),
    )
    result = ct.trigger_first_collection.run(task.id, "fp", "create")
    assert result["status"] == "accepted"
    trigger.assert_called_once()


def test_stale_fingerprint_skips(mocker):
    task = create_task()
    mocker.patch(
        "apps.cmdb.services.first_collection_policy.FirstCollectionPolicy.fingerprint",
        return_value="new-fp",
    )
    trigger = mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.StargazerCollectTriggerClient.trigger"
    )
    assert ct.trigger_first_collection.run(task.id, "old-fp", "update:params")["status"] == "stale"
    trigger.assert_not_called()


def test_missing_ineligible_and_disabled_skip(mocker):
    assert ct.trigger_first_collection.run(999999, "fp", "create")["status"] == "missing"
    short = create_task(cycle_value="5")
    assert ct.trigger_first_collection.run(short.id, "fp", "create")["status"] == "ineligible"
    long_task = create_task(name="disabled")
    mocker.patch("apps.cmdb.constants.constants.CMDB_FIRST_COLLECTION_ENABLED", False)
    assert ct.trigger_first_collection.run(long_task.id, "fp", "create")["status"] == "disabled"


def test_retryable_error_uses_celery_retry(mocker):
    task = create_task()
    mocker.patch(
        "apps.cmdb.services.first_collection_policy.FirstCollectionPolicy.is_eligible",
        return_value=True,
    )
    mocker.patch(
        "apps.cmdb.services.first_collection_policy.FirstCollectionPolicy.fingerprint",
        return_value="fp",
    )
    from apps.cmdb.services.stargazer_collect_trigger import StargazerCollectRetryableError
    mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.StargazerCollectTriggerClient.trigger",
        side_effect=StargazerCollectRetryableError("retryable"),
    )
    retry = mocker.patch.object(
        ct.trigger_first_collection,
        "retry",
        side_effect=RuntimeError("retry-scheduled"),
    )
    with pytest.raises(RuntimeError, match="retry-scheduled"):
        ct.trigger_first_collection.run(task.id, "fp", "create")
    assert retry.call_args.kwargs["countdown"] in {10, 20}
    assert ct.trigger_first_collection.max_retries == 2


def test_permanent_error_does_not_retry(mocker):
    task = create_task()
    mocker.patch(
        "apps.cmdb.services.first_collection_policy.FirstCollectionPolicy.is_eligible",
        return_value=True,
    )
    mocker.patch(
        "apps.cmdb.services.first_collection_policy.FirstCollectionPolicy.fingerprint",
        return_value="fp",
    )
    from apps.cmdb.services.stargazer_collect_trigger import StargazerCollectPermanentError
    mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.StargazerCollectTriggerClient.trigger",
        side_effect=StargazerCollectPermanentError("HTTP 400"),
    )
    retry = mocker.patch.object(ct.trigger_first_collection, "retry")
    result = ct.trigger_first_collection.run(task.id, "fp", "create")
    assert result == {"status": "failed", "task_id": task.id, "reason": "create"}
    retry.assert_not_called()
```

- [ ] **Step 2: 运行测试确认红灯**

```bash
cd server && .venv/bin/pytest apps/cmdb/tests/test_first_collection_task.py -q
```

Expected: FAIL，`celery_tasks` 没有 `trigger_first_collection`。

- [ ] **Step 3: 实现 Celery 任务**

在 `server/apps/cmdb/tasks/celery_tasks.py` 顶部增加 `import time`，并在 `sync_collect_task` 前增加：

```python
@shared_task(
    bind=True,
    max_retries=2,
    name="apps.cmdb.tasks.celery_tasks.trigger_first_collection",
)
def trigger_first_collection(self, task_id, expected_fingerprint, reason):
    from apps.cmdb.constants import constants as cmdb_constants
    from apps.cmdb.services.first_collection_policy import FirstCollectionPolicy
    from apps.cmdb.services.stargazer_collect_trigger import (
        StargazerCollectPermanentError,
        StargazerCollectRetryableError,
        StargazerCollectTriggerClient,
    )

    started_at = time.monotonic()
    if not cmdb_constants.CMDB_FIRST_COLLECTION_ENABLED:
        return {"status": "disabled", "task_id": task_id, "reason": reason}

    task = CollectModels._default_manager.filter(id=task_id).first()
    if not task:
        return {"status": "missing", "task_id": task_id, "reason": reason}
    if not FirstCollectionPolicy.is_eligible(task):
        return {"status": "ineligible", "task_id": task_id, "reason": reason}

    cycle_minutes = int(task.cycle_value)
    attempt = int(self.request.retries) + 1
    current_fingerprint = FirstCollectionPolicy.fingerprint(task)
    fingerprint_short = current_fingerprint[:12]
    if current_fingerprint != expected_fingerprint:
        logger.info(
            "[FirstCollection] 跳过过期配置 task_id=%s fingerprint=%s reason=%s "
            "cycle_minutes=%s attempt=%s elapsed_ms=%s result=stale",
            task_id,
            fingerprint_short,
            reason,
            cycle_minutes,
            attempt,
            int((time.monotonic() - started_at) * 1000),
        )
        return {"status": "stale", "task_id": task_id, "reason": reason}

    try:
        result = StargazerCollectTriggerClient().trigger(task)
    except StargazerCollectRetryableError as exc:
        retry_number = int(self.request.retries)
        countdown = 10 * (2 ** retry_number)
        logger.warning(
            "[FirstCollection] 可重试失败 task_id=%s fingerprint=%s "
            "reason=%s cycle_minutes=%s attempt=%s elapsed_ms=%s error_type=%s",
            task_id,
            fingerprint_short,
            reason,
            cycle_minutes,
            attempt,
            int((time.monotonic() - started_at) * 1000),
            exc.__class__.__name__,
        )
        raise self.retry(exc=exc, countdown=countdown)
    except StargazerCollectPermanentError as exc:
        logger.warning(
            "[FirstCollection] 永久失败 task_id=%s fingerprint=%s "
            "reason=%s cycle_minutes=%s attempt=%s elapsed_ms=%s error_type=%s",
            task_id,
            fingerprint_short,
            reason,
            cycle_minutes,
            attempt,
            int((time.monotonic() - started_at) * 1000),
            exc.__class__.__name__,
        )
        return {"status": "failed", "task_id": task_id, "reason": reason}

    logger.info(
        "[FirstCollection] 已接收 task_id=%s fingerprint=%s reason=%s "
        "cycle_minutes=%s attempt=%s elapsed_ms=%s status=%s total=%s accepted=%s",
        task_id,
        fingerprint_short,
        reason,
        cycle_minutes,
        attempt,
        int((time.monotonic() - started_at) * 1000),
        result.status,
        result.total,
        result.accepted,
    )
    return {
        "status": result.status,
        "task_id": task_id,
        "reason": reason,
        "total": result.total,
        "accepted": result.accepted,
    }
```

在 `server/apps/cmdb/tasks/__init__.py` 导入列表增加：

```python
trigger_first_collection,
```

- [ ] **Step 4: 运行测试确认绿灯**

```bash
cd server && .venv/bin/pytest apps/cmdb/tests/test_first_collection_task.py -q
```

Expected: PASS；`max_retries=2` 保证最多三次请求。

- [ ] **Step 5: 提交**

```bash
git add server/apps/cmdb/tasks/celery_tasks.py server/apps/cmdb/tasks/__init__.py server/apps/cmdb/tests/test_first_collection_task.py
git commit -m "功能：增加 CMDB 首次采集异步协调任务"
```

---

### Task 4: 接入创建、更新与延迟同步

**Files:**
- Modify: `server/apps/cmdb/services/collect_service.py:30-41,365-411,438-540`
- Create: `server/apps/cmdb/tests/test_collect_service_first_collection.py`
- Test: `server/apps/cmdb/tests/test_collect_service_methods.py`

**Interfaces:**
- Consumes: Tasks 1—3。
- Produces: `CollectModelService.schedule_first_collection_if_needed(instance, old_instance=None, reason="create") -> bool`。

- [ ] **Step 1: 写投递辅助方法失败测试**

创建 `server/apps/cmdb/tests/test_collect_service_first_collection.py`：

```python
import types

import pytest
from django.db import transaction

from apps.cmdb.constants.constants import CollectPluginTypes
from apps.cmdb.services.collect_service import CollectModelService

pytestmark = pytest.mark.unit


def task(**overrides):
    values = {
        "id": 7,
        "is_interval": True,
        "cycle_value_type": "cycle",
        "cycle_value": "30",
        "task_type": CollectPluginTypes.HOST,
        "driver_type": "snmp",
        "model_id": "host",
        "instances": [{"inst_name": "host-1"}],
        "ip_range": "",
        "access_point": [{"id": "node-1"}],
        "plugin_id": "host_info",
        "params": {},
        "timeout": 60,
        "decrypt_credentials": {"username": "root", "password": "secret"},
        "name": "task",
        "team": [1],
        "expire_days": 0,
        "data_cleanup_strategy": "no_cleanup",
    }
    values.update(overrides)
    return types.SimpleNamespace(**values)


def test_create_registers_one_on_commit_dispatch(mocker):
    callbacks = []
    mocker.patch(
        "apps.cmdb.services.collect_service.transaction.on_commit",
        side_effect=callbacks.append,
    )
    send_task = mocker.patch("apps.cmdb.services.collect_service.current_app.send_task")
    assert CollectModelService.schedule_first_collection_if_needed(task()) is True
    assert send_task.call_count == 0
    assert len(callbacks) == 1
    callbacks[0]()
    send_task.assert_called_once_with(
        CollectModelService.FIRST_COLLECTION_TASK,
        args=[7, mocker.ANY, "create"],
    )
    assert "secret" not in repr(send_task.call_args)


@pytest.mark.django_db(transaction=True)
def test_rollback_discards_first_collection_dispatch(mocker):
    send_task = mocker.patch("apps.cmdb.services.collect_service.current_app.send_task")
    with pytest.raises(RuntimeError, match="rollback"):
        with transaction.atomic():
            CollectModelService.schedule_first_collection_if_needed(task())
            raise RuntimeError("rollback")
    send_task.assert_not_called()


def test_update_source_change_has_field_reason(mocker):
    callbacks = []
    mocker.patch(
        "apps.cmdb.services.collect_service.transaction.on_commit",
        side_effect=callbacks.append,
    )
    send_task = mocker.patch("apps.cmdb.services.collect_service.current_app.send_task")
    old = task(params={"port": 22})
    new = task(params={"port": 2222})
    assert CollectModelService.schedule_first_collection_if_needed(
        new, old_instance=old, reason="update"
    ) is True
    callbacks[0]()
    assert send_task.call_args.args[1][2] == "update:params"


def test_governance_only_disabled_short_k8s_and_config_file_skip(mocker):
    on_commit = mocker.patch("apps.cmdb.services.collect_service.transaction.on_commit")
    assert CollectModelService.schedule_first_collection_if_needed(
        task(name="new"), old_instance=task(), reason="update"
    ) is False
    assert CollectModelService.schedule_first_collection_if_needed(
        task(cycle_value="5")
    ) is False
    assert CollectModelService.schedule_first_collection_if_needed(
        task(task_type=CollectPluginTypes.K8S)
    ) is False
    assert CollectModelService.schedule_first_collection_if_needed(
        task(task_type=CollectPluginTypes.CONFIG_FILE)
    ) is False
    mocker.patch("apps.cmdb.constants.constants.CMDB_FIRST_COLLECTION_ENABLED", False)
    assert CollectModelService.schedule_first_collection_if_needed(task()) is False
    on_commit.assert_not_called()
```

- [ ] **Step 2: 运行测试确认红灯**

```bash
cd server && .venv/bin/pytest apps/cmdb/tests/test_collect_service_first_collection.py -q
```

Expected: FAIL，缺少 `schedule_first_collection_if_needed`。

- [ ] **Step 3: 实现事务提交后投递方法**

在 `CollectModelService` 增加常量：

```python
FIRST_COLLECTION_TASK = "apps.cmdb.tasks.celery_tasks.trigger_first_collection"
```

在 `schedule_delayed_sync_if_needed` 前增加：

```python
    @classmethod
    def schedule_first_collection_if_needed(
        cls,
        instance,
        old_instance=None,
        reason="create",
    ):
        from apps.cmdb.constants import constants as cmdb_constants
        from apps.cmdb.services.first_collection_policy import FirstCollectionPolicy

        if not cmdb_constants.CMDB_FIRST_COLLECTION_ENABLED:
            return False
        if not FirstCollectionPolicy.is_eligible(instance):
            return False

        if old_instance is not None:
            changed_fields = FirstCollectionPolicy.changed_fields(old_instance, instance)
            if not changed_fields:
                return False
            reason = f"update:{','.join(changed_fields)}"

        fingerprint = FirstCollectionPolicy.fingerprint(instance)
        transaction.on_commit(
            lambda task_id=instance.id, expected=fingerprint, trigger_reason=reason:
            current_app.send_task(
                cls.FIRST_COLLECTION_TASK,
                args=[task_id, expected, trigger_reason],
            )
        )
        logger.info(
            "[FirstCollection] 已注册事务后触发 task_id=%s fingerprint=%s reason=%s",
            instance.id,
            fingerprint[:12],
            reason,
        )
        return True
```

- [ ] **Step 4: 运行辅助方法测试确认绿灯**

```bash
cd server && .venv/bin/pytest apps/cmdb/tests/test_collect_service_first_collection.py -q
```

Expected: PASS。

- [ ] **Step 5: 写 create/update 接线失败测试**

向同一测试文件追加：

```python
def test_create_schedules_first_and_delayed_sync(mocker):
    instance = task()
    view = mocker.Mock()
    view.get_serializer.return_value = mocker.Mock(instance=instance)
    request = mocker.Mock(data={}, user=mocker.Mock(username="admin"))
    mocker.patch.object(
        CollectModelService,
        "format_params",
        return_value=({}, True, "*/30 * * * *"),
    )
    mocker.patch.object(CollectModelService, "enrich_host_cloud_snapshot_payload")
    mocker.patch.object(CollectModelService, "push_butch_node_params")
    mocker.patch(
        "apps.cmdb.services.collect_service.CeleryUtils.create_or_update_periodic_task"
    )
    first = mocker.patch.object(
        CollectModelService,
        "schedule_first_collection_if_needed",
        return_value=True,
    )
    delayed = mocker.patch.object(
        CollectModelService,
        "schedule_delayed_sync_if_needed",
    )
    mocker.patch("apps.cmdb.services.collect_service.create_change_record")

    assert CollectModelService.create(request, view) == 7
    first.assert_called_once_with(instance=instance, reason="create")
    delayed.assert_called_once_with(instance=instance, is_interval=True)


def test_update_source_change_schedules_delayed_sync_once(mocker):
    current = task(params={"port": 22})
    view = mocker.Mock()
    view.get_object.return_value = current
    view.get_serializer.return_value = mocker.Mock(instance=current)
    request = mocker.Mock(data={"team": [1]}, user=mocker.Mock(username="admin"))
    mocker.patch.object(CollectModelService, "has_permission")
    mocker.patch.object(
        CollectModelService,
        "format_params",
        return_value=({"params": {"port": 2222}}, True, "*/30 * * * *"),
    )
    mocker.patch.object(CollectModelService, "format_update_credential")
    mocker.patch.object(CollectModelService, "enrich_host_cloud_snapshot_payload")
    mocker.patch.object(CollectModelService, "delete_butch_node_params")
    mocker.patch.object(CollectModelService, "push_butch_node_params")
    mocker.patch.object(CollectModelService, "delete_team")
    mocker.patch(
        "apps.cmdb.services.collect_service.CeleryUtils.create_or_update_periodic_task"
    )
    mocker.patch(
        "apps.cmdb.services.collect_service.CollectCredentialPoolService.diff_pool",
        return_value=([], [], []),
    )
    mocker.patch(
        "apps.cmdb.services.collect_service.CollectHitStateService.clear_by_credential_ids",
        return_value=0,
    )
    mocker.patch("apps.cmdb.services.collect_service.create_change_record")
    view.perform_update.side_effect = lambda _serializer: setattr(
        current, "params", {"port": 2222}
    )

    first = mocker.patch.object(
        CollectModelService,
        "schedule_first_collection_if_needed",
        return_value=True,
    )
    delayed = mocker.patch.object(
        CollectModelService,
        "schedule_delayed_sync_if_needed",
    )
    mocker.patch.object(
        CollectModelService,
        "is_schedule_config_changed",
        return_value=False,
    )

    CollectModelService.update(request, view)
    assert first.call_args.kwargs["old_instance"].params == {"port": 22}
    delayed.assert_called_once_with(instance=current, is_interval=True)
```

- [ ] **Step 6: 运行接线测试确认红灯**

```bash
cd server && .venv/bin/pytest apps/cmdb/tests/test_collect_service_first_collection.py -q
```

Expected: create/update 接线用例 FAIL。

- [ ] **Step 7: 最小接入 create/update**

create 的周期分支在创建周期任务后调用：

```python
cls.schedule_first_collection_if_needed(instance=instance, reason="create")
cls.schedule_delayed_sync_if_needed(instance=instance, is_interval=is_interval)
```

update 中完成 serializer 更新和节点配置重下发后调用：

```python
schedule_changed = cls.is_schedule_config_changed(
    old_instance=old_instance,
    new_instance=instance,
)
first_collection_scheduled = cls.schedule_first_collection_if_needed(
    instance=instance,
    old_instance=old_instance,
    reason="update",
)
if is_interval and (schedule_changed or first_collection_scheduled):
    cls.schedule_delayed_sync_if_needed(
        instance=instance,
        is_interval=is_interval,
    )
```

删除 update 旧的“仅调度变化时立即安排延迟同步”分支，保证一次更新只注册一次延迟同步。不要修改 `claim_execution`、`execute`、`sync_collect_task`、RUNNING 状态或多凭据派发逻辑。

- [ ] **Step 8: 运行接线和既有延迟同步测试**

```bash
cd server && .venv/bin/pytest \
  apps/cmdb/tests/test_collect_service_first_collection.py \
  apps/cmdb/tests/test_collect_service_methods.py -q
```

Expected: PASS。

- [ ] **Step 9: 提交**

```bash
git add server/apps/cmdb/services/collect_service.py server/apps/cmdb/tests/test_collect_service_first_collection.py
git commit -m "功能：接入 CMDB 长周期任务首次采集"
```

---

### Task 5: 回归、覆盖率和真实环境验收

**Files:**
- Test: Tasks 1—4 的全部测试文件。
- Test: `server/apps/cmdb/tests/test_collect_celery_tasks_svc.py`
- Test: `server/apps/cmdb/tests/test_collect_task_single_flight.py`
- Test: `server/apps/cmdb/tests/test_collect_dispatch_service.py`

**Interfaces:**
- Consumes: Tasks 1—4。
- Produces: 测试、覆盖率、门禁和真实环境证据，不新增产品接口。

- [ ] **Step 1: 运行首次采集目标测试**

```bash
cd server && .venv/bin/pytest \
  apps/cmdb/tests/test_first_collection_policy.py \
  apps/cmdb/tests/test_stargazer_collect_trigger.py \
  apps/cmdb/tests/test_first_collection_task.py \
  apps/cmdb/tests/test_collect_service_first_collection.py \
  apps/cmdb/tests/test_collect_service_methods.py -q
```

Expected: PASS。

- [ ] **Step 2: 运行并发、状态和派发回归**

```bash
cd server && .venv/bin/pytest \
  apps/cmdb/tests/test_collect_celery_tasks_svc.py \
  apps/cmdb/tests/test_collect_task_single_flight.py \
  apps/cmdb/tests/test_collect_dispatch_service.py -q
```

Expected: PASS，首次触发没有改变 `claim_execution`、RUNNING 单飞或多凭据语义。

- [ ] **Step 3: 检查覆盖率不低于 75%**

```bash
cd server && .venv/bin/pytest \
  apps/cmdb/tests/test_first_collection_policy.py \
  apps/cmdb/tests/test_stargazer_collect_trigger.py \
  apps/cmdb/tests/test_first_collection_task.py \
  apps/cmdb/tests/test_collect_service_first_collection.py \
  --cov=apps.cmdb.services.first_collection_policy \
  --cov=apps.cmdb.services.stargazer_collect_trigger \
  --cov-report=term-missing \
  --cov-fail-under=75
```

Expected: PASS，退出码 0。

- [ ] **Step 4: 运行服务端门禁**

```bash
cd server && make test
```

Expected: PASS。若被任务外既有环境错误阻断，保存完整失败摘要，并确保 Steps 1—3 通过；不得将既有失败误报为全量门禁通过。

- [ ] **Step 5: 检查最小 diff、敏感信息和迁移**

```bash
git diff --check
git diff --name-only
git diff -- server/apps/cmdb server/envs/.env.example
git grep -n "CMDB_FIRST_COLLECTION_ENABLED\|trigger_first_collection" -- server/apps/cmdb server/envs/.env.example
cd server && .venv/bin/python manage.py makemigrations --check --dry-run
```

Expected: 无空白错误；仅包含本计划列出的业务、测试与配置文件；日志不含凭据或响应正文；迁移检查输出 `No changes detected`。

- [ ] **Step 6: 完成 30 分钟任务真实验收**

```text
1. 创建循环周期 30 分钟的非 K8S、非配置文件任务并记录保存时间。
2. 确认节点 Telegraf inputs.prometheus.interval 仍为 1800s。
3. 确认事务提交后出现 FirstCollection accepted 或 deduplicated 日志。
4. 确认 Stargazer 入队一次，Worker 完成后指标进入 VictoriaMetrics。
5. 保存后 5 分钟内确认任务详情出现真实执行结果和 raw_data。
6. 等待下一周期，确认仍按 30 分钟运行且没有临时短周期。
7. 设置 CMDB_FIRST_COLLECTION_ENABLED=false 并重启服务；再次创建长周期任务，确认不快速触发，但 Telegraf 周期和原延迟同步仍存在。
```

Expected: 七项全部满足。目标不可达或采集本身超过 5 分钟时记录真实限制，不增加并发或无限重试。

- [ ] **Step 7: 仅在验证产生修正时提交**

```bash
git add server/apps/cmdb server/envs/.env.example
git commit -m "测试：补充 CMDB 首次采集验收覆盖"
```

如果验证没有产生文件变化，跳过提交，在交付说明中列出命令退出码和真实验收结果。
