# CMDB 数据治理健康度快照 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在商业版后端实现 CMDB 数据治理完整性/新鲜度健康度每日聚合快照，并在社区版采集链路补齐自动采集实例级操作日志作为新鲜度事实源。

**Architecture:** 社区侧在采集成功结果处写实例级 `ChangeRecord`，并保留采集企业扩展 no-op hook；商业版在 `cmdb_enterprise/governance` 下实现快照模型、计算服务、Celery 任务和手动命令。健康度任务读取模型治理标记、图数据库实例和实例级 `ChangeRecord`，按 `global/model/organization/model_organization` 四类维度 upsert 聚合快照。

**Tech Stack:** Python 3.12, Django 4.2, Celery, Django ORM, CMDB GraphClient, pytest.

---

## 文件结构

- Modify: `server/apps/cmdb/collect/extensions.py`
  - 为采集企业扩展契约增加 `on_collect_instances_applied(management, result)` no-op hook。
- Modify: `server/apps/cmdb/collection/common.py`
  - 在采集 `controller()` 与选择字段采集 `update()` 完成后写实例级操作日志并调用采集扩展 hook。
- Create: `server/apps/cmdb/collection/change_records.py`
  - 自动采集实例级 `ChangeRecord` 批量构造与写入，属于社区版 CMDB 基础历史能力。
- Create: `enterprise/server/apps/cmdb_enterprise/governance/__init__.py`
  - 治理健康度能力包入口。
- Create: `enterprise/server/apps/cmdb_enterprise/governance/constants.py`
  - 维度、时效窗口、日志场景、忽略字段常量。
- Create: `enterprise/server/apps/cmdb_enterprise/governance/models.py`
  - `CmdbGovernanceHealthSnapshot` 聚合快照模型。
- Modify: `enterprise/server/apps/cmdb_enterprise/models/__init__.py`
  - 聚合 governance 模型，确保 Django migration 能发现。
- Modify: `enterprise/server/apps/cmdb_enterprise/collect/provider.py`
  - 仅注册商业版采集对象树、插件包与 NodeParams 包，不写采集实例操作日志。
- Create: `enterprise/server/apps/cmdb_enterprise/governance/services.py`
  - 模型治理配置读取、空值判断、操作日志解释、健康度计算与快照 upsert。
- Create: `enterprise/server/apps/cmdb_enterprise/governance/tasks.py`
  - Celery 周期任务入口。
- Modify: `enterprise/server/apps/cmdb_enterprise/tasks/__init__.py`
  - 导入治理健康度任务，保证 Celery autodiscover 能发现。
- Modify: `enterprise/server/apps/cmdb_enterprise/config.py`
  - 增加每日 03:30 健康度快照任务。
- Create: `enterprise/server/apps/cmdb_enterprise/management/__init__.py`
- Create: `enterprise/server/apps/cmdb_enterprise/management/commands/__init__.py`
- Create: `enterprise/server/apps/cmdb_enterprise/management/commands/calculate_cmdb_governance_health.py`
  - 手动触发指定日期快照。
- Create: `enterprise/server/apps/cmdb_enterprise/migrations/0003_cmdbgovernancehealthsnapshot.py`
  - 新增聚合快照表。
- Create: `enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py`
  - 完整性、新鲜度、聚合快照服务测试。
- Create: `server/apps/cmdb/tests/test_collect_change_records.py`
  - 自动采集实例级日志补齐测试。
- Modify: `server/apps/cmdb/tests/test_enterprise_extensions.py`
  - 社区采集扩展默认 no-op 行为测试。

用户已要求文档和代码一起提交；本计划执行时不做中间 git commit。每个任务末尾用 `git diff --check` 和聚焦测试替代提交步骤。

---

### Task 1: 扩展采集企业契约并保持社区 no-op

**Files:**
- Modify: `server/apps/cmdb/collect/extensions.py`
- Test: `server/apps/cmdb/tests/test_enterprise_extensions.py`

- [ ] **Step 1: 写失败测试**

在 `server/apps/cmdb/tests/test_enterprise_extensions.py` 增加测试，确认社区默认采集扩展有采集写库后置 hook 且调用无副作用：

```python
def test_collect_default_after_apply_hook_is_noop():
    ext = CollectEnterpriseExtension()

    assert ext.on_collect_instances_applied(management=object(), result={"add": {"success": []}}) is None
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd server && uv run pytest apps/cmdb/tests/test_enterprise_extensions.py::test_collect_default_after_apply_hook_is_noop -q
```

Expected: FAIL，错误包含 `AttributeError: 'CollectEnterpriseExtension' object has no attribute 'on_collect_instances_applied'`。

- [ ] **Step 3: 实现 no-op hook**

修改 `server/apps/cmdb/collect/extensions.py`，将 dataclass 改为带默认方法的普通类，保留原有字段语义：

```python
"""采集能力域的企业版扩展契约（社区侧门面）。"""

from dataclasses import dataclass, field

from apps.cmdb.extensions import registry


@dataclass(frozen=True)
class CollectEnterpriseExtension:
    collect_tree: list = field(default_factory=list)
    plugin_packages: tuple = ()
    node_param_packages: tuple = ()

    def on_collect_instances_applied(self, *, management, result):
        """采集实例写库后的企业版扩展点。社区默认 no-op。"""
        return None


_EMPTY_COLLECT_EXTENSION = CollectEnterpriseExtension()


def get_collect_enterprise_extension() -> CollectEnterpriseExtension:
    return registry.get("collect", _EMPTY_COLLECT_EXTENSION)
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
cd server && uv run pytest apps/cmdb/tests/test_enterprise_extensions.py::test_collect_default_after_apply_hook_is_noop -q
```

Expected: PASS。

- [ ] **Step 5: 检查 diff**

Run:

```bash
cd server && git diff --check -- apps/cmdb/collect/extensions.py apps/cmdb/tests/test_enterprise_extensions.py
```

Expected: 无输出。

---

### Task 2: 在采集写库完成后写社区操作日志并调用扩展 hook

**Files:**
- Modify: `server/apps/cmdb/collection/common.py`
- Test: `server/apps/cmdb/tests/test_enterprise_extensions.py`

- [ ] **Step 1: 写失败测试**

在 `server/apps/cmdb/tests/test_enterprise_extensions.py` 增加一个针对 `Management.controller()` 的轻量测试，避免真实图数据库：

```python
def test_collection_management_controller_calls_collect_extension_hook(monkeypatch):
    from apps.cmdb.collection import common

    calls = []

    class FakeExtension:
        def on_collect_instances_applied(self, *, management, result):
            calls.append((management, result))

    monkeypatch.setattr(common, "get_collect_enterprise_extension", lambda: FakeExtension())
    monkeypatch.setattr(common.Management, "delete_inst", lambda self, inst_list: {"success": [], "failed": []})
    monkeypatch.setattr(common.Management, "add_inst", lambda self, inst_list: {"success": [{"inst_info": {"_id": 1}}], "failed": []})
    monkeypatch.setattr(common.Management, "update_inst", lambda self, inst_list: {"success": [], "failed": []})
    monkeypatch.setattr(common.Management, "get_check_attr_map", lambda self: {"is_only": {}, "is_required": {}, "editable": {}})

    management = common.Management(
        organization=[1],
        inst_name="demo",
        model_id="host",
        old_data=[],
        new_data=[{"inst_name": "host-a"}],
        unique_keys=["inst_name"],
        collect_time="2026-06-11T03:30:00+08:00",
        task_id=7,
    )

    result = management.controller()

    assert calls == [(management, result)]
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd server && uv run pytest apps/cmdb/tests/test_enterprise_extensions.py::test_collection_management_controller_calls_collect_extension_hook -q
```

Expected: FAIL，`calls == []`。

- [ ] **Step 3: 添加 hook 调用**

修改 `server/apps/cmdb/collection/common.py`：

```python
from apps.cmdb.collect.extensions import get_collect_enterprise_extension
```

并修改 `controller()`：

```python
    def controller(self):
        delete_result = self.delete_inst(self.delete_list)
        add_result = self.add_inst(self.add_list)
        update_result = self.update_inst(self.update_list)
        result = dict(add=add_result, update=update_result, delete=delete_result)
        get_collect_enterprise_extension().on_collect_instances_applied(management=self, result=result)
        return result
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
cd server && uv run pytest apps/cmdb/tests/test_enterprise_extensions.py::test_collection_management_controller_calls_collect_extension_hook -q
```

Expected: PASS。

- [ ] **Step 5: 检查 diff**

Run:

```bash
cd server && git diff --check -- apps/cmdb/collection/common.py apps/cmdb/tests/test_enterprise_extensions.py
```

Expected: 无输出。

---

### Task 3: 创建治理常量和快照模型

**Files:**
- Create: `enterprise/server/apps/cmdb_enterprise/governance/__init__.py`
- Create: `enterprise/server/apps/cmdb_enterprise/governance/constants.py`
- Create: `enterprise/server/apps/cmdb_enterprise/governance/models.py`
- Modify: `enterprise/server/apps/cmdb_enterprise/models/__init__.py`
- Create: `enterprise/server/apps/cmdb_enterprise/migrations/0003_cmdbgovernancehealthsnapshot.py`
- Test: `enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py`

- [ ] **Step 1: 写失败测试**

创建 `enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py`，先覆盖快照模型的 key 归一化：

```python
import importlib
from pathlib import Path

import pytest

import apps

ENTERPRISE_APPS_PATH = str(Path(__file__).resolve().parents[2])
if ENTERPRISE_APPS_PATH not in apps.__path__:
    apps.__path__.append(ENTERPRISE_APPS_PATH)

snapshot_models = importlib.import_module("apps.cmdb_enterprise.governance.models")
CmdbGovernanceHealthSnapshot = snapshot_models.CmdbGovernanceHealthSnapshot


@pytest.mark.django_db
def test_health_snapshot_normalizes_unique_keys():
    row = CmdbGovernanceHealthSnapshot.objects.create(
        snapshot_date="2026-06-11",
        dimension="global",
        total_count=0,
        complete_count=0,
        fresh_count=0,
        healthy_count=0,
    )

    assert row.model_key == ""
    assert row.organization_key == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py::test_health_snapshot_normalizes_unique_keys -q
```

Expected: FAIL，错误包含 `ModuleNotFoundError: No module named 'apps.cmdb_enterprise.governance'`。

- [ ] **Step 3: 创建常量**

创建 `enterprise/server/apps/cmdb_enterprise/governance/__init__.py`：

```python
"""CMDB 数据治理健康度商业版能力。"""
```

创建 `enterprise/server/apps/cmdb_enterprise/governance/constants.py`：

```python
DIMENSION_GLOBAL = "global"
DIMENSION_MODEL = "model"
DIMENSION_ORGANIZATION = "organization"
DIMENSION_MODEL_ORGANIZATION = "model_organization"

DIMENSION_CHOICES = (
    (DIMENSION_GLOBAL, "全局"),
    (DIMENSION_MODEL, "模型"),
    (DIMENSION_ORGANIZATION, "组织"),
    (DIMENSION_MODEL_ORGANIZATION, "模型+组织"),
)

FRESHNESS_TIMELY = "timely"
FRESHNESS_OCCASIONAL = "occasional"
FRESHNESS_STABLE = "stable"

FRESHNESS_WINDOWS_DAYS = {
    FRESHNESS_TIMELY: 7,
    FRESHNESS_OCCASIONAL: 90,
}

SYSTEM_DIFF_IGNORED_FIELDS = {
    "_id",
    "id",
    "_labels",
    "_display",
    "_creator",
    "model_id",
    "organization",
    "collect_task",
    "collect_time",
    "auto_collect",
}
```

- [ ] **Step 4: 创建模型并聚合导入**

创建 `enterprise/server/apps/cmdb_enterprise/governance/models.py`：

```python
from django.db import models

from apps.core.models.time_info import TimeInfo
from apps.cmdb_enterprise.governance.constants import DIMENSION_CHOICES


class CmdbGovernanceHealthSnapshot(TimeInfo):
    snapshot_date = models.DateField(db_index=True, verbose_name="快照日期")
    dimension = models.CharField(max_length=32, choices=DIMENSION_CHOICES, db_index=True, verbose_name="聚合维度")
    model_id = models.CharField(max_length=64, blank=True, default="", db_index=True, verbose_name="模型ID")
    organization_id = models.BigIntegerField(null=True, blank=True, db_index=True, verbose_name="组织ID")
    model_key = models.CharField(max_length=64, blank=True, default="", db_index=True, verbose_name="模型唯一键")
    organization_key = models.BigIntegerField(default=0, db_index=True, verbose_name="组织唯一键")
    total_count = models.PositiveIntegerField(default=0, verbose_name="纳入治理资产数")
    complete_count = models.PositiveIntegerField(default=0, verbose_name="完整性达标资产数")
    fresh_count = models.PositiveIntegerField(default=0, verbose_name="新鲜度达标资产数")
    healthy_count = models.PositiveIntegerField(default=0, verbose_name="完全健康资产数")
    completeness_score = models.FloatField(null=True, blank=True, verbose_name="完整性健康度")
    freshness_score = models.FloatField(null=True, blank=True, verbose_name="新鲜度健康度")
    overall_score = models.FloatField(null=True, blank=True, verbose_name="总健康度")
    metadata = models.JSONField(default=dict, verbose_name="扩展信息")

    class Meta:
        app_label = "cmdb_enterprise"
        db_table = "cmdb_governance_health_snapshot"
        verbose_name = "CMDB 数据治理健康度快照"
        verbose_name_plural = verbose_name
        unique_together = (("snapshot_date", "dimension", "model_key", "organization_key"),)
        indexes = [
            models.Index(fields=["snapshot_date", "dimension"], name="idx_cg_snapshot_date_dim"),
            models.Index(fields=["dimension", "model_key"], name="idx_cg_snapshot_model"),
            models.Index(fields=["dimension", "organization_key"], name="idx_cg_snapshot_org"),
        ]

    def save(self, *args, **kwargs):
        self.model_key = self.model_id or ""
        self.organization_key = int(self.organization_id or 0)
        super().save(*args, **kwargs)
```

修改 `enterprise/server/apps/cmdb_enterprise/models/__init__.py`：

```python
"""cmdb_enterprise overlay models（各商业域模型在此聚合）。"""
from apps.cmdb_enterprise.models.file_object import *  # noqa
from apps.cmdb_enterprise.custom_reporting.models import *  # noqa
from apps.cmdb_enterprise.governance.models import *  # noqa
```

- [ ] **Step 5: 创建 migration**

创建 `enterprise/server/apps/cmdb_enterprise/migrations/0003_cmdbgovernancehealthsnapshot.py`：

```python
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb_enterprise", "0002_customreportingbatch_customreportingcleanupreview_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="CmdbGovernanceHealthSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("snapshot_date", models.DateField(db_index=True, verbose_name="快照日期")),
                ("dimension", models.CharField(choices=[("global", "全局"), ("model", "模型"), ("organization", "组织"), ("model_organization", "模型+组织")], db_index=True, max_length=32, verbose_name="聚合维度")),
                ("model_id", models.CharField(blank=True, db_index=True, default="", max_length=64, verbose_name="模型ID")),
                ("organization_id", models.BigIntegerField(blank=True, db_index=True, null=True, verbose_name="组织ID")),
                ("model_key", models.CharField(blank=True, db_index=True, default="", max_length=64, verbose_name="模型唯一键")),
                ("organization_key", models.BigIntegerField(db_index=True, default=0, verbose_name="组织唯一键")),
                ("total_count", models.PositiveIntegerField(default=0, verbose_name="纳入治理资产数")),
                ("complete_count", models.PositiveIntegerField(default=0, verbose_name="完整性达标资产数")),
                ("fresh_count", models.PositiveIntegerField(default=0, verbose_name="新鲜度达标资产数")),
                ("healthy_count", models.PositiveIntegerField(default=0, verbose_name="完全健康资产数")),
                ("completeness_score", models.FloatField(blank=True, null=True, verbose_name="完整性健康度")),
                ("freshness_score", models.FloatField(blank=True, null=True, verbose_name="新鲜度健康度")),
                ("overall_score", models.FloatField(blank=True, null=True, verbose_name="总健康度")),
                ("metadata", models.JSONField(default=dict, verbose_name="扩展信息")),
            ],
            options={
                "verbose_name": "CMDB 数据治理健康度快照",
                "verbose_name_plural": "CMDB 数据治理健康度快照",
                "db_table": "cmdb_governance_health_snapshot",
                "unique_together": {("snapshot_date", "dimension", "model_key", "organization_key")},
            },
        ),
        migrations.AddIndex(
            model_name="cmdbgovernancehealthsnapshot",
            index=models.Index(fields=["snapshot_date", "dimension"], name="idx_cg_snapshot_date_dim"),
        ),
        migrations.AddIndex(
            model_name="cmdbgovernancehealthsnapshot",
            index=models.Index(fields=["dimension", "model_key"], name="idx_cg_snapshot_model"),
        ),
        migrations.AddIndex(
            model_name="cmdbgovernancehealthsnapshot",
            index=models.Index(fields=["dimension", "organization_key"], name="idx_cg_snapshot_org"),
        ),
    ]
```

- [ ] **Step 6: 运行测试确认通过**

Run:

```bash
cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py::test_health_snapshot_normalizes_unique_keys -q
```

Expected: PASS。

- [ ] **Step 7: 检查 diff**

Run:

```bash
cd server && git diff --check -- ../enterprise/server/apps/cmdb_enterprise/governance ../enterprise/server/apps/cmdb_enterprise/models/__init__.py ../enterprise/server/apps/cmdb_enterprise/migrations/0003_cmdbgovernancehealthsnapshot.py
```

Expected: 无输出。

---

### Task 4: 实现治理字段解析与基础判断函数

**Files:**
- Modify: `enterprise/server/apps/cmdb_enterprise/governance/services.py`
- Test: `enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py`

- [ ] **Step 1: 写失败测试**

在 `test_governance_health_service.py` 增加：

```python
services = importlib.import_module("apps.cmdb_enterprise.governance.services")


def test_build_governance_model_config_filters_fields():
    attrs = [
        {"attr_id": "owner", "governance": {"key_attribute": True, "freshness": ""}},
        {"attr_id": "status", "governance": {"key_attribute": False, "freshness": "timely"}},
        {"attr_id": "serial", "governance": {"key_attribute": False, "freshness": "occasional"}},
        {"attr_id": "rack", "governance": {"key_attribute": False, "freshness": "stable"}},
    ]

    config = services.build_governance_model_config("host", attrs)

    assert config.model_id == "host"
    assert config.key_attribute_ids == ["owner"]
    assert config.freshness_windows == {"status": 7, "serial": 90}
    assert config.is_governed is True


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),
        ("", False),
        ("   ", False),
        ([], False),
        ({}, False),
        (0, True),
        (False, True),
        ("0", True),
        ([0], True),
        ({"value": None}, True),
    ],
)
def test_has_filled_value(value, expected):
    assert services.has_filled_value(value) is expected
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py::test_build_governance_model_config_filters_fields ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py::test_has_filled_value -q
```

Expected: FAIL，错误包含 `ModuleNotFoundError` 或 `AttributeError`。

- [ ] **Step 3: 实现基础服务函数**

创建或修改 `enterprise/server/apps/cmdb_enterprise/governance/services.py`：

```python
from dataclasses import dataclass
from datetime import date, datetime, time

from django.utils import timezone

from apps.cmdb_enterprise.governance.constants import FRESHNESS_WINDOWS_DAYS


@dataclass(frozen=True)
class GovernanceModelConfig:
    model_id: str
    key_attribute_ids: list[str]
    freshness_windows: dict[str, int]

    @property
    def is_governed(self) -> bool:
        return bool(self.key_attribute_ids or self.freshness_windows)


def build_governance_model_config(model_id: str, attrs: list[dict]) -> GovernanceModelConfig:
    key_attribute_ids: list[str] = []
    freshness_windows: dict[str, int] = {}
    for attr in attrs or []:
        attr_id = attr.get("attr_id")
        if not attr_id:
            continue
        governance = attr.get("governance") or {}
        if governance.get("key_attribute") is True:
            key_attribute_ids.append(attr_id)
        freshness = governance.get("freshness") or ""
        if freshness in FRESHNESS_WINDOWS_DAYS:
            freshness_windows[attr_id] = FRESHNESS_WINDOWS_DAYS[freshness]
    return GovernanceModelConfig(
        model_id=model_id,
        key_attribute_ids=key_attribute_ids,
        freshness_windows=freshness_windows,
    )


def has_filled_value(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def snapshot_cutoff(snapshot_date: date) -> datetime:
    return timezone.make_aware(datetime.combine(snapshot_date, time.max))
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py::test_build_governance_model_config_filters_fields ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py::test_has_filled_value -q
```

Expected: PASS。

- [ ] **Step 5: 检查 diff**

Run:

```bash
cd server && git diff --check -- ../enterprise/server/apps/cmdb_enterprise/governance/services.py ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py
```

Expected: 无输出。

---

### Task 5: 实现操作日志解释与字段核实时间计算

**Files:**
- Modify: `enterprise/server/apps/cmdb_enterprise/governance/services.py`
- Test: `enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py`

- [ ] **Step 1: 写失败测试**

在 `test_governance_health_service.py` 增加：

```python
from datetime import timedelta
from django.utils import timezone

from apps.cmdb.models.change_record import (
    ChangeRecord,
    COLLECT_AUTOMATION_CHANGE,
    ORDINARY_ATTRIBUTE_CHANGE,
    CREATE_INST,
    UPDATE_INST,
)
from apps.cmdb.constants.constants import INSTANCE, OPERATOR_INSTANCE


@pytest.mark.django_db
def test_collect_change_record_verifies_all_freshness_fields():
    created_at = timezone.now() - timedelta(days=2)
    ChangeRecord.objects.create(
        inst_id=101,
        model_id="host",
        label=INSTANCE,
        type=UPDATE_INST,
        scenario=COLLECT_AUTOMATION_CHANGE,
        model_object=OPERATOR_INSTANCE,
        after_data={"_id": 101, "status": "running"},
        created_at=created_at,
    )
    config = services.GovernanceModelConfig("host", [], {"status": 7, "version": 90})

    verified = services.load_verified_field_times(
        inst_ids=[101],
        configs={"host": config},
        snapshot_at=timezone.now(),
    )

    assert set(verified[101]) == {"status", "version"}


@pytest.mark.django_db
def test_ordinary_update_verifies_only_changed_fields():
    record_time = timezone.now() - timedelta(days=1)
    ChangeRecord.objects.create(
        inst_id=102,
        model_id="host",
        label=INSTANCE,
        type=UPDATE_INST,
        scenario=ORDINARY_ATTRIBUTE_CHANGE,
        model_object=OPERATOR_INSTANCE,
        before_data={"status": "running", "version": "1.0"},
        after_data={"status": "stopped", "version": "1.0"},
        created_at=record_time,
    )
    config = services.GovernanceModelConfig("host", [], {"status": 7, "version": 90})

    verified = services.load_verified_field_times(
        inst_ids=[102],
        configs={"host": config},
        snapshot_at=timezone.now(),
    )

    assert "status" in verified[102]
    assert "version" not in verified[102]
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py::test_collect_change_record_verifies_all_freshness_fields ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py::test_ordinary_update_verifies_only_changed_fields -q
```

Expected: FAIL，错误包含 `AttributeError: module ... has no attribute 'load_verified_field_times'`。

- [ ] **Step 3: 实现日志解释**

修改 `enterprise/server/apps/cmdb_enterprise/governance/services.py`，追加：

```python
from collections import defaultdict

from apps.cmdb.constants.constants import INSTANCE, OPERATOR_INSTANCE
from apps.cmdb.models.change_record import (
    COLLECT_AUTOMATION_CHANGE,
    CREATE_INST,
    DEVICE_LIFECYCLE,
    ORDINARY_ATTRIBUTE_CHANGE,
    UPDATE_INST,
    ChangeRecord,
)


FULL_INSTANCE_VERIFY_SCENARIOS = {COLLECT_AUTOMATION_CHANGE}
FIELD_CHANGE_VERIFY_SCENARIOS = {ORDINARY_ATTRIBUTE_CHANGE, DEVICE_LIFECYCLE}


def _changed_fields(before_data: dict, after_data: dict, candidate_fields: set[str]) -> set[str]:
    changed = set()
    before_data = before_data or {}
    after_data = after_data or {}
    for field in candidate_fields:
        if before_data.get(field) != after_data.get(field):
            changed.add(field)
    return changed


def load_verified_field_times(
    *,
    inst_ids: list[int],
    configs: dict[str, GovernanceModelConfig],
    snapshot_at: datetime,
) -> dict[int, dict[str, datetime]]:
    result: dict[int, dict[str, datetime]] = defaultdict(dict)
    if not inst_ids:
        return result

    records = (
        ChangeRecord.objects.filter(
            inst_id__in=inst_ids,
            created_at__lte=snapshot_at,
            label=INSTANCE,
            model_object=OPERATOR_INSTANCE,
            type__in=[CREATE_INST, UPDATE_INST],
        )
        .order_by("-created_at")
        .only("inst_id", "model_id", "type", "scenario", "before_data", "after_data", "created_at")
    )

    for record in records:
        config = configs.get(record.model_id)
        if not config or not config.freshness_windows:
            continue
        freshness_fields = set(config.freshness_windows)
        if record.scenario in FULL_INSTANCE_VERIFY_SCENARIOS:
            fields = freshness_fields
        elif record.scenario in FIELD_CHANGE_VERIFY_SCENARIOS:
            if record.type == CREATE_INST:
                fields = {field for field in freshness_fields if field in (record.after_data or {})}
            else:
                fields = _changed_fields(record.before_data or {}, record.after_data or {}, freshness_fields)
        else:
            continue
        for field in fields:
            if field not in result[record.inst_id]:
                result[record.inst_id][field] = record.created_at
    return result
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py::test_collect_change_record_verifies_all_freshness_fields ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py::test_ordinary_update_verifies_only_changed_fields -q
```

Expected: PASS。

- [ ] **Step 5: 检查 diff**

Run:

```bash
cd server && git diff --check -- ../enterprise/server/apps/cmdb_enterprise/governance/services.py ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py
```

Expected: 无输出。

---

### Task 6: 实现实例健康判断与维度聚合 upsert

**Files:**
- Modify: `enterprise/server/apps/cmdb_enterprise/governance/services.py`
- Test: `enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py`

- [ ] **Step 1: 写失败测试**

在 `test_governance_health_service.py` 增加：

```python
@pytest.mark.django_db
def test_calculate_instance_health_and_aggregate_snapshots(monkeypatch):
    snapshot_date = date(2026, 6, 11)
    snapshot_at = services.snapshot_cutoff(snapshot_date)
    configs = {
        "host": services.GovernanceModelConfig("host", ["owner"], {"status": 7}),
    }
    instances_by_model = {
        "host": [
            {"_id": 1, "model_id": "host", "owner": "alice", "status": "running", "organization": [10, 20]},
            {"_id": 2, "model_id": "host", "owner": "", "status": "running", "organization": [10]},
        ]
    }
    verified = {
        1: {"status": snapshot_at},
        2: {"status": snapshot_at},
    }

    summary = services.calculate_and_store_snapshots(
        snapshot_date=snapshot_date,
        configs=configs,
        instances_by_model=instances_by_model,
        verified_times=verified,
    )

    assert summary["snapshots"] == 5
    global_row = CmdbGovernanceHealthSnapshot.objects.get(dimension="global")
    assert global_row.total_count == 2
    assert global_row.complete_count == 1
    assert global_row.fresh_count == 2
    assert global_row.healthy_count == 1
    org_10 = CmdbGovernanceHealthSnapshot.objects.get(dimension="organization", organization_id=10)
    assert org_10.total_count == 2
    org_20 = CmdbGovernanceHealthSnapshot.objects.get(dimension="organization", organization_id=20)
    assert org_20.total_count == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py::test_calculate_instance_health_and_aggregate_snapshots -q
```

Expected: FAIL，错误包含 `AttributeError: module ... has no attribute 'calculate_and_store_snapshots'`。

- [ ] **Step 3: 实现聚合器**

修改 `enterprise/server/apps/cmdb_enterprise/governance/services.py`，追加：

```python
from dataclasses import dataclass

from apps.cmdb_enterprise.governance.constants import (
    DIMENSION_GLOBAL,
    DIMENSION_MODEL,
    DIMENSION_MODEL_ORGANIZATION,
    DIMENSION_ORGANIZATION,
)
from apps.cmdb_enterprise.governance.models import CmdbGovernanceHealthSnapshot


@dataclass
class HealthCounter:
    total_count: int = 0
    complete_count: int = 0
    fresh_count: int = 0
    healthy_count: int = 0

    def add(self, *, is_complete: bool, is_fresh: bool) -> None:
        self.total_count += 1
        if is_complete:
            self.complete_count += 1
        if is_fresh:
            self.fresh_count += 1
        if is_complete and is_fresh:
            self.healthy_count += 1


def _score(part: int, total: int):
    if total == 0:
        return None
    return part / total


def is_instance_complete(instance: dict, config: GovernanceModelConfig) -> bool:
    return all(has_filled_value(instance.get(field)) for field in config.key_attribute_ids)


def is_instance_fresh(instance: dict, config: GovernanceModelConfig, verified_times: dict[str, datetime], snapshot_at: datetime) -> bool:
    for field, days in config.freshness_windows.items():
        verified_at = verified_times.get(field)
        if not verified_at:
            return False
        if snapshot_at - verified_at > timezone.timedelta(days=days):
            return False
    return True


def _counter_key(dimension: str, model_id: str = "", organization_id: int | None = None):
    return dimension, model_id or "", int(organization_id or 0)


def calculate_and_store_snapshots(
    *,
    snapshot_date: date,
    configs: dict[str, GovernanceModelConfig],
    instances_by_model: dict[str, list[dict]],
    verified_times: dict[int, dict[str, datetime]],
) -> dict:
    snapshot_at = snapshot_cutoff(snapshot_date)
    counters: dict[tuple, HealthCounter] = defaultdict(HealthCounter)

    for model_id, instances in instances_by_model.items():
        config = configs[model_id]
        for instance in instances:
            inst_id = int(instance["_id"])
            is_complete = is_instance_complete(instance, config)
            is_fresh = is_instance_fresh(instance, config, verified_times.get(inst_id, {}), snapshot_at)
            org_ids = [int(org_id) for org_id in (instance.get("organization") or []) if org_id not in (None, "")]

            counters[_counter_key(DIMENSION_GLOBAL)].add(is_complete=is_complete, is_fresh=is_fresh)
            counters[_counter_key(DIMENSION_MODEL, model_id=model_id)].add(is_complete=is_complete, is_fresh=is_fresh)
            for org_id in org_ids:
                counters[_counter_key(DIMENSION_ORGANIZATION, organization_id=org_id)].add(is_complete=is_complete, is_fresh=is_fresh)
                counters[_counter_key(DIMENSION_MODEL_ORGANIZATION, model_id=model_id, organization_id=org_id)].add(
                    is_complete=is_complete,
                    is_fresh=is_fresh,
                )

    saved = 0
    for (dimension, model_id, organization_key), counter in counters.items():
        organization_id = organization_key or None
        defaults = {
            "model_id": model_id,
            "organization_id": organization_id,
            "total_count": counter.total_count,
            "complete_count": counter.complete_count,
            "fresh_count": counter.fresh_count,
            "healthy_count": counter.healthy_count,
            "completeness_score": _score(counter.complete_count, counter.total_count),
            "freshness_score": _score(counter.fresh_count, counter.total_count),
            "overall_score": _score(counter.healthy_count, counter.total_count),
            "metadata": {},
        }
        CmdbGovernanceHealthSnapshot.objects.update_or_create(
            snapshot_date=snapshot_date,
            dimension=dimension,
            model_key=model_id or "",
            organization_key=organization_key,
            defaults=defaults,
        )
        saved += 1
    return {"snapshots": saved}
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py::test_calculate_instance_health_and_aggregate_snapshots -q
```

Expected: PASS。

- [ ] **Step 5: 检查 diff**

Run:

```bash
cd server && git diff --check -- ../enterprise/server/apps/cmdb_enterprise/governance/services.py ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py
```

Expected: 无输出。

---

### Task 7: 实现端到端快照计算入口

**Files:**
- Modify: `enterprise/server/apps/cmdb_enterprise/governance/services.py`
- Test: `enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py`

- [ ] **Step 1: 写失败测试**

在 `test_governance_health_service.py` 增加，使用 monkeypatch 隔离图数据库：

```python
def test_calculate_governance_health_snapshot_loads_sources(monkeypatch):
    snapshot_date = date(2026, 6, 11)
    called = {}

    monkeypatch.setattr(
        services,
        "load_governed_model_configs",
        lambda: {"host": services.GovernanceModelConfig("host", ["owner"], {})},
    )
    monkeypatch.setattr(
        services,
        "load_instances_by_model",
        lambda configs: called.setdefault("configs", configs) or {"host": [{"_id": 1, "model_id": "host", "owner": "alice", "organization": [1]}]},
    )
    monkeypatch.setattr(
        services,
        "load_verified_field_times",
        lambda **kwargs: called.setdefault("verified_kwargs", kwargs) or {1: {}},
    )
    monkeypatch.setattr(
        services,
        "calculate_and_store_snapshots",
        lambda **kwargs: called.setdefault("store_kwargs", kwargs) or {"snapshots": 1},
    )

    result = services.calculate_governance_health_snapshot(snapshot_date=snapshot_date)

    assert result == {"snapshots": 1}
    assert "host" in called["configs"]
    assert called["verified_kwargs"]["inst_ids"] == [1]
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py::test_calculate_governance_health_snapshot_loads_sources -q
```

Expected: FAIL，错误包含 `AttributeError: module ... has no attribute 'calculate_governance_health_snapshot'`。

- [ ] **Step 3: 实现加载与入口函数**

修改 `enterprise/server/apps/cmdb_enterprise/governance/services.py`，追加：

```python
from apps.cmdb.constants.constants import INSTANCE
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.services.model import ModelManage


def load_governed_model_configs() -> dict[str, GovernanceModelConfig]:
    configs: dict[str, GovernanceModelConfig] = {}
    for model in ModelManage.search_model(include_hidden=True):
        model_id = model.get("model_id")
        if not model_id:
            continue
        attrs = ModelManage._normalize_attr_constraints(ModelManage.parse_attrs(model.get("attrs", "[]")))
        config = build_governance_model_config(model_id, attrs)
        if config.is_governed:
            configs[model_id] = config
    return configs


def load_instances_by_model(configs: dict[str, GovernanceModelConfig]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    with GraphClient() as graph:
        for model_id in configs:
            instances, _ = graph.query_entity(
                INSTANCE,
                [{"field": "model_id", "type": "str=", "value": model_id}],
            )
            result[model_id] = instances
    return result


def calculate_governance_health_snapshot(snapshot_date: date | None = None) -> dict:
    snapshot_date = snapshot_date or timezone.localdate()
    configs = load_governed_model_configs()
    instances_by_model = load_instances_by_model(configs)
    inst_ids = [
        int(instance["_id"])
        for instances in instances_by_model.values()
        for instance in instances
        if instance.get("_id") is not None
    ]
    verified_times = load_verified_field_times(
        inst_ids=inst_ids,
        configs=configs,
        snapshot_at=snapshot_cutoff(snapshot_date),
    )
    return calculate_and_store_snapshots(
        snapshot_date=snapshot_date,
        configs=configs,
        instances_by_model=instances_by_model,
        verified_times=verified_times,
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py::test_calculate_governance_health_snapshot_loads_sources -q
```

Expected: PASS。

- [ ] **Step 5: 检查 diff**

Run:

```bash
cd server && git diff --check -- ../enterprise/server/apps/cmdb_enterprise/governance/services.py ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py
```

Expected: 无输出。

---

### Task 8: 在社区采集链路实现自动采集实例级 ChangeRecord 写入

**Files:**
- Create: `server/apps/cmdb/collection/change_records.py`
- Modify: `server/apps/cmdb/collection/common.py`
- Test: `server/apps/cmdb/tests/test_collect_change_records.py`

- [ ] **Step 1: 写失败测试**

创建 `server/apps/cmdb/tests/test_collect_change_records.py`：

```python
import importlib
from pathlib import Path

import apps

ENTERPRISE_APPS_PATH = str(Path(__file__).resolve().parents[2])
if ENTERPRISE_APPS_PATH not in apps.__path__:
    apps.__path__.append(ENTERPRISE_APPS_PATH)

collect_logs = importlib.import_module("apps.cmdb.collection.change_records")


class FakeManagement:
    model_id = "host"
    old_map = {
        ("host-a",): {"_id": 1, "model_id": "host", "inst_name": "host-a", "status": "running"},
        ("host-b",): {"_id": 2, "model_id": "host", "inst_name": "host-b", "status": "running"},
    }


def test_build_collect_change_records_marks_changed_and_unchanged():
    result = {
        "add": {"success": [{"inst_info": {"_id": 3, "model_id": "host", "inst_name": "host-c"}}], "failed": []},
        "update": {
            "success": [
                {"inst_info": {"_id": 1, "model_id": "host", "inst_name": "host-a", "status": "stopped"}},
                {"inst_info": {"_id": 2, "model_id": "host", "inst_name": "host-b", "status": "running"}},
            ],
            "failed": [],
        },
        "delete": {"success": [{"_id": 4, "model_id": "host", "inst_name": "host-d"}], "failed": []},
    }

    records = collect_logs.build_collect_change_records(FakeManagement(), result)

    assert [record["message"] for record in records["create"]] == ["自动采集新增实例"]
    assert [record["message"] for record in records["update"]] == ["自动采集更新实例", "自动采集核实实例，字段无变化"]
    assert [record["message"] for record in records["delete"]] == ["自动采集删除实例"]
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd server && uv run pytest apps/cmdb/tests/test_collect_change_records.py::test_build_collect_change_records_marks_changed_and_unchanged -q
```

Expected: FAIL，错误包含 `ModuleNotFoundError: No module named 'apps.cmdb.collection.change_records'`。

- [ ] **Step 3: 实现社区版 change_records**

创建 `server/apps/cmdb/collection/change_records.py`：

```python
from apps.cmdb.constants.constants import INSTANCE, OPERATOR_INSTANCE
from apps.cmdb.models.change_record import (
    COLLECT_AUTOMATION_CHANGE,
    CREATE_INST,
    DELETE_INST,
    UPDATE_INST,
)
from apps.cmdb.utils.change_record import batch_create_change_record
SYSTEM_DIFF_IGNORED_FIELDS = {"_id", "model_id", "collect_time", "collect_task", "auto_collect"}


def _business_snapshot(data: dict) -> dict:
    return {
        key: value
        for key, value in (data or {}).items()
        if key not in SYSTEM_DIFF_IGNORED_FIELDS and not str(key).startswith("_")
    }


def _has_business_changes(before_data: dict, after_data: dict) -> bool:
    return _business_snapshot(before_data) != _business_snapshot(after_data)


def _old_instance_by_id(management) -> dict[int, dict]:
    result = {}
    for old in getattr(management, "old_map", {}).values():
        if old.get("_id") is not None:
            result[int(old["_id"])] = old
    return result


def build_collect_change_records(management, result: dict) -> dict[str, list[dict]]:
    old_by_id = _old_instance_by_id(management)
    create_records = []
    update_records = []
    delete_records = []

    for item in ((result.get("add") or {}).get("success") or []):
        inst_info = item.get("inst_info") or item
        create_records.append(
            {
                "inst_id": inst_info["_id"],
                "model_id": inst_info["model_id"],
                "after_data": inst_info,
                "model_object": OPERATOR_INSTANCE,
                "message": "自动采集新增实例",
            }
        )

    for item in ((result.get("update") or {}).get("success") or []):
        inst_info = item.get("inst_info") or item
        before_data = old_by_id.get(int(inst_info["_id"]), inst_info)
        message = "自动采集更新实例" if _has_business_changes(before_data, inst_info) else "自动采集核实实例，字段无变化"
        update_records.append(
            {
                "inst_id": inst_info["_id"],
                "model_id": inst_info["model_id"],
                "before_data": before_data,
                "after_data": inst_info,
                "model_object": OPERATOR_INSTANCE,
                "message": message,
            }
        )

    for item in ((result.get("delete") or {}).get("success") or []):
        inst_info = item.get("inst_info") or item
        delete_records.append(
            {
                "inst_id": inst_info["_id"],
                "model_id": inst_info["model_id"],
                "before_data": inst_info,
                "model_object": OPERATOR_INSTANCE,
                "message": "自动采集删除实例",
            }
        )

    return {"create": create_records, "update": update_records, "delete": delete_records}


def record_collect_instance_change_logs(management, result: dict) -> None:
    records = build_collect_change_records(management, result)
    if records["create"]:
        batch_create_change_record(
            INSTANCE,
            CREATE_INST,
            records["create"],
            operator="system",
            scenario=COLLECT_AUTOMATION_CHANGE,
        )
    if records["update"]:
        batch_create_change_record(
            INSTANCE,
            UPDATE_INST,
            records["update"],
            operator="system",
            scenario=COLLECT_AUTOMATION_CHANGE,
        )
    if records["delete"]:
        batch_create_change_record(
            INSTANCE,
            DELETE_INST,
            records["delete"],
            operator="system",
            scenario=COLLECT_AUTOMATION_CHANGE,
        )
```

- [ ] **Step 4: 接入采集写库后置处理**

修改 `server/apps/cmdb/collection/common.py`，让完整采集 `controller()` 和选择字段采集 `update()` 都调用统一后置处理：

```python
from apps.cmdb.collect.extensions import CollectEnterpriseExtension
from apps.cmdb.collection.change_records import write_collect_instance_change_records


def _after_instances_applied(self, result):
    write_collect_instance_change_records(self, result)
    get_collect_enterprise_extension().on_collect_instances_applied(management=self, result=result)
```

- [ ] **Step 5: 运行测试确认通过**

Run:

```bash
cd server && uv run pytest apps/cmdb/tests/test_collect_change_records.py apps/cmdb/tests/test_collect_management_hooks.py -q
```

Expected: PASS。

- [ ] **Step 6: 检查 diff**

Run:

```bash
cd server && git diff --check -- apps/cmdb/collection/change_records.py apps/cmdb/collection/common.py apps/cmdb/tests/test_collect_change_records.py apps/cmdb/tests/test_collect_management_hooks.py
```

Expected: 无输出。

---

### Task 9: 增加 Celery 任务与手动命令

**Files:**
- Create: `enterprise/server/apps/cmdb_enterprise/governance/tasks.py`
- Modify: `enterprise/server/apps/cmdb_enterprise/tasks/__init__.py`
- Modify: `enterprise/server/apps/cmdb_enterprise/config.py`
- Create: `enterprise/server/apps/cmdb_enterprise/management/__init__.py`
- Create: `enterprise/server/apps/cmdb_enterprise/management/commands/__init__.py`
- Create: `enterprise/server/apps/cmdb_enterprise/management/commands/calculate_cmdb_governance_health.py`
- Test: `enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py`

- [ ] **Step 1: 写失败测试**

在 `test_governance_health_service.py` 增加命令测试：

```python
from io import StringIO
from django.core.management import call_command


def test_calculate_cmdb_governance_health_command(monkeypatch):
    calls = []
    monkeypatch.setattr(
        services,
        "calculate_governance_health_snapshot",
        lambda snapshot_date=None: calls.append(snapshot_date) or {"snapshots": 3},
    )
    out = StringIO()

    call_command("calculate_cmdb_governance_health", "--date", "2026-06-11", stdout=out)

    assert calls == [date(2026, 6, 11)]
    assert "snapshots=3" in out.getvalue()
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py::test_calculate_cmdb_governance_health_command -q
```

Expected: FAIL，错误包含 `Unknown command: 'calculate_cmdb_governance_health'`。

- [ ] **Step 3: 创建 Celery 任务**

创建 `enterprise/server/apps/cmdb_enterprise/governance/tasks.py`：

```python
from celery import shared_task

from apps.cmdb_enterprise.governance.services import calculate_governance_health_snapshot


@shared_task
def calculate_cmdb_governance_health_snapshot_task():
    return calculate_governance_health_snapshot()
```

修改 `enterprise/server/apps/cmdb_enterprise/tasks/__init__.py`：

```python
"""cmdb_enterprise Celery tasks（Celery autodiscover 入口）。"""
from apps.cmdb_enterprise.instance_ops.tasks import cleanup_attachment_files  # noqa: F401
from apps.cmdb_enterprise.governance.tasks import calculate_cmdb_governance_health_snapshot_task  # noqa: F401
```

修改 `enterprise/server/apps/cmdb_enterprise/config.py`：

```python
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "cleanup_attachment_files": {
        "task": "apps.cmdb_enterprise.instance_ops.tasks.cleanup_attachment_files",
        "schedule": crontab(hour="3", minute="30"),
    },
    "cmdb-governance-health-snapshot": {
        "task": "apps.cmdb_enterprise.governance.tasks.calculate_cmdb_governance_health_snapshot_task",
        "schedule": crontab(hour="3", minute="30"),
    },
}
```

- [ ] **Step 4: 创建 management command**

创建 `enterprise/server/apps/cmdb_enterprise/management/__init__.py`：

```python
"""cmdb_enterprise management commands."""
```

创建 `enterprise/server/apps/cmdb_enterprise/management/commands/__init__.py`：

```python
"""cmdb_enterprise command package."""
```

创建 `enterprise/server/apps/cmdb_enterprise/management/commands/calculate_cmdb_governance_health.py`：

```python
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from apps.cmdb_enterprise.governance.services import calculate_governance_health_snapshot


class Command(BaseCommand):
    help = "生成 CMDB 数据治理健康度快照"

    def add_arguments(self, parser):
        parser.add_argument("--date", dest="snapshot_date", default="", help="快照日期，格式 YYYY-MM-DD")

    def handle(self, *args, **options):
        raw_date = options.get("snapshot_date") or ""
        snapshot_date = None
        if raw_date:
            try:
                snapshot_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
            except ValueError as exc:
                raise CommandError("--date 必须使用 YYYY-MM-DD 格式") from exc
        result = calculate_governance_health_snapshot(snapshot_date=snapshot_date)
        self.stdout.write(self.style.SUCCESS(f"CMDB governance health calculated: snapshots={result.get('snapshots', 0)}"))
```

- [ ] **Step 5: 运行测试确认通过**

Run:

```bash
cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py::test_calculate_cmdb_governance_health_command -q
```

Expected: PASS。

- [ ] **Step 6: 检查 diff**

Run:

```bash
cd server && git diff --check -- ../enterprise/server/apps/cmdb_enterprise/governance/tasks.py ../enterprise/server/apps/cmdb_enterprise/tasks/__init__.py ../enterprise/server/apps/cmdb_enterprise/config.py ../enterprise/server/apps/cmdb_enterprise/management
```

Expected: 无输出。

---

### Task 10: 补齐边界测试与回归验证

**Files:**
- Modify: `enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py`
- Modify: `server/apps/cmdb/tests/test_collect_change_records.py`

- [ ] **Step 1: 增加新鲜度过期与无核实记录测试**

在 `test_governance_health_service.py` 增加：

```python
def test_is_instance_fresh_requires_verified_time_within_window():
    snapshot_at = timezone.now()
    config = services.GovernanceModelConfig("host", [], {"status": 7, "serial": 90})

    assert services.is_instance_fresh(
        {"_id": 1},
        config,
        {"status": snapshot_at - timedelta(days=8), "serial": snapshot_at},
        snapshot_at,
    ) is False
    assert services.is_instance_fresh(
        {"_id": 1},
        config,
        {"status": snapshot_at - timedelta(days=6)},
        snapshot_at,
    ) is False
    assert services.is_instance_fresh(
        {"_id": 1},
        config,
        {"status": snapshot_at - timedelta(days=6), "serial": snapshot_at - timedelta(days=80)},
        snapshot_at,
    ) is True
```

- [ ] **Step 2: 增加重复执行 upsert 测试**

在 `test_governance_health_service.py` 增加：

```python
@pytest.mark.django_db
def test_snapshot_generation_upserts_same_day_dimension():
    snapshot_date = date(2026, 6, 11)
    config = services.GovernanceModelConfig("host", ["owner"], {})
    instances_by_model = {"host": [{"_id": 1, "model_id": "host", "owner": "alice", "organization": [10]}]}

    services.calculate_and_store_snapshots(
        snapshot_date=snapshot_date,
        configs={"host": config},
        instances_by_model=instances_by_model,
        verified_times={},
    )
    services.calculate_and_store_snapshots(
        snapshot_date=snapshot_date,
        configs={"host": config},
        instances_by_model=instances_by_model,
        verified_times={},
    )

    assert CmdbGovernanceHealthSnapshot.objects.filter(snapshot_date=snapshot_date, dimension="global").count() == 1
```

- [ ] **Step 3: 增加采集失败行不写日志测试**

在 `test_collect_change_records.py` 增加：

```python
def test_build_collect_change_records_ignores_failed_rows():
    result = {
        "add": {"success": [], "failed": [{"instance_info": {"inst_name": "bad"}, "error": "boom"}]},
        "update": {"success": [], "failed": [{"instance_info": {"_id": 1, "model_id": "host"}, "error": "boom"}]},
        "delete": {"success": [], "failed": [{"_id": 2, "model_id": "host", "error": "boom"}]},
    }

    records = collect_logs.build_collect_change_records(FakeManagement(), result)

    assert records == {"create": [], "update": [], "delete": []}
```

- [ ] **Step 4: 运行聚焦测试**

Run:

```bash
cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests/test_governance_health_service.py apps/cmdb/tests/test_collect_change_records.py apps/cmdb/tests/test_enterprise_extensions.py -q
```

Expected: PASS。

- [ ] **Step 5: 运行受影响模块测试**

Run:

```bash
cd server && uv run pytest ../enterprise/server/apps/cmdb_enterprise/tests -q
```

Expected: PASS。

- [ ] **Step 6: 运行门禁**

Run:

```bash
cd server && make test
```

Expected: `pytest` 退出码为 0。

- [ ] **Step 7: 最终检查**

Run:

```bash
cd /Users/hong/Desktop/weops相关/new-weops-x/bk-lite && git status --short && git diff --check
```

Expected:

- `git status --short` 显示本需求相关文件变更。
- `git diff --check` 无输出。

---

## Self-Review

**Spec coverage:** 本计划覆盖了商业版快照表、四类聚合维度、完整性计算、新鲜度基于操作日志计算、自动采集实例级日志补齐、每日 Celery 任务、手动 management command、测试和验证命令。自定义上报按 spec 排除在本期实现外，只保留后续接入说明。

**Placeholder scan:** 未使用 `TBD`、`TODO`、`implement later` 或空泛“补充测试”式描述。每个代码步骤都给出明确文件、函数和命令。

**Type consistency:** 计划中统一使用 `GovernanceModelConfig`、`CmdbGovernanceHealthSnapshot`、`calculate_governance_health_snapshot`、`calculate_and_store_snapshots`、`build_collect_change_records`、`record_collect_instance_change_logs`，后续任务引用与定义一致。
