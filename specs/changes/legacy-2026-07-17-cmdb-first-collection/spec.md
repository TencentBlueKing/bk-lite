# Historical Superpowers change: 2026-07-17-cmdb-first-collection

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-17-cmdb-first-collection.md

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

## specs: 2026-07-17-cmdb-first-collection-design.md

日期：2026-07-17
状态：设计已确认

## 1. 背景

CMDB 配置采集任务的循环周期会写入 Telegraf `inputs.prometheus.interval`。当用户设置 30 分钟周期时，Telegraf 常驻进程会等待输入调度器的下一次 ticker，不会因为新增子配置而额外先采集一次。因此，任务下发后可能长时间没有真实指标可供 CMDB 查询。

现有逻辑会对循环周期不小于 15 分钟的任务安排一次“下发约 4 分钟后同步”。该同步只执行 `sync_collect_task`，从 VictoriaMetrics 查询已有指标；它不会主动让 Stargazer 产生数据。如果 Telegraf 尚未触发输入，本次同步仍可能得到空结果。

仓库已经具备可复用的即时链路：服务端调用 Stargazer `/api/collect/collect_info` 后，Stargazer 将真实采集放入现有任务队列，Worker 完成采集并主动写入 NATS/VictoriaMetrics。配置文件采集已经使用这一模式。

## 2. 目标与非目标

### 2.1 目标

- 循环周期不小于 15 分钟的任务在首次下发后主动触发一次真实采集。
- Stargazer 与目标资源正常可用时，采集任务详情在保存成功后 5 分钟内出现真实执行结果和原始数据。
- 新建任务，以及采集对象、凭据、插件参数或长周期配置发生有效变更时触发快速采集。
- 不改变用户配置的长期 Telegraf 周期。
- 快速触发失败时保留原有 Telegraf 周期链路作为降级路径。
- 使用现有队列、去重和资源控制，避免绕过 Stargazer 调度造成采集风暴。

### 2.2 非目标

- 不要求 CMDB 资产实例的新增或更新也必须在 5 分钟内完成。
- 不为小于 15 分钟的循环任务增加快速触发。
- 不为 K8S 采集增加 Telegraf 首次触发逻辑。
- 不重复处理已有专用即时触发协调器的配置文件采集。
- 本期不新增前端临时状态、数据库字段或迁移。
- 不通过临时修改 Telegraf 周期或执行 `telegraf --once` 实现加速。

## 3. 方案概述

采用“服务端主动触发一次 Stargazer 采集，Telegraf 继续负责长期周期”的双路径设计：

1. CMDB 保存任务、创建或更新 Celery 周期，并正常下发 Telegraf 子配置。
2. 数据库事务提交后，投递一次首次采集异步任务；接口请求不等待 Stargazer。
3. 异步任务读取最新任务并重新校验资格和配置指纹。
4. 任务复用节点参数工厂生成与 Telegraf 一致的采集参数和标签，调用 Stargazer。
5. Stargazer 使用现有队列执行真实采集，并由 Worker 主动写入 NATS/VictoriaMetrics。
6. 下发约 4 分钟后继续执行现有 `sync_collect_task`，生成任务详情中的执行结果和原始数据。
7. 后续仅由 Telegraf 按用户配置的周期调度。

快速触发是加速通道，不是新的长期调度器。

## 4. 组件边界

### 4.1 `FirstCollectionPolicy`

负责纯业务判断，不执行网络请求：

- 判断任务是否为循环周期且周期不小于 15 分钟。
- 排除 K8S 和配置文件专用链路。
- 比较更新前后快照，判断是否修改了影响采集结果的字段。
- 生成稳定的采集配置指纹。

该组件应设计为纯函数或无外部副作用的服务，便于直接单元测试。

### 4.2 `StargazerCollectTriggerClient`

负责单次 Stargazer 触发：

- 通过 `NodeParamsFactory` 生成采集参数，保证服务端即时触发与 Telegraf 使用同一参数来源。
- 调用 `${STARGAZER_URL}/api/collect/collect_info`。
- 校验单任务和批量任务响应。
- 对可重试错误执行有界重试。
- 输出脱敏、结构化日志。

配置文件采集后续可复用该客户端，但本变更不要求重构其业务协调流程。

### 4.3 `trigger_first_collection` Celery 任务

负责异步协调：

- 接收任务 ID 和期望配置指纹。
- 重新读取最新 `CollectModels`。
- 重新执行资格判断。
- 当前指纹与期望指纹不一致时，将本次任务标记为过期并退出。
- 调用 `StargazerCollectTriggerClient`。
- 无论快速触发成功与否，都不修改用户的 Telegraf 周期配置。

### 4.4 `CollectModelService` 接入点

- 新建：符合资格时，在事务提交后投递一次快速触发。
- 更新：仅当更新后的任务符合资格且数据源相关配置发生变化时投递。
- 现有约 4 分钟延迟同步继续保留。
- HTTP 调用和 Celery 投递不得发生在数据库事务提交之前。

## 5. 触发规则

### 5.1 新建任务

同时满足以下条件时触发：

- `is_interval=true`；
- `cycle_value_type=cycle`；
- `cycle_value` 可解析为整数且不小于 15；
- 任务通过 Telegraf/Stargazer 配置采集链路运行；
- 任务不是 K8S；
- 任务不是已有专用即时触发的配置文件采集。

### 5.2 更新任务

更新后的任务满足新建资格，且下列任一字段发生语义变化时触发：

- 采集对象：`instances`、`ip_range`、`access_point`；
- 凭据：`credential`；
- 插件和参数：`plugin_id`、`params`、`task_type`、`driver_type`、`model_id`；
- 执行约束：`timeout`；
- 长周期调度：进入不小于 15 分钟的区间，或在该区间内修改循环周期。

下列字段单独变化时不触发：

- `name`；
- `team`；
- `expire_days`；
- `data_cleanup_strategy`；
- 其他不改变实际采集请求的展示或治理字段。

比较时应使用规范化后的业务值，避免字典键顺序、列表表现形式等非语义差异触发重复采集。

## 6. 配置指纹与并发一致性

配置指纹只包含影响实际采集请求的规范化字段，并使用稳定序列化后计算摘要。摘要不可包含可逆的明文凭据，也不得写入用户可见错误信息。

异步任务执行时重新计算当前指纹：

- 相同：执行快速触发。
- 不同：说明用户已再次编辑任务，旧触发直接退出。
- 任务已删除或已不满足资格：直接退出。

该机制保证连续编辑时只有最新配置有资格执行。Stargazer 现有参数去重继续处理响应丢失重试、Telegraf 首次 ticker 恰好到达等并发情况。

## 7. Stargazer 请求与响应契约

请求参数和标签必须与 Telegraf 子配置保持同源：

- `cmdb*` 参数来自节点参数对象的 `custom_headers()`；
- 实例、采集和配置标签来自节点参数对象的 `tags`；
- 地址使用服务端配置的 `STARGAZER_URL`；
- 请求超时使用受控的服务端值，不接受终端用户直接覆盖。

响应判断：

- 单任务 `queued`：成功接收。
- 单任务 `skipped`：已有相同参数任务正在处理，视为成功接收。
- 批量任务：仅 `X-Success-Count == X-Task-Count` 且总数大于 0 时视为完整接收。
- 批量部分接收：本次快速触发失败，不得伪装成完整成功。
- 4xx：参数或契约错误，不重试。
- 连接异常、超时和 5xx：最多重试 3 次，使用短退避。

重试必须使用相同参数。若首次请求已入队但响应丢失，Stargazer 去重应阻止重复的实际采集。

## 8. 失败处理与降级

- 快速触发发生在事务提交后，失败不能回滚已保存的采集任务。
- 快速触发失败不能删除或修改已下发的 Telegraf 配置。
- 原有周期任务继续存在，最终由 Telegraf 正常采集。
- 约 4 分钟后的同步任务继续执行，保持现有任务详情行为。
- 资格不满足、任务被删除或配置指纹过期属于正常跳过，不记录为系统错误。
- 网络失败、5xx、4xx、部分接收和重试耗尽需要记录不同的结构化结果。
- 任何日志和异常均不得包含密码、Token、完整凭据、完整请求头或未经脱敏的响应正文。

5 分钟目标适用于 Stargazer、消息链路、VictoriaMetrics 和目标资源正常可用，且单次真实采集能在该时间窗口内完成的场景。目标资源不可达或采集本身超过 5 分钟时，应展示真实失败或延迟结果，不以扩大并发或无限重试掩盖问题。

## 9. 资源安全与回滚

- 快速触发只负责向现有 Stargazer 队列提交任务，不在 CMDB 服务端按主机创建并发执行器。
- 主机拆分、任务排队、运行标记和参数去重继续由 Stargazer 负责。
- 单次保存最多投递一个首次采集协调任务。
- 重试次数和退避固定受限，不允许形成无限递归投递。
- 增加服务端功能开关；关闭后立即停止新增快速触发，系统退回原有 Telegraf 周期行为。
- 阈值和延迟同步时间使用服务端常量或受控配置，不允许由普通 API 请求任意覆盖。
- 回滚不需要恢复数据或 Telegraf 配置，因为本方案不修改长期周期，也不引入数据库结构。

## 10. 可观测性

首次触发日志至少包含：

- CMDB 任务 ID；
- 配置指纹的不可逆短摘要；
- 触发原因：`create` 或具体更新类别；
- 当前周期；
- 尝试次数；
- 结果：`accepted`、`deduplicated`、`stale`、`ineligible`、`retrying`、`failed`；
- 总耗时；
- 脱敏错误类别。

禁止记录请求凭据和完整响应内容。本期不新增前端状态；真实同步记录仍是用户判断采集结果的权威来源。

## 11. 测试策略

实现遵循 TDD，先写失败测试，再完成最小实现。

### 11.1 策略测试

- 新建 30 分钟任务符合资格。
- 新建 5 分钟任务不符合资格。
- 定点任务不符合资格。
- K8S 和配置文件专用链路不符合资格。
- 修改对象、凭据、插件参数、超时或长周期会触发。
- 仅修改名称、组织、过期天数或清理策略不触发。
- 规范化后语义相同的数据不触发。

### 11.2 接入与事务测试

- 新建符合资格的任务仅在事务提交后投递一次。
- 事务回滚时不投递。
- 更新符合条件时投递，普通字段更新不投递。
- 投递参数包含任务 ID 和期望指纹，不包含明文凭据。
- 现有 Telegraf 配置仍使用用户设置的原始周期。

### 11.3 异步任务测试

- 当前指纹匹配时调用 Stargazer。
- 指纹过期、任务删除或资格变化时安全退出。
- 单任务 `queued` 和 `skipped` 正确处理。
- 批量全部接收成功，部分接收失败。
- 网络异常和 5xx 有界重试，4xx 不重试。
- 重试耗尽后不影响周期配置和已有任务。
- 日志与异常不泄露凭据。

### 11.4 回归测试

- 原有不小于 15 分钟任务的延迟同步仍被安排。
- 小周期、K8S、配置文件采集和非周期任务行为不变。
- Stargazer 队列去重对相同参数重复请求继续有效。
- 配置文件采集原有即时触发不产生第二次通用触发。

## 12. 真实环境验收

使用一个 30 分钟循环任务进行验收：

1. 记录任务保存成功时间。
2. 确认节点 Telegraf 子配置的输入周期仍为 `1800s`。
3. 确认保存后 Stargazer 立即收到一次请求并成功入队。
4. 确认 Worker 完成真实采集，指标进入 VictoriaMetrics。
5. 在保存成功后 5 分钟内确认任务详情出现真实执行结果和原始数据。
6. 等待后续周期，确认任务仍按 30 分钟执行。
7. 确认不存在临时短周期配置、额外 Telegraf 进程或持续重复触发。
8. 关闭功能开关后重复创建任务，确认系统安全退回原有周期行为。

## 13. 备选方案及不采用原因

### 13.1 临时缩短 Telegraf 周期

首次下发 1 分钟配置，采集后恢复用户周期。该方案需要两次配置下发；恢复失败会使昂贵采集长期高频运行，因此不采用。

### 13.2 节点执行 `telegraf --once`

该命令可能执行节点整份 Telegraf 配置，而非仅当前 CMDB 子配置，并增加进程冲突、资源峰值和跨平台兼容成本，因此不采用。

### 13.3 仅保留现有 4 分钟延迟同步

该方案只查询 VictoriaMetrics，不触发真实产数，无法解决首个 Telegraf ticker 之前无数据的问题，因此不采用。
