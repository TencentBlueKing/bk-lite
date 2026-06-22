# CMDB/Alert 富日志经 NATS 镜像到平台操作日志 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 CMDB `ChangeRecord` 与 Alert `OperatorLog` 的富内容(target、before/after、scenario/operator_object)经 NATS RPC `save_operation_log` 镜像进 `system_mgmt.OperationLog`,使平台操作日志自包含、信息不丢失。

**Architecture:** 不用信号(bulk_create 不触发 post_save)。在中央写入入口处理:CMDB 已中央化于 `apps/cmdb/utils/change_record.py`(3 函数);Alert 新增 `apps/alerts/utils/operator_log.py` helper 并把所有写入点改调它(其中 8 处服务层写入已汇聚在 2 个 `operator_log` staticmethod)。镜像经扩展后的 `save_operation_log` 同步、失败安全推送。`OperationLog` 加 `target_type/target_id/detail` 三字段承载富内容。

**Tech Stack:** Python 3.12 / Django 4.2 / DRF / NATS RPC(`apps.rpc.system_mgmt.SystemMgmt`)/ pytest + pytest-django。

**测试命令(本地 docker postgres,见 memory `local-dev-env-setup`):**
```
cd server && DB_ENGINE=postgresql DB_HOST=127.0.0.1 DB_NAME=weops_lite_2 DB_USER=postgres DB_PASSWORD=123456 DB_PORT=5432 INSTALL_APPS=cmdb,system_mgmt,alerts ENABLE_CELERY=true IS_LOCAL_RPC=1 uv run --extra dev --group dev pytest <path> -q -p no:sugar
```
首次加 `--create-db`(schema 变动后)。

**关键既有事实(已核实,verbatim):**
- `OperationLog`(`apps/system_mgmt/models/operation_log.py`)继承 `TimeInfo`,字段 `username/source_ip/app/action_type/summary/domain`;`ACTION_CREATE/UPDATE/DELETE/EXECUTE = "create"/"update"/"delete"/"execute"`。
- `save_operation_log` 现签名(`apps/system_mgmt/nats_api.py`):`(username, source_ip, app, action_type, summary="", domain="domain.com")`;RPC 包装在 `apps/rpc/system_mgmt.py`。
- JSONField 导入约定:`from django.db.models import JSONField`。
- system_mgmt 最新迁移 `0032_errorlog_stack_trace.py` → 新迁移 `0033`。
- CMDB `change_record.py` 3 函数:`create_change_record`、`batch_create_change_record`、`create_change_record_by_asso`(+ `create_custom_reporting_change_record` 是 `create_change_record` 的薄封装,自动覆盖)。常量在 `apps/cmdb/models/change_record.py`:类型 `CREATE_INST/UPDATE_INST/DELETE_INST/CREATE_INST_ASST/DELETE_INST_ASST/EXECUTE`;场景 `DEVICE_LIFECYCLE/RELATION_CHANGE/ORDINARY_ATTRIBUTE_CHANGE/COLLECT_AUTOMATION_CHANGE/MODEL_MANAGEMENT_CHANGE/CUSTOM_REPORTING_CHANGE`。
- Alert `OperatorLog`(`apps/alerts/models/operator_log.py`)字段 `operator/action/target_type/operator_object/target_id/overview`;`LogAction.ADD/MODIFY/DELETE/EXECUTE = "add"/"modify"/"delete"/"execute"`(`apps/alerts/constants/constants.py`)。

---

## File Structure

| 文件 | 责任 | 任务 |
|---|---|---|
| `server/apps/system_mgmt/models/operation_log.py` | OperationLog +target_type/target_id/detail | T1 |
| `server/apps/system_mgmt/migrations/0033_operationlog_target_detail.py` | 迁移 | T1 |
| `server/apps/system_mgmt/nats_api.py` | save_operation_log 加参 | T2 |
| `server/apps/rpc/system_mgmt.py` | RPC 包装加参 | T2 |
| `server/apps/cmdb/utils/change_record.py` | 3 函数内镜像推送(scenario 过滤) | T3 |
| `server/apps/alerts/utils/operator_log.py`(新) | record_operator_log / _bulk + 镜像 | T4 |
| `server/apps/alerts/service/incident_operator.py`、`service/alter_operator.py` | 2 staticmethod 改调 helper | T5 |
| `server/apps/alerts/views/{assignment_shield,strategy,incident,incident_update,system_setting}.py`、`common/{assignment,auto_close}.py` | 写入点改调 helper | T5 |
| `web/src/app/system-manager/components/security/operationLogs.tsx` | detail 详情抽屉 | T6(可后置) |
| 测试文件 | 各任务对应 | 全程 |

---

## Task 1: OperationLog 加 target_type/target_id/detail + 迁移

**Files:**
- Modify: `server/apps/system_mgmt/models/operation_log.py`
- Create: `server/apps/system_mgmt/migrations/0033_operationlog_target_detail.py`
- Test: `server/apps/system_mgmt/tests/test_operation_log_model_service.py`

- [ ] **Step 1: 写失败测试**

创建 `server/apps/system_mgmt/tests/test_operation_log_model_service.py`:
```python
import pytest

from apps.system_mgmt.models.operation_log import OperationLog


@pytest.mark.django_db
def test_operation_log_stores_target_and_detail():
    log = OperationLog.objects.create(
        username="alice", source_ip="1.2.3.4", app="cmdb", action_type="update",
        summary="编辑模型", target_type="host", target_id="42",
        detail={"before_data": {"a": 1}, "after_data": {"a": 2}, "scenario": "model_management_change"},
    )
    log.refresh_from_db()
    assert log.target_type == "host"
    assert log.target_id == "42"
    assert log.detail["after_data"] == {"a": 2}


@pytest.mark.django_db
def test_operation_log_target_detail_default_empty():
    log = OperationLog.objects.create(
        username="bob", source_ip="1.2.3.4", app="job", action_type="create", summary="x",
    )
    assert log.target_type == ""
    assert log.target_id == ""
    assert log.detail == {}
```

- [ ] **Step 2: 运行确认失败**

Run: `cd server && DB_ENGINE=postgresql DB_HOST=127.0.0.1 DB_NAME=weops_lite_2 DB_USER=postgres DB_PASSWORD=123456 DB_PORT=5432 INSTALL_APPS=cmdb,system_mgmt,alerts ENABLE_CELERY=true IS_LOCAL_RPC=1 uv run --extra dev --group dev pytest apps/system_mgmt/tests/test_operation_log_model_service.py -q -p no:sugar --create-db`
Expected: FAIL(`TypeError: unexpected keyword 'target_type'` 或字段不存在)。

- [ ] **Step 3: 改模型**

`operation_log.py`:顶部加 `from django.db.models import JSONField`(与 `from django.db import models` 并存)。在 `domain` 字段后新增:
```python
    target_type = models.CharField("Target Type", max_length=50, blank=True, default="", db_index=True)
    target_id = models.CharField("Target ID", max_length=100, blank=True, default="", db_index=True)
    detail = JSONField("Detail", default=dict, blank=True)
```
并把 `display_fields()` 列表追加 `"target_type", "target_id", "detail"`。

- [ ] **Step 4: 生成迁移**

Run: `cd server && DB_ENGINE=postgresql DB_HOST=127.0.0.1 DB_NAME=weops_lite_2 DB_USER=postgres DB_PASSWORD=123456 DB_PORT=5432 INSTALL_APPS=cmdb,system_mgmt,alerts ENABLE_CELERY=true IS_LOCAL_RPC=1 uv run python manage.py makemigrations system_mgmt`
Expected: 生成 `0033_*.py`(若文件名不同,重命名为 `0033_operationlog_target_detail.py` 并修正 dependencies 指向 `0032_errorlog_stack_trace`)。

- [ ] **Step 5: 运行确认通过**

Run: 同 Step 2(去掉 `--create-db` 之后亦可,首跑用 `--create-db`)。Expected: 2 passed。

- [ ] **Step 6: 提交**
```bash
git add server/apps/system_mgmt/models/operation_log.py server/apps/system_mgmt/migrations/0033_operationlog_target_detail.py server/apps/system_mgmt/tests/test_operation_log_model_service.py
git commit -m "feat(system_mgmt): OperationLog 增加 target_type/target_id/detail 字段"
```

---

## Task 2: 扩展 save_operation_log(NATS + RPC 包装)

**Files:**
- Modify: `server/apps/system_mgmt/nats_api.py`(`save_operation_log`)
- Modify: `server/apps/rpc/system_mgmt.py`(`SystemMgmt.save_operation_log`)
- Test: `server/apps/system_mgmt/tests/test_save_operation_log_service.py`

- [ ] **Step 1: 写失败测试**

创建 `server/apps/system_mgmt/tests/test_save_operation_log_service.py`:
```python
import pytest

from apps.system_mgmt.models.operation_log import OperationLog
from apps.system_mgmt.nats_api import save_operation_log


@pytest.mark.django_db
def test_save_operation_log_persists_target_and_detail():
    res = save_operation_log(
        username="alice", source_ip="internal", app="cmdb", action_type="update",
        summary="编辑模型", target_type="host", target_id="42",
        detail={"scenario": "model_management_change"},
    )
    assert res["result"] is True
    log = OperationLog.objects.get()
    assert (log.target_type, log.target_id) == ("host", "42")
    assert log.detail == {"scenario": "model_management_change"}


@pytest.mark.django_db
def test_save_operation_log_backward_compatible_without_new_params():
    res = save_operation_log(
        username="bob", source_ip="internal", app="job", action_type="create", summary="x",
    )
    assert res["result"] is True
    log = OperationLog.objects.get()
    assert log.target_type == "" and log.detail == {}


@pytest.mark.django_db
def test_save_operation_log_rejects_bad_action_type():
    res = save_operation_log(username="x", source_ip="internal", app="cmdb", action_type="frobnicate")
    assert res["result"] is False
```

- [ ] **Step 2: 运行确认失败**

Run: `cd server && DB_ENGINE=postgresql DB_HOST=127.0.0.1 DB_NAME=weops_lite_2 DB_USER=postgres DB_PASSWORD=123456 DB_PORT=5432 INSTALL_APPS=cmdb,system_mgmt,alerts ENABLE_CELERY=true IS_LOCAL_RPC=1 uv run --extra dev --group dev pytest apps/system_mgmt/tests/test_save_operation_log_service.py -q -p no:sugar`
Expected: FAIL(`unexpected keyword 'target_type'`)。

- [ ] **Step 3: 改 nats_api.py**

把 `save_operation_log` 签名与创建改为:
```python
@nats_client.register
def save_operation_log(username, source_ip, app, action_type, summary="", domain="domain.com",
                       target_type="", target_id="", detail=None):
    """保存操作日志(target_type/target_id/detail 为可选富内容)"""
    try:
        valid_actions = [
            OperationLog.ACTION_CREATE, OperationLog.ACTION_UPDATE,
            OperationLog.ACTION_DELETE, OperationLog.ACTION_EXECUTE,
        ]
        if action_type not in valid_actions:
            return {"result": False, "message": f"Invalid action_type. Must be one of: {', '.join(valid_actions)}"}
        OperationLog.objects.create(
            username=username, source_ip=source_ip, app=app, action_type=action_type,
            summary=summary, domain=domain,
            target_type=target_type or "", target_id=str(target_id or ""), detail=detail or {},
        )
        return {"result": True, "message": "Operation log saved successfully"}
    except Exception as e:
        logger.exception(f"Failed to save operation log: {e}")
        return {"result": False, "message": str(e)}
```

- [ ] **Step 4: 改 rpc/system_mgmt.py 包装**
```python
def save_operation_log(self, username, source_ip, app, action_type, summary="", domain="domain.com",
                       target_type="", target_id="", detail=None):
    return self.client.run(
        "save_operation_log", username=username, source_ip=source_ip, app=app, action_type=action_type,
        summary=summary, domain=domain, target_type=target_type, target_id=target_id, detail=detail,
    )
```

- [ ] **Step 5: 运行确认通过**

Run: 同 Step 2。Expected: 3 passed。

- [ ] **Step 6: 提交**
```bash
git add server/apps/system_mgmt/nats_api.py server/apps/rpc/system_mgmt.py server/apps/system_mgmt/tests/test_save_operation_log_service.py
git commit -m "feat(system_mgmt): save_operation_log 支持 target_type/target_id/detail(向后兼容)"
```

---

## Task 3: CMDB change_record 三函数内镜像推送(scenario 过滤)

**Files:**
- Modify: `server/apps/cmdb/utils/change_record.py`
- Test: `server/apps/cmdb/tests/test_change_record_mirror_service.py`

- [ ] **Step 1: 写失败测试**

创建 `server/apps/cmdb/tests/test_change_record_mirror_service.py`:
```python
from unittest.mock import patch

import pytest

from apps.cmdb.models.change_record import (
    CREATE_INST, MODEL_MANAGEMENT_CHANGE, ORDINARY_ATTRIBUTE_CHANGE,
)
from apps.cmdb.utils import change_record as cr


@pytest.mark.django_db
@patch("apps.cmdb.utils.change_record.SystemMgmt")
def test_management_scenario_is_mirrored(mock_sm):
    cr.create_change_record(
        inst_id=42, model_id="host", label="主机", _type=CREATE_INST,
        after_data={"name": "h1"}, operator="alice", message="新增模型 host",
        model_object="host", scenario=MODEL_MANAGEMENT_CHANGE,
    )
    call = mock_sm.return_value.save_operation_log
    assert call.called
    kw = call.call_args.kwargs
    assert kw["app"] == "cmdb"
    assert kw["action_type"] == "create"
    assert kw["target_id"] == "42"
    assert kw["detail"]["scenario"] == MODEL_MANAGEMENT_CHANGE
    assert kw["detail"]["after_data"] == {"name": "h1"}


@pytest.mark.django_db
@patch("apps.cmdb.utils.change_record.SystemMgmt")
def test_ordinary_attribute_change_is_NOT_mirrored(mock_sm):
    cr.create_change_record(
        inst_id=1, model_id="host", label="主机", _type=CREATE_INST,
        operator="alice", scenario=ORDINARY_ATTRIBUTE_CHANGE,
    )
    assert not mock_sm.return_value.save_operation_log.called


@pytest.mark.django_db
@patch("apps.cmdb.utils.change_record.SystemMgmt")
def test_mirror_failure_does_not_break_change_record(mock_sm):
    from apps.cmdb.models.change_record import ChangeRecord
    mock_sm.return_value.save_operation_log.side_effect = RuntimeError("nats down")
    cr.create_change_record(
        inst_id=7, model_id="host", label="主机", _type=CREATE_INST,
        operator="alice", scenario=MODEL_MANAGEMENT_CHANGE,
    )
    assert ChangeRecord.objects.filter(inst_id=7).exists()  # 源记录照常写入
```

- [ ] **Step 2: 运行确认失败**

Run: `cd server && DB_ENGINE=postgresql DB_HOST=127.0.0.1 DB_NAME=weops_lite_2 DB_USER=postgres DB_PASSWORD=123456 DB_PORT=5432 INSTALL_APPS=cmdb,system_mgmt,alerts ENABLE_CELERY=true IS_LOCAL_RPC=1 uv run --extra dev --group dev pytest apps/cmdb/tests/test_change_record_mirror_service.py -q -p no:sugar`
Expected: FAIL(`AttributeError`/`change_record` 无 `SystemMgmt`,或 mirror 未调用)。

- [ ] **Step 3: 在 change_record.py 顶部加导入与映射常量**

在现有 import 之后追加:
```python
from apps.cmdb.models.change_record import (
    CREATE_INST, UPDATE_INST, DELETE_INST, CREATE_INST_ASST, DELETE_INST_ASST, EXECUTE,
    COLLECT_AUTOMATION_CHANGE, MODEL_MANAGEMENT_CHANGE,
)
from apps.rpc.system_mgmt import SystemMgmt
from apps.core.logger import cmdb_logger as logger

# 仅这些管理/结构类场景镜像进平台操作日志(跳过高频实例数据变更)
_MIRROR_SCENARIOS = {MODEL_MANAGEMENT_CHANGE, COLLECT_AUTOMATION_CHANGE, CUSTOM_REPORTING_CHANGE, RELATION_CHANGE}
_TYPE_ACTION_MAP = {
    CREATE_INST: "create", UPDATE_INST: "update", DELETE_INST: "delete",
    CREATE_INST_ASST: "create", DELETE_INST_ASST: "delete", EXECUTE: "execute",
}


def _mirror_change_record(*, inst_id, model_id, _type, operator, scenario,
                          message="", model_object="", before_data=None, after_data=None):
    """把一条管理类 ChangeRecord 镜像进平台操作日志(失败安全)。"""
    if scenario not in _MIRROR_SCENARIOS:
        return
    try:
        SystemMgmt().save_operation_log(
            username=operator or "system",
            source_ip="internal",
            app="cmdb",
            action_type=_TYPE_ACTION_MAP.get(_type, "execute"),
            summary=message or f"{_type}: {model_object or model_id}",
            target_type=model_object or model_id,
            target_id=str(inst_id),
            detail={
                "before_data": before_data or {}, "after_data": after_data or {},
                "scenario": scenario, "model_object": model_object, "source": "change_record",
            },
        )
    except Exception as e:  # noqa: 镜像失败绝不影响源写入
        logger.warning(f"mirror change_record to operation_log failed: {e}")
```
注:`CUSTOM_REPORTING_CHANGE`、`RELATION_CHANGE`、`ORDINARY_ATTRIBUTE_CHANGE` 已在文件原有 import 中;若缺再补。`cmdb_logger` 若不存在,用 `from apps.core.logger import cmdb_logger as logger` 前先 grep 确认 logger 名,改成实际可用的。

- [ ] **Step 4: 在三个函数末尾调用镜像**

`create_change_record` 末尾(`ChangeRecord.objects.create(...)` 之后)加:
```python
    _mirror_change_record(
        inst_id=inst_id, model_id=model_id, _type=_type, operator=operator, scenario=scenario,
        message=message, model_object=model_object, before_data=before_data, after_data=after_data,
    )
```
`batch_create_change_record` 在 `bulk_create` 之后加:
```python
    for rec in change_records:
        _mirror_change_record(
            inst_id=rec.get("inst_id"), model_id=rec.get("model_id"), _type=_type,
            operator=operator, scenario=scenario, message=rec.get("message", ""),
            model_object=rec.get("model_object", ""),
            before_data=rec.get("before_data"), after_data=rec.get("after_data"),
        )
```
`create_change_record_by_asso` 在 `bulk_create` 之后加(scenario 默认 RELATION_CHANGE → 命中镜像):
```python
    for inst_info in [data["src"], data["dst"]]:
        if inst_info.get("model_id"):
            _mirror_change_record(
                inst_id=inst_info["_id"], model_id=inst_info["model_id"], _type=_type,
                operator=operator, scenario=scenario, message=message,
                model_object=OPERATOR_INSTANCE,
                before_data=change_data.get("before_data"), after_data=change_data.get("after_data"),
            )
```

- [ ] **Step 5: 运行确认通过**

Run: 同 Step 2。Expected: 3 passed。

- [ ] **Step 6: 回归 + 提交**

Run: `... uv run --extra dev --group dev pytest apps/cmdb/tests/test_change_record_pure.py apps/cmdb/tests/test_change_record_views.py -q -p no:sugar`(若存在;否则跑 `apps/cmdb/tests -k change_record`)。Expected: 不新增失败。
```bash
git add server/apps/cmdb/utils/change_record.py server/apps/cmdb/tests/test_change_record_mirror_service.py
git commit -m "feat(cmdb): change_record 管理类场景经 NATS 镜像进平台操作日志"
```

---

## Task 4: Alert operator_log helper(新增)

**Files:**
- Create: `server/apps/alerts/utils/operator_log.py`
- Test: `server/apps/alerts/tests/test_operator_log_mirror_service.py`

- [ ] **Step 1: 写失败测试**

创建 `server/apps/alerts/tests/test_operator_log_mirror_service.py`:
```python
from unittest.mock import patch

import pytest

from apps.alerts.constants.constants import LogAction, LogTargetType
from apps.alerts.models.operator_log import OperatorLog
from apps.alerts.utils.operator_log import record_operator_log, record_operator_logs_bulk


@pytest.mark.django_db
@patch("apps.alerts.utils.operator_log.SystemMgmt")
def test_record_operator_log_writes_and_mirrors(mock_sm):
    obj = record_operator_log(
        action=LogAction.ADD, target_type=LogTargetType.SYSTEM, operator="alice",
        operator_object="告警分派策略-创建", target_id="5", overview="创建告警分派策略[x]",
    )
    assert OperatorLog.objects.filter(id=obj.id).exists()
    kw = mock_sm.return_value.save_operation_log.call_args.kwargs
    assert kw["app"] == "alarm"
    assert kw["action_type"] == "create"          # add -> create
    assert kw["target_type"] == LogTargetType.SYSTEM
    assert kw["target_id"] == "5"
    assert kw["summary"] == "创建告警分派策略[x]"
    assert kw["detail"]["operator_object"] == "告警分派策略-创建"


@pytest.mark.django_db
@patch("apps.alerts.utils.operator_log.SystemMgmt")
def test_bulk_mirrors_each(mock_sm):
    items = [
        dict(action=LogAction.MODIFY, target_type=LogTargetType.ALERT, operator="system",
             operator_object="告警处理-自动分派", target_id=f"a{i}", overview="x")
        for i in range(3)
    ]
    objs = record_operator_logs_bulk(items)
    assert len(objs) == 3
    assert mock_sm.return_value.save_operation_log.call_count == 3


@pytest.mark.django_db
@patch("apps.alerts.utils.operator_log.SystemMgmt")
def test_mirror_failure_does_not_break_write(mock_sm):
    mock_sm.return_value.save_operation_log.side_effect = RuntimeError("nats down")
    obj = record_operator_log(
        action=LogAction.DELETE, target_type=LogTargetType.INCIDENT, operator="bob",
        operator_object="事故-删除", target_id="INC-1", overview="删",
    )
    assert OperatorLog.objects.filter(id=obj.id).exists()
```

- [ ] **Step 2: 运行确认失败**

Run: `cd server && DB_ENGINE=postgresql DB_HOST=127.0.0.1 DB_NAME=weops_lite_2 DB_USER=postgres DB_PASSWORD=123456 DB_PORT=5432 INSTALL_APPS=cmdb,system_mgmt,alerts ENABLE_CELERY=true IS_LOCAL_RPC=1 uv run --extra dev --group dev pytest apps/alerts/tests/test_operator_log_mirror_service.py -q -p no:sugar`
Expected: FAIL(模块 `apps.alerts.utils.operator_log` 不存在)。

- [ ] **Step 3: 新建 helper**

`server/apps/alerts/utils/operator_log.py`:
```python
from apps.alerts.constants.constants import LogAction
from apps.alerts.models.operator_log import OperatorLog
from apps.core.logger import alert_logger as logger  # 若 logger 名不同,grep apps/alerts 现有用法替换
from apps.rpc.system_mgmt import SystemMgmt

_ACTION_MAP = {
    LogAction.ADD: "create", LogAction.MODIFY: "update",
    LogAction.DELETE: "delete", LogAction.EXECUTE: "execute",
}


def _mirror(objs):
    for obj in objs:
        try:
            SystemMgmt().save_operation_log(
                username=obj.operator or "system",
                source_ip="internal",
                app="alarm",
                action_type=_ACTION_MAP.get(obj.action, "execute"),
                summary=obj.overview or "",
                target_type=obj.target_type or "",
                target_id=str(obj.target_id or ""),
                detail={"operator_object": obj.operator_object, "source": "operator_log"},
            )
        except Exception as e:  # noqa: 镜像失败绝不影响源写入
            logger.warning(f"mirror operator_log to operation_log failed: {e}")


def record_operator_log(**log_data):
    """写一条 OperatorLog 并镜像进平台操作日志。替代散落的 OperatorLog.objects.create(**log_data)。"""
    obj = OperatorLog.objects.create(**log_data)
    _mirror([obj])
    return obj


def record_operator_logs_bulk(items):
    """items: List[dict 或 OperatorLog 实例]。bulk_create + 镜像。"""
    objs = [i if isinstance(i, OperatorLog) else OperatorLog(**i) for i in items]
    OperatorLog.objects.bulk_create(objs)
    _mirror(objs)
    return objs
```

- [ ] **Step 4: 运行确认通过**

Run: 同 Step 2。Expected: 3 passed。

- [ ] **Step 5: 提交**
```bash
git add server/apps/alerts/utils/operator_log.py server/apps/alerts/tests/test_operator_log_mirror_service.py
git commit -m "feat(alerts): 新增 operator_log helper,写入即经 NATS 镜像(app=alarm)"
```

---

## Task 5: Alert 写入点改调 helper(重构)

**Files(全部 Modify):**
- `server/apps/alerts/service/incident_operator.py`(staticmethod，覆盖 3 服务写入)
- `server/apps/alerts/service/alter_operator.py`(staticmethod，覆盖 5 服务写入)
- `server/apps/alerts/views/assignment_shield.py`(6)、`views/strategy.py`(3)、`views/incident.py`(5)、`views/incident_update.py`(3)、`views/system_setting.py`(2)
- `server/apps/alerts/common/assignment.py`(1 bulk)、`common/auto_close.py`(1 bulk)

- [ ] **Step 1: 改两个 service staticmethod(覆盖 8 处服务写入)**

两个文件里的 `operator_log` staticmethod body 由 `OperatorLog.objects.create(**log_data)` 改为:
```python
        from apps.alerts.utils.operator_log import record_operator_log
        record_operator_log(**log_data)
```
(`incident_operator.py:209`、`alter_operator.py:591`)。其余调 `self.operator_log(log_data)` 的服务方法自动受益。

- [ ] **Step 2: 改 19 处 view 直写**

把这些文件中每处 `OperatorLog.objects.create(**log_data)` / `OperatorLog.objects.create(<kwargs>)` 改为 `record_operator_log(**log_data)` / `record_operator_log(<kwargs>)`,并在各文件顶部加 `from apps.alerts.utils.operator_log import record_operator_log`(替换原 `from apps.alerts.models.operator_log import OperatorLog` 若不再直接用):
- `views/assignment_shield.py`:6 处(行 50/65/80/164/179/194)。
- `views/strategy.py`:3 处(行 104/165/204)。
- `views/incident.py`:5 处(行 232/280/308,及 add_alerts 385、remove_alerts 425 的关键字形式)。
- `views/incident_update.py`:3 处(行 94/132/161,关键字形式)。
- `views/system_setting.py`:2 处(行 71/101)。

- [ ] **Step 3: 改 2 处 bulk**

- `common/assignment.py`:把构造 `bulk_data=[OperatorLog(...)]` + `OperatorLog.objects.bulk_create(bulk_data)` 改为构造同样的 `OperatorLog(...)` 列表后 `record_operator_logs_bulk(bulk_data)`(import 该函数)。
- `common/auto_close.py`:把 `OperatorLog.objects.bulk_create(self.bulk_logs, batch_size=200)` 改为 `record_operator_logs_bulk(self.bulk_logs)`。

- [ ] **Step 4: 运行 Alert 既有测试回归**

Run: `cd server && DB_ENGINE=postgresql DB_HOST=127.0.0.1 DB_NAME=weops_lite_2 DB_USER=postgres DB_PASSWORD=123456 DB_PORT=5432 INSTALL_APPS=cmdb,system_mgmt,alerts ENABLE_CELERY=true IS_LOCAL_RPC=1 uv run --extra dev --group dev pytest apps/alerts/tests -q -p no:sugar --continue-on-collection-errors`
Expected: 既有针对这些视图/服务的测试通过(OperatorLog 行为不变;镜像失败安全)。预存在的无关 collection error(若有)照旧,和 base 对比判断。

- [ ] **Step 5: 提交**
```bash
git add server/apps/alerts/service/incident_operator.py server/apps/alerts/service/alter_operator.py server/apps/alerts/views/assignment_shield.py server/apps/alerts/views/strategy.py server/apps/alerts/views/incident.py server/apps/alerts/views/incident_update.py server/apps/alerts/views/system_setting.py server/apps/alerts/common/assignment.py server/apps/alerts/common/auto_close.py
git commit -m "refactor(alerts): 所有 OperatorLog 写入改走 record_operator_log helper(统一镜像)"
```

---

## Task 6: 前端操作日志「详情」抽屉(可后置)

**Files:**
- Modify: `web/src/app/system-manager/components/security/operationLogs.tsx`
- Test: `web/scripts/operation-log-detail-test.ts`(tsx 脚本,纯函数)

- [ ] **Step 1: 抽出并测试详情判定纯函数**

`web/scripts/operation-log-detail-test.ts`:
```ts
import assert from 'node:assert/strict';
import { hasOperationDetail } from '../src/app/system-manager/utils/operationLogDetail';

assert.equal(hasOperationDetail({ detail: { after_data: { a: 1 } } }), true);
assert.equal(hasOperationDetail({ detail: {} }), false);
assert.equal(hasOperationDetail({}), false);
console.log('PASS');
```
新建 `web/src/app/system-manager/utils/operationLogDetail.ts`:
```ts
export function hasOperationDetail(row: { detail?: Record<string, any> }): boolean {
  return !!row.detail && Object.keys(row.detail).length > 0;
}
```

- [ ] **Step 2: 运行**

Run: `cd web && node_modules/.bin/tsx scripts/operation-log-detail-test.ts`。Expected: `PASS`。注册 `package.json` scripts `"test:operation-log-detail": "pnpm exec tsx scripts/operation-log-detail-test.ts"`。

- [ ] **Step 3: 接到表格**

在 `operationLogs.tsx`:`OperationLog` interface 加 `target_type?: string; target_id?: string; detail?: Record<string, any>;`。新增「详情」列(仅当 `hasOperationDetail(record)` 显示按钮),点击打开 Antd `Drawer`/`Modal`,渲染:`target_type`/`target_id`、`detail.scenario`/`detail.operator_object` 标签、`detail.before_data`/`detail.after_data` 用 `react-diff-viewer-continued`(仓库已有依赖)做前后对比。

- [ ] **Step 4: 校验 + 提交**

Run: `cd web && node_modules/.bin/tsx scripts/operation-log-detail-test.ts`(若本机 eslint 因 storybook 插件 ESM 问题跑不起,以 tsx 单测 + 人工核对为准)。
```bash
git add web/src/app/system-manager/components/security/operationLogs.tsx web/src/app/system-manager/utils/operationLogDetail.ts web/scripts/operation-log-detail-test.ts web/package.json
git commit -m "feat(system-manager): 操作日志详情抽屉渲染 target/before-after/scenario"
```

---

## Task 7: 端到端镜像回归

**Files:** 无改动,仅验证。

- [ ] **Step 1: 端到端镜像测试**

创建 `server/apps/system_mgmt/tests/test_audit_mirror_e2e_service.py`:
```python
import pytest

from apps.cmdb.models.change_record import CREATE_INST, MODEL_MANAGEMENT_CHANGE
from apps.cmdb.utils import change_record as cr
from apps.alerts.constants.constants import LogAction, LogTargetType
from apps.alerts.utils.operator_log import record_operator_log
from apps.system_mgmt.models.operation_log import OperationLog


@pytest.mark.django_db
def test_cmdb_management_change_mirrors_to_operation_log():
    # 本地 IS_LOCAL_RPC=1：save_operation_log 在进程内执行,真实落库
    cr.create_change_record(inst_id=99, model_id="host", label="主机", _type=CREATE_INST,
                            operator="alice", message="新增模型 host",
                            model_object="host", scenario=MODEL_MANAGEMENT_CHANGE)
    assert OperationLog.objects.filter(app="cmdb", target_id="99", action_type="create").exists()


@pytest.mark.django_db
def test_alert_operator_log_mirrors_to_operation_log():
    record_operator_log(action=LogAction.ADD, target_type=LogTargetType.SYSTEM, operator="bob",
                        operator_object="告警分派策略-创建", target_id="7", overview="创建[x]")
    assert OperationLog.objects.filter(app="alarm", target_id="7", action_type="create").exists()
```

- [ ] **Step 2: 跑全部接入测试**

Run: `cd server && DB_ENGINE=postgresql DB_HOST=127.0.0.1 DB_NAME=weops_lite_2 DB_USER=postgres DB_PASSWORD=123456 DB_PORT=5432 INSTALL_APPS=cmdb,system_mgmt,alerts ENABLE_CELERY=true IS_LOCAL_RPC=1 uv run --extra dev --group dev pytest apps/system_mgmt/tests/test_operation_log_model_service.py apps/system_mgmt/tests/test_save_operation_log_service.py apps/cmdb/tests/test_change_record_mirror_service.py apps/alerts/tests/test_operator_log_mirror_service.py apps/system_mgmt/tests/test_audit_mirror_e2e_service.py -q -p no:sugar`
Expected: all passed。

- [ ] **Step 3: cmdb/alerts/system_mgmt 回归对比 base(确认无新增失败)**

Run: `... uv run --extra dev --group dev pytest apps/cmdb apps/alerts apps/system_mgmt -q -p no:sugar --no-cov -o addopts="" --continue-on-collection-errors`,与改动前 base 跑同一命令对比;只接受预存在(neo4j/falkordb/job_mgmt collection error 等)失败。

- [ ] **Step 4: 提交**
```bash
git add server/apps/system_mgmt/tests/test_audit_mirror_e2e_service.py
git commit -m "test(system_mgmt): CMDB/Alert 日志经 NATS 镜像端到端回归"
```

---

## Self-Review 注记

- **Spec 覆盖**:schema(§8)=T1;RPC 扩展(§6)=T2;CMDB hook+scenario 过滤(§5.1/§7.1)=T3;Alert helper(§5.2/§7.2)=T4;Alert 重构(§5.2)=T5;前端 detail(§9)=T6;测试(§11)贯穿 + T7。错误处理(§10)在 T3/T4 的失败安全测试中验证。
- **scope 修正**:实际 Alert 写入点为 19 view 直写 + 8 服务(经 2 staticmethod)+ 2 bulk,比 spec「~15」多;T5 已按真实清单枚举,2 staticmethod 覆盖 8 处。
- **类型一致**:全程 `record_operator_log`/`record_operator_logs_bulk`/`_mirror_change_record`/`save_operation_log(...,target_type,target_id,detail)` 命名一致。
- **占位符**:无 TODO/TBD;每步含可执行代码/命令。
- **待实现期核对**:各 app 的 logger 名(`cmdb_logger`/`alert_logger`)需 grep 现有用法确认后替换;`change_record.py` 现有 import 已含部分常量,补齐缺失项即可。
