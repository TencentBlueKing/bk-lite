# 告警升级（Escalation）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在告警分派规则内新增"升级链"——告警在某层等待时长内未被认领时，由一个独立的时间驱动扫描任务自动切换/扩展在岗集合并通知，复用现有通知发送出口；前端在分派规则表单内提供升级链配置区块。

**Architecture:** 升级链作为 JSON 块存进 `AlertAssignment.config["escalation"]`。每条告警起一个**独立的** `AlertEscalationTask`（与 `AlertReminderTask` 解耦，避免"无提醒频率即无升级"的耦合），由新 beat 任务 `check_and_send_escalations` 每分钟按 `layer_started_at + wait_minutes` 推进层级。升级与级内提醒是两个独立时钟，但共享同一发送出口（`sync_notify`）：提醒发送时改读升级任务的"当前在岗集合 + 当前层渠道"。认领/解决/关闭终止升级，改派重置到第 0 层。Layer 0 即初始责任人。

**Tech Stack:** Django 4.2 + DRF + Celery beat（后端，`uv run pytest`），Next.js 16 + Ant Design + react-intl（前端）。

---

## ⚠️ 与 spec §4 的一处偏离（实现前先知会）

Spec `spec/requirements/告警中心/20260531.告警中心-新增告警升级策略.md` §4 写的是"扩展 `AlertReminderTask` 记录层级锚点"。实现中发现：`ReminderService.create_reminder_task` 在该告警级别**没有有效提醒频率（`interval_minutes<=0`）时直接返回 None、不建任何 `AlertReminderTask` 行**（见 `reminder_service.py:114`）。若把升级状态挂在该模型上，则"配了升级链但没配级内提醒频率"的规则将永远不会升级——这违背升级与提醒解耦的初衷。

**因此本计划改用独立模型 `AlertEscalationTask`。** 外部行为与 spec 完全一致，仅内部存储从"扩展旧表"变为"新建旁表"。Task 0 会同步把 spec §4 这句话改掉。

---

## File Structure

**后端（server/apps/alerts/）**
- Create: `models/alert_operator.py` 末尾追加 `AlertEscalationTask`（与现有 `AlertReminderTask` 同文件，分派/提醒/升级三表同域）
- Create: `service/escalation_service.py` — `EscalationService`：配置解析、在岗集合计算、建/停/重置升级任务、扫描推进、提醒在岗集合改写入口、清理
- Modify: `service/alter_operator.py` — `_assign_alert`（建升级任务 + 把第 0 层人并入 operator）、`_acknowledge_alert`/`_close_alert`/`_resolve_alert`（停升级）、`_reassign_alert`（重置升级）
- Modify: `service/reminder_service.py` — `_send_reminder_notification` 改读升级在岗集合/渠道
- Modify: `serializers/assignment_shield.py` — `AlertAssignmentModelSerializer.validate_config` 校验升级块
- Modify: `tasks/tasks.py` — 新增 `check_and_send_escalations` celery 任务；`cleanup_reminder_tasks` 顺带清升级
- Modify: `config.py` — beat 注册 `check_and_send_escalations`
- Create: `tests/test_escalation_service.py`、`tests/test_escalation_assignment_flow.py`、`tests/test_assignment_config_validation.py`
- Migration: 由 `makemigrations` 生成

**前端（web/src/app/alarm/）**
- Modify: `(pages)/settings/alertAssign/components/operateModal.tsx` — 升级链配置区块 + `getParams` 写 `config.escalation` + 编辑回填
- Create: `(pages)/settings/alertAssign/components/escalationChain.tsx` — 升级链子组件（Form.List）
- Modify: `locales/en.json`、`locales/zh.json`（i18n 键）

**升级链 JSON 结构（`AlertAssignment.config["escalation"]`）**
```json
{
  "enabled": true,
  "mode": "append",
  "layers": [
    {"personnel": ["u1"], "wait_minutes": 10, "notify_channels": []},
    {"personnel": ["u2", "u3"], "wait_minutes": 20, "notify_channels": [{"id": 5, "channel_type": "wechat", "name": "企微"}]}
  ]
}
```
- `mode`: `"append"`（累加）| `"replace"`（替换）
- `layers[0]` = 初始责任人；`layers[i].wait_minutes` = 在第 i 层等多久未认领则升到 i+1 层
- `notify_channels` 为空数组时该层沿用 `assignment.notify_channels`

---

## Task 0: 同步 spec §4 文字（消除偏离）

**Files:**
- Modify: `spec/requirements/告警中心/20260531.告警中心-新增告警升级策略.md`

- [ ] **Step 1: 改写 §4 最后一条**

把 §4 中以 "**`AlertReminderTask` 扩展的时间锚点与状态。**" 开头那一整条 bullet 替换为：

```markdown
- **独立的升级任务表 `AlertEscalationTask`。** 每条告警在分派且命中规则配了升级链时，创建一条与 `AlertReminderTask` 解耦的升级任务，记录：分派策略、升级模式快照、升级链层级快照、当前层级 index、本层开始时间（升级 due 计算锚点）、是否激活。解耦的原因：提醒任务在该级别无有效提醒频率时不会创建，升级不应被此耦合。级内提醒计数 `reminder_count` 在跨层时归零、`max_count` 预算按当前在岗集合重置。
```

- [ ] **Step 2: Commit**

```bash
git add "spec/requirements/告警中心/20260531.告警中心-新增告警升级策略.md"
git commit -m "docs(alerts): escalation spec §4 改用独立 AlertEscalationTask 表"
```

---

## Task 1: 模型 `AlertEscalationTask` + 迁移

**Files:**
- Modify: `server/apps/alerts/models/alert_operator.py`（在 `AlertReminderTask` 之后、`AlarmStrategy` 之前插入）
- Test: `server/apps/alerts/tests/test_escalation_service.py`

- [ ] **Step 1: Write the failing test**

新建 `server/apps/alerts/tests/test_escalation_service.py`：

```python
"""告警升级服务覆盖测试。

对照 spec/requirements/告警中心/20260531.告警中心-新增告警升级策略.md
"""
import pytest
from django.utils import timezone

from apps.alerts.models.alert_operator import AlertAssignment, AlertEscalationTask
from apps.alerts.models.models import Alert


def _make_alert(alert_id="A1", level="0", status="pending", operator=None):
    return Alert.objects.create(
        alert_id=alert_id, level=level, title="t", content="c",
        fingerprint="fp-" + alert_id, status=status, operator=operator or [],
    )


def _chain(mode="append", layers=None):
    return {"enabled": True, "mode": mode, "layers": layers or [
        {"personnel": ["u1"], "wait_minutes": 10, "notify_channels": []},
        {"personnel": ["u2"], "wait_minutes": 20, "notify_channels": []},
    ]}


def _make_assignment(name="分派", escalation=None, channels=None, personnel=None):
    return AlertAssignment.objects.create(
        name=name, match_type="all",
        personnel=personnel or ["u1"],
        notify_channels=channels or [{"id": 1, "channel_type": "email", "name": "邮件"}],
        config={"escalation": escalation} if escalation else {},
    )


@pytest.mark.django_db
def test_escalation_task_fields_persist():
    alert = _make_alert()
    assignment = _make_assignment(escalation=_chain())
    task = AlertEscalationTask.objects.create(
        alert=alert, assignment=assignment, is_active=True,
        mode="append", layers=_chain()["layers"],
        current_layer_index=0, layer_started_at=timezone.now(),
    )
    task.refresh_from_db()
    assert task.current_layer_index == 0
    assert task.mode == "append"
    assert task.layers[1]["wait_minutes"] == 20
    assert task.is_active is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest apps/alerts/tests/test_escalation_service.py::test_escalation_task_fields_persist -v`
Expected: FAIL — `ImportError: cannot import name 'AlertEscalationTask'`

- [ ] **Step 3: Add the model**

在 `server/apps/alerts/models/alert_operator.py` 的 `AlertReminderTask` 类之后插入：

```python
class AlertEscalationTask(models.Model):
    """
    告警升级任务 - 时间驱动，独立于提醒任务
    """

    alert = models.OneToOneField(
        "Alert", on_delete=models.CASCADE, help_text="关联的告警", primary_key=True
    )
    assignment = models.ForeignKey(
        AlertAssignment, on_delete=models.CASCADE, help_text="分派策略"
    )

    is_active = models.BooleanField(default=True, help_text="是否激活")
    mode = models.CharField(max_length=16, help_text="升级模式 append/replace")
    layers = JSONField(default=list, help_text="升级链层级快照")
    current_layer_index = models.IntegerField(default=0, help_text="当前层级索引")
    layer_started_at = models.DateTimeField(help_text="本层开始时间")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "alerts_escalation_task"
        indexes = [
            models.Index(fields=["is_active", "layer_started_at"]),
        ]

    def __str__(self):
        return f"EscalationTask for Alert {self.alert.alert_id}"
```

- [ ] **Step 4: Generate migration**

Run: `cd server && uv run python manage.py makemigrations alerts`
Expected: 新建一个迁移文件，新增 `AlertEscalationTask`。

- [ ] **Step 5: Run test to verify it passes**

Run: `cd server && uv run pytest apps/alerts/tests/test_escalation_service.py::test_escalation_task_fields_persist -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add server/apps/alerts/models/alert_operator.py server/apps/alerts/migrations/ server/apps/alerts/tests/test_escalation_service.py
git commit -m "feat(alerts): add AlertEscalationTask model"
```

---

## Task 2: 纯函数 `parse_escalation_config` + `compute_roster`

**Files:**
- Create: `server/apps/alerts/service/escalation_service.py`
- Test: `server/apps/alerts/tests/test_escalation_service.py`

- [ ] **Step 1: Write the failing tests**

追加到 `test_escalation_service.py`：

```python
from apps.alerts.service.escalation_service import EscalationService as ES


def test_parse_escalation_config_disabled():
    assert ES.parse_escalation_config({}) is None
    assert ES.parse_escalation_config({"escalation": {"enabled": False, "mode": "append", "layers": [{"personnel": ["u1"], "wait_minutes": 5}]}}) is None


def test_parse_escalation_config_invalid_mode():
    cfg = {"escalation": {"enabled": True, "mode": "bogus", "layers": [{"personnel": ["u1"], "wait_minutes": 5}]}}
    assert ES.parse_escalation_config(cfg) is None


def test_parse_escalation_config_empty_layers():
    cfg = {"escalation": {"enabled": True, "mode": "append", "layers": []}}
    assert ES.parse_escalation_config(cfg) is None


def test_parse_escalation_config_layer_missing_personnel():
    cfg = {"escalation": {"enabled": True, "mode": "append", "layers": [{"personnel": [], "wait_minutes": 5}]}}
    assert ES.parse_escalation_config(cfg) is None


def test_parse_escalation_config_layer_bad_wait():
    cfg = {"escalation": {"enabled": True, "mode": "append", "layers": [{"personnel": ["u1"], "wait_minutes": 0}]}}
    assert ES.parse_escalation_config(cfg) is None


def test_parse_escalation_config_valid():
    cfg = {"escalation": {"enabled": True, "mode": "replace", "layers": [
        {"personnel": ["u1"], "wait_minutes": 10, "notify_channels": []},
        {"personnel": ["u2"], "wait_minutes": 20},
    ]}}
    result = ES.parse_escalation_config(cfg)
    assert result["mode"] == "replace"
    assert len(result["layers"]) == 2
    assert result["layers"][1]["notify_channels"] == []  # 默认补空


def test_compute_roster_replace():
    layers = [{"personnel": ["u1"]}, {"personnel": ["u2", "u3"]}]
    assert ES.compute_roster(layers, 0, "replace") == ["u1"]
    assert ES.compute_roster(layers, 1, "replace") == ["u2", "u3"]


def test_compute_roster_append_dedups_and_orders():
    layers = [{"personnel": ["u1", "u2"]}, {"personnel": ["u2", "u3"]}]
    assert ES.compute_roster(layers, 0, "append") == ["u1", "u2"]
    assert ES.compute_roster(layers, 1, "append") == ["u1", "u2", "u3"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && uv run pytest apps/alerts/tests/test_escalation_service.py -k "parse_escalation or compute_roster" -v`
Expected: FAIL — `ModuleNotFoundError: apps.alerts.service.escalation_service`

- [ ] **Step 3: Create the service with pure helpers**

新建 `server/apps/alerts/service/escalation_service.py`：

```python
# -- coding: utf-8 --
import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from django.db import connection, transaction
from django.utils import timezone

from apps.alerts.constants.constants import AlertStatus, SessionStatus
from apps.alerts.models.alert_operator import (
    AlertAssignment,
    AlertEscalationTask,
    AlertReminderTask,
)
from apps.alerts.models.models import Alert

logger = logging.getLogger(__name__)

VALID_MODES = ("append", "replace")


class EscalationService:
    EXPIRED_DAYS = 30

    @staticmethod
    def parse_escalation_config(config: Optional[dict]) -> Optional[dict]:
        """解析并规范化升级链配置。无效或未启用返回 None。"""
        if not config:
            return None
        block = config.get("escalation") if isinstance(config, dict) else None
        if not block or not block.get("enabled"):
            return None
        mode = block.get("mode")
        if mode not in VALID_MODES:
            logger.warning("升级链模式非法: mode=%s", mode)
            return None
        raw_layers = block.get("layers") or []
        if not isinstance(raw_layers, list) or len(raw_layers) == 0:
            return None
        layers: List[dict] = []
        for idx, layer in enumerate(raw_layers):
            personnel = layer.get("personnel") or []
            if not isinstance(personnel, list) or len(personnel) == 0:
                logger.warning("升级链第 %s 层缺少处理人", idx)
                return None
            try:
                wait_minutes = int(layer.get("wait_minutes", 0) or 0)
            except (TypeError, ValueError):
                return None
            if wait_minutes <= 0:
                logger.warning("升级链第 %s 层等待时长非法: %s", idx, layer.get("wait_minutes"))
                return None
            layers.append({
                "personnel": list(dict.fromkeys(personnel)),
                "wait_minutes": wait_minutes,
                "notify_channels": layer.get("notify_channels") or [],
            })
        return {"mode": mode, "layers": layers}

    @staticmethod
    def compute_roster(layers: List[dict], current_index: int, mode: str) -> List[str]:
        """当前在岗集合（去重保序）。replace=本层；append=0..current 并集。"""
        if mode == "replace":
            source = layers[current_index].get("personnel", [])
        else:
            source = []
            for layer in layers[: current_index + 1]:
                source.extend(layer.get("personnel", []))
        return list(dict.fromkeys(source))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && uv run pytest apps/alerts/tests/test_escalation_service.py -k "parse_escalation or compute_roster" -v`
Expected: PASS（8 个用例）

- [ ] **Step 5: Commit**

```bash
git add server/apps/alerts/service/escalation_service.py server/apps/alerts/tests/test_escalation_service.py
git commit -m "feat(alerts): escalation config parsing and roster computation"
```

---

## Task 3: `create_escalation_task` / `stop_escalation_task` / `reset_escalation_task`

**Files:**
- Modify: `server/apps/alerts/service/escalation_service.py`
- Test: `server/apps/alerts/tests/test_escalation_service.py`

- [ ] **Step 1: Write the failing tests**

追加到 `test_escalation_service.py`：

```python
@pytest.mark.django_db
def test_create_escalation_task_none_when_disabled():
    alert = _make_alert()
    assignment = _make_assignment(escalation=None)
    assert ES.create_escalation_task(alert, assignment) is None


@pytest.mark.django_db
def test_create_escalation_task_creates_at_layer_zero():
    alert = _make_alert(operator=["existing"])
    assignment = _make_assignment(escalation=_chain(mode="append"))
    task = ES.create_escalation_task(alert, assignment)
    assert task is not None
    assert task.current_layer_index == 0
    assert task.mode == "append"
    assert task.is_active is True
    # 第 0 层处理人并入 operator（认领资格累加），保留已有
    alert.refresh_from_db()
    assert "existing" in alert.operator
    assert "u1" in alert.operator


@pytest.mark.django_db
def test_create_escalation_task_idempotent_reactivates():
    alert = _make_alert()
    assignment = _make_assignment(escalation=_chain())
    first = ES.create_escalation_task(alert, assignment)
    first.is_active = False
    first.current_layer_index = 1
    first.save()
    second = ES.create_escalation_task(alert, assignment)
    assert second.alert_id == first.alert_id
    assert second.is_active is True
    assert second.current_layer_index == 0  # 复用即重置


@pytest.mark.django_db
def test_stop_escalation_task():
    alert = _make_alert()
    assignment = _make_assignment(escalation=_chain())
    ES.create_escalation_task(alert, assignment)
    assert ES.stop_escalation_task(alert) is True
    assert AlertEscalationTask.objects.get(alert=alert).is_active is False


@pytest.mark.django_db
def test_reset_escalation_task_back_to_layer_zero():
    alert = _make_alert()
    assignment = _make_assignment(escalation=_chain())
    task = ES.create_escalation_task(alert, assignment)
    task.current_layer_index = 1
    task.is_active = False
    task.save()
    reset = ES.reset_escalation_task(alert, assignment)
    assert reset.current_layer_index == 0
    assert reset.is_active is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && uv run pytest apps/alerts/tests/test_escalation_service.py -k "create_escalation or stop_escalation or reset_escalation" -v`
Expected: FAIL — `AttributeError: type object 'EscalationService' has no attribute 'create_escalation_task'`

- [ ] **Step 3: Implement lifecycle methods**

在 `EscalationService` 内追加（接 `compute_roster` 之后）：

```python
    @classmethod
    def _union_into_operator(cls, alert: Alert, personnel: List[str]) -> None:
        """把新层处理人并入 operator（认领资格累加，不移除）。"""
        merged = list(dict.fromkeys(list(alert.operator or []) + list(personnel)))
        if merged != (alert.operator or []):
            alert.operator = merged
            alert.save(update_fields=["operator", "updated_at"])

    @classmethod
    def create_escalation_task(
        cls, alert: Alert, assignment: AlertAssignment
    ) -> Optional[AlertEscalationTask]:
        """分派时创建升级任务（命中规则配了升级链才创建）。"""
        normalized = cls.parse_escalation_config(assignment.config)
        if not normalized:
            return None
        now = timezone.now()
        task, _ = AlertEscalationTask.objects.update_or_create(
            alert=alert,
            defaults={
                "assignment": assignment,
                "is_active": True,
                "mode": normalized["mode"],
                "layers": normalized["layers"],
                "current_layer_index": 0,
                "layer_started_at": now,
            },
        )
        cls._union_into_operator(alert, normalized["layers"][0]["personnel"])
        logger.info("创建升级任务: alert_id=%s, mode=%s, layers=%s",
                    alert.alert_id, normalized["mode"], len(normalized["layers"]))
        return task

    @classmethod
    def stop_escalation_task(cls, alert: Alert) -> bool:
        """认领/解决/关闭后停止升级。"""
        updated = AlertEscalationTask.objects.filter(
            alert=alert, is_active=True
        ).update(is_active=False, updated_at=timezone.now())
        return updated > 0

    @classmethod
    def reset_escalation_task(
        cls, alert: Alert, assignment: Optional[AlertAssignment]
    ) -> Optional[AlertEscalationTask]:
        """改派后升级计时重置到第 0 层。assignment 为空时沿用既有任务的策略。"""
        if assignment is None:
            existing = AlertEscalationTask.objects.filter(alert=alert).select_related("assignment").first()
            if not existing:
                return None
            assignment = existing.assignment
        return cls.create_escalation_task(alert, assignment)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && uv run pytest apps/alerts/tests/test_escalation_service.py -k "create_escalation or stop_escalation or reset_escalation" -v`
Expected: PASS（5 个用例）

- [ ] **Step 5: Commit**

```bash
git add server/apps/alerts/service/escalation_service.py server/apps/alerts/tests/test_escalation_service.py
git commit -m "feat(alerts): escalation task create/stop/reset lifecycle"
```

---

## Task 4: 扫描推进 `check_and_process_escalations` + `_advance_layer` + 通知

**Files:**
- Modify: `server/apps/alerts/service/escalation_service.py`
- Test: `server/apps/alerts/tests/test_escalation_service.py`

- [ ] **Step 1: Write the failing tests**

追加到 `test_escalation_service.py`（顶部已 import `timedelta`? 若无则补 `from datetime import timedelta`）：

```python
from datetime import timedelta
from unittest import mock


def _due_task(alert, assignment, index=0, minutes_ago=15):
    task = ES.create_escalation_task(alert, assignment)
    task.current_layer_index = index
    task.layer_started_at = timezone.now() - timedelta(minutes=minutes_ago)
    task.save()
    return task


@pytest.mark.django_db
@mock.patch("apps.alerts.service.escalation_service.EscalationService._send_escalation_notification")
def test_scan_advances_layer_when_deadline_passed(mock_send):
    alert = _make_alert(status="pending")
    assignment = _make_assignment(escalation=_chain(mode="append"))  # layer0 wait 10m
    _due_task(alert, assignment, index=0, minutes_ago=15)
    result = ES.check_and_process_escalations()
    task = AlertEscalationTask.objects.get(alert=alert)
    assert task.current_layer_index == 1
    assert result["escalated"] == 1
    # 累加模式：u1+u2 并入 operator 且通知 u2 所在新在岗集合
    alert.refresh_from_db()
    assert {"u1", "u2"}.issubset(set(alert.operator))
    mock_send.assert_called_once()


@pytest.mark.django_db
@mock.patch("apps.alerts.service.escalation_service.EscalationService._send_escalation_notification")
def test_scan_not_due_does_nothing(mock_send):
    alert = _make_alert(status="pending")
    assignment = _make_assignment(escalation=_chain())
    _due_task(alert, assignment, index=0, minutes_ago=3)  # < 10m
    ES.check_and_process_escalations()
    assert AlertEscalationTask.objects.get(alert=alert).current_layer_index == 0
    mock_send.assert_not_called()


@pytest.mark.django_db
@mock.patch("apps.alerts.service.escalation_service.EscalationService._send_escalation_notification")
def test_scan_last_layer_deactivates_no_more_escalation(mock_send):
    alert = _make_alert(status="pending")
    assignment = _make_assignment(escalation=_chain())  # 2 层, 末层 index=1 wait 20m
    _due_task(alert, assignment, index=1, minutes_ago=25)
    ES.check_and_process_escalations()
    task = AlertEscalationTask.objects.get(alert=alert)
    assert task.current_layer_index == 1
    assert task.is_active is False
    mock_send.assert_not_called()


@pytest.mark.django_db
@mock.patch("apps.alerts.service.escalation_service.EscalationService._send_escalation_notification")
def test_scan_deactivates_when_alert_not_pending(mock_send):
    alert = _make_alert(status="processing")
    assignment = _make_assignment(escalation=_chain())
    _due_task(alert, assignment, index=0, minutes_ago=15)
    ES.check_and_process_escalations()
    task = AlertEscalationTask.objects.get(alert=alert)
    assert task.is_active is False
    assert task.current_layer_index == 0
    mock_send.assert_not_called()


@pytest.mark.django_db
@mock.patch("apps.alerts.service.escalation_service.EscalationService._send_escalation_notification")
def test_advance_resets_reminder_counter(mock_send):
    alert = _make_alert(status="pending")
    assignment = _make_assignment(escalation=_chain())
    AlertReminderTask.objects.create(
        alert=alert, assignment=assignment, is_active=False,
        reminder_count=9, current_frequency_minutes=5, current_max_reminders=10,
        next_reminder_time=timezone.now(),
    )
    _due_task(alert, assignment, index=0, minutes_ago=15)
    ES.check_and_process_escalations()
    reminder = AlertReminderTask.objects.get(alert=alert)
    assert reminder.reminder_count == 0
    assert reminder.is_active is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && uv run pytest apps/alerts/tests/test_escalation_service.py -k "scan or advance_resets" -v`
Expected: FAIL — `AttributeError: ... has no attribute 'check_and_process_escalations'`

- [ ] **Step 3: Implement scan, advance, notify, reminder reset**

在 `EscalationService` 内追加：

```python
    @classmethod
    def _reset_reminder_for_new_roster(cls, alert: Alert) -> None:
        """跨层后级内提醒计数归零、预算重置、重新激活（若存在提醒任务）。"""
        reminder = AlertReminderTask.objects.filter(alert=alert).first()
        if not reminder:
            return
        now = timezone.now()
        reminder.reminder_count = 0
        reminder.is_active = True
        reminder.last_reminder_time = None
        reminder.next_reminder_time = now + timedelta(
            minutes=reminder.current_frequency_minutes
        )
        reminder.save(update_fields=[
            "reminder_count", "is_active", "last_reminder_time",
            "next_reminder_time", "updated_at",
        ])

    @classmethod
    def _send_escalation_notification(
        cls, alert: Alert, assignment: AlertAssignment,
        roster: List[str], layer_channels: List[dict],
    ) -> bool:
        """升级通知：复用与提醒一致的发送出口 sync_notify。"""
        from apps.alerts.common.notify.base import NotifyParamsFormat

        if alert.is_session_alert and alert.session_status != SessionStatus.CONFIRMED:
            logger.info("升级跳过会话观察期告警: alert_id=%s", alert.alert_id)
            return False
        if not roster:
            return False
        channels = layer_channels or assignment.notify_channels or []
        if not channels:
            logger.warning("升级通知无可用渠道: alert_id=%s", alert.alert_id)
            return False

        param_format = NotifyParamsFormat(username_list=roster, alerts=[alert])
        title = param_format.format_title()
        content = param_format.format_content()
        channel_params = [{
            "username_list": roster,
            "channel_type": ch["channel_type"],
            "channel_id": ch["id"],
            "title": title,
            "content": content,
            "object_id": alert.alert_id,
            "notify_action_object": "alert",
        } for ch in channels]

        from apps.alerts.tasks import sync_notify

        def _enqueue():
            sync_notify.delay(channel_params)

        if transaction.get_connection().in_atomic_block:
            transaction.on_commit(_enqueue)
        else:
            _enqueue()
        return True

    @classmethod
    def _advance_layer(cls, task: AlertEscalationTask) -> bool:
        """推进到下一层并通知；返回是否真正升级了一层。"""
        alert = task.alert
        next_index = task.current_layer_index + 1
        now = timezone.now()
        task.current_layer_index = next_index
        task.layer_started_at = now
        task.save(update_fields=["current_layer_index", "layer_started_at", "updated_at"])

        roster = cls.compute_roster(task.layers, next_index, task.mode)
        cls._union_into_operator(alert, task.layers[next_index]["personnel"])
        cls._reset_reminder_for_new_roster(alert)
        cls._send_escalation_notification(
            alert, task.assignment, roster, task.layers[next_index].get("notify_channels") or []
        )
        logger.info("告警升级到第 %s 层: alert_id=%s, roster=%s",
                    next_index, alert.alert_id, roster)
        return True

    @classmethod
    def check_and_process_escalations(cls) -> Dict[str, Any]:
        """每分钟扫描：到本层等待时长且仍待响应则升级到下一层。"""
        processed = 0
        escalated = 0
        try:
            ids = list(
                AlertEscalationTask.objects.filter(is_active=True).values_list(
                    "alert_id", flat=True
                )
            )
            select_for_update_kwargs = {}
            if connection.features.has_select_for_update_skip_locked:
                select_for_update_kwargs["skip_locked"] = True

            for alert_id in ids:
                try:
                    with transaction.atomic():
                        task = (
                            AlertEscalationTask.objects.select_for_update(
                                **select_for_update_kwargs
                            )
                            .select_related("alert", "assignment")
                            .filter(alert_id=alert_id, is_active=True)
                            .first()
                        )
                        if not task:
                            continue
                        processed += 1

                        if task.alert.status != AlertStatus.PENDING:
                            task.is_active = False
                            task.save(update_fields=["is_active", "updated_at"])
                            continue

                        deadline = task.layer_started_at + timedelta(
                            minutes=task.layers[task.current_layer_index]["wait_minutes"]
                        )
                        if timezone.now() < deadline:
                            continue

                        is_last = task.current_layer_index >= len(task.layers) - 1
                        if is_last:
                            task.is_active = False
                            task.save(update_fields=["is_active", "updated_at"])
                            logger.info("告警已达最后一层，不再升级: alert_id=%s", task.alert.alert_id)
                            continue

                        if cls._advance_layer(task):
                            escalated += 1
                except Exception as e:
                    logger.error("处理升级任务失败: alert_id=%s, error=%s", alert_id, str(e))
        except Exception as e:
            logger.error("检查升级任务失败: %s", str(e))
        return {"processed": processed, "escalated": escalated}

    @classmethod
    def cleanup_expired_escalations(cls) -> int:
        cutoff = timezone.now() - timedelta(days=cls.EXPIRED_DAYS)
        deleted, _ = AlertEscalationTask.objects.filter(
            is_active=False, updated_at__lt=cutoff
        ).delete()
        return deleted
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && uv run pytest apps/alerts/tests/test_escalation_service.py -k "scan or advance_resets" -v`
Expected: PASS（5 个用例）

- [ ] **Step 5: Run full escalation service suite**

Run: `cd server && uv run pytest apps/alerts/tests/test_escalation_service.py -v`
Expected: PASS（全部）

- [ ] **Step 6: Commit**

```bash
git add server/apps/alerts/service/escalation_service.py server/apps/alerts/tests/test_escalation_service.py
git commit -m "feat(alerts): escalation scan, layer advance, notification, reminder reset"
```

---

## Task 5: 提醒发送改读升级在岗集合/渠道

**Files:**
- Modify: `server/apps/alerts/service/escalation_service.py`（新增 `active_roster_for_reminder`）
- Modify: `server/apps/alerts/service/reminder_service.py:398-439`（`_send_reminder_notification` 内 username/channel 改写）
- Test: `server/apps/alerts/tests/test_escalation_service.py`

- [ ] **Step 1: Write the failing test**

追加到 `test_escalation_service.py`：

```python
@pytest.mark.django_db
def test_active_roster_for_reminder_replace_mode():
    alert = _make_alert(status="pending")
    assignment = _make_assignment(escalation=_chain(mode="replace"))
    task = ES.create_escalation_task(alert, assignment)
    task.current_layer_index = 1
    task.save()
    roster, channels = ES.active_roster_for_reminder(alert)
    assert roster == ["u2"]            # replace: 仅本层
    assert channels is None             # 本层未配渠道 -> None（调用方沿用 assignment 渠道）


@pytest.mark.django_db
def test_active_roster_for_reminder_none_when_no_task():
    alert = _make_alert(status="pending")
    assert ES.active_roster_for_reminder(alert) == (None, None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && uv run pytest apps/alerts/tests/test_escalation_service.py -k active_roster_for_reminder -v`
Expected: FAIL — `AttributeError: ... has no attribute 'active_roster_for_reminder'`

- [ ] **Step 3: Add `active_roster_for_reminder`**

在 `EscalationService` 内追加：

```python
    @classmethod
    def active_roster_for_reminder(cls, alert: Alert):
        """供提醒发送复用：返回 (在岗集合, 当前层渠道)。
        无活跃升级任务时返回 (None, None)，调用方沿用分派规则原值。"""
        task = AlertEscalationTask.objects.filter(alert=alert, is_active=True).first()
        if not task:
            return None, None
        roster = cls.compute_roster(task.layers, task.current_layer_index, task.mode)
        channels = task.layers[task.current_layer_index].get("notify_channels") or None
        return roster, channels
```

- [ ] **Step 4: Wire into `_send_reminder_notification`**

在 `server/apps/alerts/service/reminder_service.py`，把 `_send_reminder_notification` 中这段（约 398-419 行）：

```python
            username_list = assignment.personnel
            if not username_list:
                logger.warning(
                    f"提醒任务 {assignment.id} 没有配置接收人员，无法发送通知"
                )
                return False

            channel_list = assignment.notify_channels
```

替换为：

```python
            from apps.alerts.service.escalation_service import EscalationService

            roster, layer_channels = EscalationService.active_roster_for_reminder(alert)
            username_list = roster if roster is not None else assignment.personnel
            if not username_list:
                logger.warning(
                    f"提醒任务 {assignment.id} 没有配置接收人员，无法发送通知"
                )
                return False

            channel_list = layer_channels if layer_channels else assignment.notify_channels
```

（其余 `channel_list` 的 str 解析与后续逻辑保持不变。）

- [ ] **Step 5: Write integration test that reminder uses escalation roster**

追加到 `test_escalation_service.py`：

```python
@pytest.mark.django_db
@mock.patch("apps.alerts.tasks.sync_notify.delay")
def test_reminder_send_uses_escalation_roster(mock_delay):
    from apps.alerts.service.reminder_service import ReminderService
    alert = _make_alert(status="pending")
    assignment = _make_assignment(
        escalation=_chain(mode="replace"),
        personnel=["orig"],
        channels=[{"id": 1, "channel_type": "email", "name": "邮件"}],
    )
    task = ES.create_escalation_task(alert, assignment)
    task.current_layer_index = 1  # 在岗集合应为 u2
    task.save()
    ReminderService._send_reminder_notification(assignment=assignment, alert=alert, reminder_id=None)
    args, _ = mock_delay.call_args
    sent_usernames = args[0][0]["username_list"]
    assert sent_usernames == ["u2"]   # 不是 assignment.personnel(["orig"])
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd server && uv run pytest apps/alerts/tests/test_escalation_service.py -k "active_roster_for_reminder or reminder_send_uses" -v`
Expected: PASS（3 个用例）

- [ ] **Step 7: Run reminder regression suite**

Run: `cd server && uv run pytest apps/alerts/tests/test_reminder_service.py -v`
Expected: PASS（无回归：无升级任务时 `active_roster_for_reminder` 返回 None，行为不变）

- [ ] **Step 8: Commit**

```bash
git add server/apps/alerts/service/escalation_service.py server/apps/alerts/service/reminder_service.py server/apps/alerts/tests/test_escalation_service.py
git commit -m "feat(alerts): reminders notify the active escalation roster and layer channels"
```

---

## Task 6: 分派/认领/解决/关闭/改派 钩子

**Files:**
- Modify: `server/apps/alerts/service/alter_operator.py`（`_assign_alert:172` 后、`_acknowledge_alert:254`、`_reassign_alert:344`，以及 `_close_alert`/`_resolve_alert` 的停提醒处）
- Test: `server/apps/alerts/tests/test_escalation_assignment_flow.py`

- [ ] **Step 1: Locate the resolve/close stop-reminder calls**

Run: `cd server && grep -n "_stop_reminder_tasks\|def _close_alert\|def _resolve_alert" apps/alerts/service/alter_operator.py`
Expected: 列出 `_close_alert`/`_resolve_alert`/认领 中调用 `self._stop_reminder_tasks(alert)` 的行号。记下这些行，Step 4 在每处其后补一行停升级。

- [ ] **Step 2: Write the failing flow test**

新建 `server/apps/alerts/tests/test_escalation_assignment_flow.py`：

```python
import pytest
from unittest import mock

from apps.alerts.models.alert_operator import AlertAssignment, AlertEscalationTask
from apps.alerts.models.models import Alert
from apps.alerts.service.alter_operator import AlertOperatorService


def _chain():
    return {"enabled": True, "mode": "append", "layers": [
        {"personnel": ["u1"], "wait_minutes": 10, "notify_channels": []},
        {"personnel": ["u2"], "wait_minutes": 20, "notify_channels": []},
    ]}


@pytest.fixture
def assignment(db):
    return AlertAssignment.objects.create(
        name="esc-rule", match_type="all", personnel=["u1"],
        notify_channels=[{"id": 1, "channel_type": "email", "name": "邮件"}],
        notification_frequency={}, config={"escalation": _chain()},
    )


def _alert(status="unassigned"):
    return Alert.objects.create(
        alert_id="FA1", level="0", title="t", content="c",
        fingerprint="fp1", status=status, operator=[],
    )


@pytest.mark.django_db
@mock.patch("apps.alerts.tasks.sync_notify.delay")
def test_assign_creates_escalation_task(mock_delay, assignment):
    alert = _alert("unassigned")
    svc = AlertOperatorService(user="u1")
    svc._assign_alert(alert.alert_id, {"assignee": ["u1"], "assignment_id": assignment.id})
    task = AlertEscalationTask.objects.get(alert=alert)
    assert task.is_active is True
    assert task.current_layer_index == 0


@pytest.mark.django_db
@mock.patch("apps.alerts.tasks.sync_notify.delay")
def test_acknowledge_stops_escalation(mock_delay, assignment):
    alert = _alert("pending")
    alert.operator = ["u1"]
    alert.save()
    AlertEscalationTask.objects.create(
        alert=alert, assignment=assignment, is_active=True, mode="append",
        layers=_chain()["layers"], current_layer_index=0,
        layer_started_at=alert.created_at,
    )
    svc = AlertOperatorService(user="u1")
    svc._acknowledge_alert(alert.alert_id, {})
    assert AlertEscalationTask.objects.get(alert=alert).is_active is False


@pytest.mark.django_db
@mock.patch("apps.alerts.tasks.sync_notify.delay")
def test_reassign_resets_escalation_to_layer_zero(mock_delay, assignment):
    alert = _alert("processing")
    alert.operator = ["u1"]
    alert.save()
    AlertEscalationTask.objects.create(
        alert=alert, assignment=assignment, is_active=False, mode="append",
        layers=_chain()["layers"], current_layer_index=1,
        layer_started_at=alert.created_at,
    )
    svc = AlertOperatorService(user="u1")
    svc._reassign_alert(alert.alert_id, {"assignee": ["u9"], "assignment_id": assignment.id})
    task = AlertEscalationTask.objects.get(alert=alert)
    assert task.is_active is True
    assert task.current_layer_index == 0
```

注：若 `AlertOperatorService` 构造签名不同，先 `grep -n "class AlertOperatorService\|def __init__" apps/alerts/service/alter_operator.py` 确认 `user` 参数名后调整。

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd server && uv run pytest apps/alerts/tests/test_escalation_assignment_flow.py -v`
Expected: FAIL — 升级任务未被创建/停止/重置

- [ ] **Step 4: Add the hooks in `alter_operator.py`**

`_assign_alert`，在 `self._create_reminder_record(alert, assignment_id)`（约 172 行）之后补：

```python
                self._create_escalation_task(alert, assignment_id)
```

`_acknowledge_alert`，在 `self._stop_reminder_tasks(alert)`（约 254 行）之后补：

```python
            self._stop_escalation_tasks(alert)
```

在 `_close_alert` 与 `_resolve_alert` 中各自 `self._stop_reminder_tasks(alert)` 之后，同样补一行 `self._stop_escalation_tasks(alert)`（行号见 Step 1）。

`_reassign_alert`，在 `self._ensure_reminder_tasks(alert, assignment_id)`（约 344 行）之后补：

```python
            self._reset_escalation_tasks(alert, assignment_id)
```

在 `_stop_reminder_tasks` 方法（约 97-104 行）之后新增三个辅助方法：

```python
    def _create_escalation_task(self, alert: Alert, assignment_id: str):
        """分派时创建升级任务"""
        try:
            from apps.alerts.service.escalation_service import EscalationService

            assignment = AlertAssignment.objects.get(id=assignment_id, is_active=True)
            EscalationService.create_escalation_task(alert, assignment)
        except AlertAssignment.DoesNotExist:
            logger.error(f"分派策略不存在: assignment_id={assignment_id}")
        except Exception:
            logger.exception(f"创建升级任务失败: alert_id={alert.alert_id}")

    def _stop_escalation_tasks(self, alert: Alert):
        """认领/解决/关闭后停止升级任务"""
        try:
            from apps.alerts.service.escalation_service import EscalationService

            EscalationService.stop_escalation_task(alert)
        except Exception as e:
            logger.error(f"停止升级任务失败: {str(e)}")

    def _reset_escalation_tasks(self, alert: Alert, assignment_id: str = None):
        """改派后升级计时重置到第一层"""
        try:
            from apps.alerts.service.escalation_service import EscalationService

            assignment = None
            if assignment_id not in (None, ""):
                assignment = AlertAssignment.objects.filter(
                    id=assignment_id, is_active=True
                ).first()
            EscalationService.reset_escalation_task(alert, assignment)
        except Exception as e:
            logger.error(f"重置升级任务失败: {str(e)}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd server && uv run pytest apps/alerts/tests/test_escalation_assignment_flow.py -v`
Expected: PASS（3 个用例）

- [ ] **Step 6: Run operator regression suite**

Run: `cd server && uv run pytest apps/alerts/tests/test_alert_operator.py -v`
Expected: PASS（无回归）

- [ ] **Step 7: Commit**

```bash
git add server/apps/alerts/service/alter_operator.py server/apps/alerts/tests/test_escalation_assignment_flow.py
git commit -m "feat(alerts): wire escalation into assign/ack/resolve/close/reassign"
```

---

## Task 7: Beat 任务注册 + 清理

**Files:**
- Modify: `server/apps/alerts/tasks/tasks.py`（新增 `check_and_send_escalations`；`cleanup_reminder_tasks` 顺带清升级）
- Modify: `server/apps/alerts/config.py`
- Test: `server/apps/alerts/tests/test_escalation_service.py`

- [ ] **Step 1: Write the failing test**

追加到 `test_escalation_service.py`：

```python
@pytest.mark.django_db
@mock.patch("apps.alerts.service.escalation_service.EscalationService.check_and_process_escalations")
def test_celery_task_invokes_service(mock_check):
    mock_check.return_value = {"processed": 2, "escalated": 1}
    from apps.alerts.tasks.tasks import check_and_send_escalations
    result = check_and_send_escalations()
    mock_check.assert_called_once()
    assert result["escalated"] == 1


@pytest.mark.django_db
def test_cleanup_expired_escalations_deletes_old_inactive():
    from django.utils import timezone
    from datetime import timedelta
    alert = _make_alert()
    assignment = _make_assignment(escalation=_chain())
    task = ES.create_escalation_task(alert, assignment)
    task.is_active = False
    task.save()
    AlertEscalationTask.objects.filter(alert=alert).update(
        updated_at=timezone.now() - timedelta(days=40)
    )
    assert ES.cleanup_expired_escalations() == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && uv run pytest apps/alerts/tests/test_escalation_service.py -k "celery_task_invokes or cleanup_expired_escalations" -v`
Expected: FAIL — `ImportError: cannot import name 'check_and_send_escalations'`

- [ ] **Step 3: Add the celery task**

在 `server/apps/alerts/tasks/tasks.py` 的 `cleanup_reminder_tasks` 之后追加：

```python
@shared_task
def check_and_send_escalations():
    """统一的升级检查任务 - 每分钟执行一次轮询"""
    logger.info("== 开始检查升级任务 ==")
    try:
        from apps.alerts.service.escalation_service import EscalationService

        result = EscalationService.check_and_process_escalations()
        logger.info(
            f"== 升级任务检查完成 == 处理={result.get('processed', 0)}, 升级={result.get('escalated', 0)}"
        )
        return result
    except Exception as e:
        logger.error(f"升级任务检查失败: {str(e)}")
        return {"processed": 0, "escalated": 0, "error": str(e)}
```

并在 `cleanup_reminder_tasks` 的 `cleaned_count = ReminderService.cleanup_expired_reminders()` 之后补一行清理升级（同一小时任务内顺带）：

```python
        from apps.alerts.service.escalation_service import EscalationService
        EscalationService.cleanup_expired_escalations()
```

- [ ] **Step 4: Register the beat schedule**

在 `server/apps/alerts/config.py` 的 `CELERY_BEAT_SCHEDULE` 字典内，`check_and_send_reminders` 条目之后追加：

```python
    "check_and_send_escalations": {
        "task": "apps.alerts.tasks.tasks.check_and_send_escalations",
        "schedule": crontab(minute="*"),
    },
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd server && uv run pytest apps/alerts/tests/test_escalation_service.py -k "celery_task_invokes or cleanup_expired_escalations" -v`
Expected: PASS

- [ ] **Step 6: Run the whole alerts escalation suite**

Run: `cd server && uv run pytest apps/alerts/tests/test_escalation_service.py apps/alerts/tests/test_escalation_assignment_flow.py -v`
Expected: PASS（全部）

- [ ] **Step 7: Commit**

```bash
git add server/apps/alerts/tasks/tasks.py server/apps/alerts/config.py server/apps/alerts/tests/test_escalation_service.py
git commit -m "feat(alerts): register escalation beat task and cleanup"
```

---

## Task 8: 序列化器校验升级链配置

**Files:**
- Modify: `server/apps/alerts/serializers/assignment_shield.py`
- Test: `server/apps/alerts/tests/test_assignment_config_validation.py`

- [ ] **Step 1: Write the failing tests**

新建 `server/apps/alerts/tests/test_assignment_config_validation.py`：

```python
import pytest
from apps.alerts.serializers.assignment_shield import AlertAssignmentModelSerializer


def _payload(escalation):
    return {
        "name": "r1", "match_type": "all",
        "notify_channels": [{"id": 1, "channel_type": "email", "name": "邮件"}],
        "personnel": ["u1"],
        "config": {"escalation": escalation},
    }


@pytest.mark.django_db
def test_valid_escalation_passes():
    ser = AlertAssignmentModelSerializer(data=_payload({
        "enabled": True, "mode": "append",
        "layers": [{"personnel": ["u1"], "wait_minutes": 10, "notify_channels": []}],
    }))
    assert ser.is_valid(), ser.errors


@pytest.mark.django_db
def test_disabled_escalation_skips_validation():
    ser = AlertAssignmentModelSerializer(data=_payload({"enabled": False}))
    assert ser.is_valid(), ser.errors


@pytest.mark.django_db
@pytest.mark.parametrize("bad", [
    {"enabled": True, "mode": "bogus", "layers": [{"personnel": ["u1"], "wait_minutes": 10}]},
    {"enabled": True, "mode": "append", "layers": []},
    {"enabled": True, "mode": "append", "layers": [{"personnel": [], "wait_minutes": 10}]},
    {"enabled": True, "mode": "append", "layers": [{"personnel": ["u1"], "wait_minutes": 0}]},
])
def test_invalid_escalation_rejected(bad):
    ser = AlertAssignmentModelSerializer(data=_payload(bad))
    assert not ser.is_valid()
    assert "config" in ser.errors
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && uv run pytest apps/alerts/tests/test_assignment_config_validation.py -v`
Expected: FAIL — 非法配置当前未被拒绝（`is_valid()` 返回 True）

- [ ] **Step 3: Add `validate_config`**

在 `server/apps/alerts/serializers/assignment_shield.py` 的 `AlertAssignmentModelSerializer` 内（`class Meta` 之前）加：

```python
    def validate_config(self, value):
        """校验升级链配置块（未启用则跳过）。"""
        from apps.alerts.service.escalation_service import EscalationService

        block = (value or {}).get("escalation")
        if not block or not block.get("enabled"):
            return value
        if EscalationService.parse_escalation_config(value) is None:
            raise serializers.ValidationError(
                "升级链配置无效：模式须为 append/替换，至少一层，每层须有处理人且等待时长大于 0"
            )
        return value
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && uv run pytest apps/alerts/tests/test_assignment_config_validation.py -v`
Expected: PASS（6 个用例）

- [ ] **Step 5: Commit**

```bash
git add server/apps/alerts/serializers/assignment_shield.py server/apps/alerts/tests/test_assignment_config_validation.py
git commit -m "feat(alerts): validate escalation chain config on assignment save"
```

---

## Task 9: 后端全量回归

**Files:** —（仅运行）

- [ ] **Step 1: Run full alerts app test suite**

Run: `cd server && uv run pytest apps/alerts/ -v`
Expected: PASS（含新增升级用例、提醒/分派回归无破坏）。若有失败，按 systematic-debugging 修复后再继续。

- [ ] **Step 2: Lint changed files**

Run: `cd server && uv run black apps/alerts/service/escalation_service.py apps/alerts/service/reminder_service.py apps/alerts/service/alter_operator.py && uv run flake8 apps/alerts/service/escalation_service.py`
Expected: 无错误（black 可能重排；若有改动一并提交）。

- [ ] **Step 3: Commit any formatting**

```bash
git add -A server/apps/alerts/
git commit -m "chore(alerts): format escalation modules" || echo "nothing to format"
```

---

## Task 10: 前端升级链子组件

**Files:**
- Create: `web/src/app/alarm/(pages)/settings/alertAssign/components/escalationChain.tsx`
- Modify: `web/src/app/alarm/locales/en.json`、`web/src/app/alarm/locales/zh.json`

注：前端 `config` 字段透传到后端（`getParams` 已写 `config`）。本任务做受控子组件，下一任务接入表单。

- [ ] **Step 1: Add i18n keys**

在 `web/src/app/alarm/locales/zh.json` 的 `settings.assignStrategy` 节点内加：

```json
"escalation": "告警升级",
"escalationEnable": "启用升级",
"escalationMode": "升级模式",
"escalationModeAppend": "累加",
"escalationModeReplace": "替换",
"escalationLayer": "升级层级",
"escalationAddLayer": "添加层级",
"escalationWaitMinutes": "未认领等待时长",
"escalationLayerChannel": "本层通知渠道（可选）",
"escalationPersonnelTip": "请选择本层处理人",
"escalationLayerRequired": "启用升级时至少配置一层"
```

在 `web/src/app/alarm/locales/en.json` 对应节点加同名键（英文值）：

```json
"escalation": "Escalation",
"escalationEnable": "Enable escalation",
"escalationMode": "Escalation mode",
"escalationModeAppend": "Accumulate",
"escalationModeReplace": "Replace",
"escalationLayer": "Layer",
"escalationAddLayer": "Add layer",
"escalationWaitMinutes": "Wait before escalating",
"escalationLayerChannel": "Layer channels (optional)",
"escalationPersonnelTip": "Select responders for this layer",
"escalationLayerRequired": "At least one layer is required when escalation is enabled"
```

- [ ] **Step 2: Create the component**

新建 `web/src/app/alarm/(pages)/settings/alertAssign/components/escalationChain.tsx`：

```tsx
'use client';

import React from 'react';
import { Form, Switch, Radio, Select, InputNumber, Checkbox, Button, Space } from 'antd';
import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';

interface Option {
  label: string;
  value: string;
}

interface EscalationChainProps {
  enabled: boolean;
  personnelOptions: Option[];
  channelOptions: Option[];
}

const EscalationChain: React.FC<EscalationChainProps> = ({
  enabled,
  personnelOptions,
  channelOptions,
}) => {
  const { t } = useTranslation();

  return (
    <>
      <Form.Item
        name={['escalation', 'enabled']}
        label={t('settings.assignStrategy.escalationEnable')}
        valuePropName="checked"
        initialValue={false}
      >
        <Switch />
      </Form.Item>

      {enabled && (
        <>
          <Form.Item
            name={['escalation', 'mode']}
            label={t('settings.assignStrategy.escalationMode')}
            initialValue="append"
            rules={[{ required: true }]}
          >
            <Radio.Group>
              <Radio value="append">
                {t('settings.assignStrategy.escalationModeAppend')}
              </Radio>
              <Radio value="replace">
                {t('settings.assignStrategy.escalationModeReplace')}
              </Radio>
            </Radio.Group>
          </Form.Item>

          <Form.List
            name={['escalation', 'layers']}
            rules={[
              {
                validator: async (_, layers) => {
                  if (!layers || layers.length < 1) {
                    return Promise.reject(
                      new Error(
                        t('settings.assignStrategy.escalationLayerRequired')
                      )
                    );
                  }
                },
              },
            ]}
          >
            {(fields, { add, remove }, { errors }) => (
              <>
                {fields.map((field, index) => (
                  <div
                    key={field.key}
                    className="border rounded p-3 mb-3 ml-[110px]"
                  >
                    <Space align="baseline" className="w-full justify-between">
                      <span className="font-bold">
                        {t('settings.assignStrategy.escalationLayer')} {index + 1}
                      </span>
                      <MinusCircleOutlined onClick={() => remove(field.name)} />
                    </Space>
                    <Form.Item
                      {...field}
                      key={`${field.key}-personnel`}
                      name={[field.name, 'personnel']}
                      label={t('settings.assignStrategy.formPersonnelSelect')}
                      rules={[{ required: true, message: t('settings.assignStrategy.escalationPersonnelTip') }]}
                    >
                      <Select mode="multiple" options={personnelOptions} />
                    </Form.Item>
                    <Form.Item
                      {...field}
                      key={`${field.key}-wait`}
                      name={[field.name, 'wait_minutes']}
                      label={t('settings.assignStrategy.escalationWaitMinutes')}
                      initialValue={10}
                      rules={[{ required: true, type: 'number', min: 1 }]}
                    >
                      <InputNumber min={1} addonAfter={t('settings.assignStrategy.frequencyUnit')} />
                    </Form.Item>
                    <Form.Item
                      {...field}
                      key={`${field.key}-channels`}
                      name={[field.name, 'notify_channels']}
                      label={t('settings.assignStrategy.escalationLayerChannel')}
                    >
                      <Checkbox.Group options={channelOptions} />
                    </Form.Item>
                  </div>
                ))}
                <Form.Item className="ml-[110px]">
                  <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>
                    {t('settings.assignStrategy.escalationAddLayer')}
                  </Button>
                  <Form.ErrorList errors={errors} />
                </Form.Item>
              </>
            )}
          </Form.List>
        </>
      )}
    </>
  );
};

export default EscalationChain;
```

- [ ] **Step 3: Type-check**

Run: `cd web && pnpm type-check`
Expected: 无新增类型错误（关于本文件）。

- [ ] **Step 4: Commit**

```bash
git add "web/src/app/alarm/(pages)/settings/alertAssign/components/escalationChain.tsx" web/src/app/alarm/locales/en.json web/src/app/alarm/locales/zh.json
git commit -m "feat(web/alarm): escalation chain form subcomponent"
```

---

## Task 11: 接入分派规则表单（回填 + getParams + personnel 单一来源）

**Files:**
- Modify: `web/src/app/alarm/(pages)/settings/alertAssign/components/operateModal.tsx`

- [ ] **Step 1: Import the subcomponent and watch enabled**

在 `operateModal.tsx` 顶部 import 区加：

```tsx
import EscalationChain from './escalationChain';
```

在 `const ruleType = Form.useWatch('match_type', form);`（约 119 行）之后加：

```tsx
  const escalationEnabled = Form.useWatch(['escalation', 'enabled'], form);
  const escalationLayers = Form.useWatch(['escalation', 'layers'], form);
  const channelCheckOptions = notifyOptions; // {label,value} 已是渠道选项
```

- [ ] **Step 2: Render the block inside the advanced Collapse panel**

在 `notification_frequency` 的 `Form.Item` 结束 `</Form.Item>`（约 392 行）之后、`</Collapse.Panel>` 之前插入：

```tsx
            <div className="text-base font-bold mb-2">
              {t('settings.assignStrategy.escalation')}
            </div>
            <EscalationChain
              enabled={!!escalationEnabled}
              personnelOptions={personnelOptions}
              channelOptions={channelCheckOptions}
            />
```

- [ ] **Step 3: Backfill escalation on edit**

在 `useEffect` 里 `if (currentRow) { ... form.setFieldsValue({ ... })}`（约 98-111 行），在传入对象中补 `escalation`：

把：

```tsx
          config: {
            ...currentRow.config,
            start_time: currentRow.config?.start_time,
            end_time: currentRow.config?.end_time,
          },
        });
```

改为：

```tsx
          config: {
            ...currentRow.config,
            start_time: currentRow.config?.start_time,
            end_time: currentRow.config?.end_time,
          },
          escalation: currentRow.config?.escalation
            ? {
                ...currentRow.config.escalation,
                layers: (currentRow.config.escalation.layers || []).map(
                  (l: any) => ({
                    ...l,
                    notify_channels: (l.notify_channels || []).map((ch: any) =>
                      ch.id.toString()
                    ),
                  })
                ),
              }
            : { enabled: false },
        });
```

- [ ] **Step 4: Write escalation into config in getParams + single source for personnel**

在 `getParams`（约 143 行）内，`params` 对象构造之后、`return params` 之前插入：

```tsx
    const esc = values.escalation;
    if (esc?.enabled) {
      const layers = (esc.layers || []).map((l: any) => ({
        personnel: l.personnel || [],
        wait_minutes: l.wait_minutes || 0,
        notify_channels: (l.notify_channels || [])
          .map((id: string) => channelList.find((ch) => ch.id.toString() === id))
          .filter(Boolean),
      }));
      params.config = {
        ...params.config,
        escalation: { enabled: true, mode: esc.mode || 'append', layers },
      };
      // 单一来源：启用升级时初始分派人 = 第 0 层处理人
      if (layers[0]?.personnel?.length) {
        params.personnel = layers[0].personnel;
      }
    } else {
      params.config = { ...params.config, escalation: { enabled: false } };
    }
```

- [ ] **Step 5: Type-check and lint**

Run: `cd web && pnpm type-check && pnpm lint`
Expected: 无新增错误。

- [ ] **Step 6: Verify in the browser (preview workflow)**

启动 web dev（若未运行），打开告警 → 设置 → 告警分派 → 新建：展开"高级"，开启"启用升级"，加两层、各选处理人和等待时长，保存。再编辑该规则确认升级链正确回填。用 preview_snapshot/preview_screenshot 留证。

- [ ] **Step 7: Commit**

```bash
git add "web/src/app/alarm/(pages)/settings/alertAssign/components/operateModal.tsx"
git commit -m "feat(web/alarm): integrate escalation chain into assignment form"
```

---

## Task 12: BDD 场景（端到端口径，中文 Gherkin）

**Files:**
- Create: `server/apps/alerts/tests/bdd/escalation.feature`
- Create: `server/apps/alerts/tests/bdd/test_escalation_bdd.py`

参照 `server/docs/testing-guide.md` 的 BDD 约定（flat 目录、`scenarios(FEATURE)`、中文 Gherkin）。

- [ ] **Step 1: Write the feature file**

新建 `server/apps/alerts/tests/bdd/escalation.feature`：

```gherkin
# language: zh-CN
功能: 告警超时升级
  作为运维负责人
  我希望告警在规定时长内无人认领时自动升级到下一层处理人
  以便兜底无人响应的场景

  场景: 第一层超时未认领自动升级到第二层
    假如 存在一条配置了两层升级链的分派规则
    并且 一条告警已分派且停留在待响应状态超过第一层等待时长
    当 升级扫描任务运行
    那么 告警进入第二层并通知第二层处理人
    并且 第二层处理人具备认领资格

  场景: 告警被认领后不再升级
    假如 存在一条配置了升级链的分派规则
    并且 一条告警已分派并被认领进入处理中
    当 升级扫描任务运行
    那么 升级任务被停用且层级不变
```

- [ ] **Step 2: Write the step definitions**

新建 `server/apps/alerts/tests/bdd/test_escalation_bdd.py`：

```python
import os
from datetime import timedelta

import pytest
from django.utils import timezone
from pytest_bdd import scenarios, given, when, then

from apps.alerts.models.alert_operator import AlertAssignment, AlertEscalationTask
from apps.alerts.models.models import Alert
from apps.alerts.service.escalation_service import EscalationService

FEATURE = os.path.join(os.path.dirname(__file__), "escalation.feature")
scenarios(FEATURE)

LAYERS = [
    {"personnel": ["u1"], "wait_minutes": 10, "notify_channels": []},
    {"personnel": ["u2"], "wait_minutes": 20, "notify_channels": []},
]


@pytest.fixture
def ctx():
    return {}


@given("存在一条配置了两层升级链的分派规则")
@given("存在一条配置了升级链的分派规则")
def _rule(ctx, db):
    ctx["assignment"] = AlertAssignment.objects.create(
        name="bdd-esc", match_type="all", personnel=["u1"],
        notify_channels=[{"id": 1, "channel_type": "email", "name": "邮件"}],
        config={"escalation": {"enabled": True, "mode": "append", "layers": LAYERS}},
    )


@given("一条告警已分派且停留在待响应状态超过第一层等待时长")
def _pending_overdue(ctx):
    alert = Alert.objects.create(
        alert_id="BDD1", level="0", title="t", content="c",
        fingerprint="bdd1", status="pending", operator=["u1"],
    )
    task = EscalationService.create_escalation_task(alert, ctx["assignment"])
    task.layer_started_at = timezone.now() - timedelta(minutes=15)
    task.save()
    ctx["alert"] = alert


@given("一条告警已分派并被认领进入处理中")
def _processing(ctx):
    alert = Alert.objects.create(
        alert_id="BDD2", level="0", title="t", content="c",
        fingerprint="bdd2", status="processing", operator=["u1"],
    )
    task = EscalationService.create_escalation_task(alert, ctx["assignment"])
    task.layer_started_at = timezone.now() - timedelta(minutes=15)
    task.save()
    ctx["alert"] = alert


@when("升级扫描任务运行")
def _run(ctx, monkeypatch):
    monkeypatch.setattr(
        EscalationService, "_send_escalation_notification",
        classmethod(lambda cls, *a, **k: True),
    )
    EscalationService.check_and_process_escalations()
    ctx["task"] = AlertEscalationTask.objects.get(alert=ctx["alert"])
    ctx["alert"].refresh_from_db()


@then("告警进入第二层并通知第二层处理人")
def _at_layer_two(ctx):
    assert ctx["task"].current_layer_index == 1


@then("第二层处理人具备认领资格")
def _claimable(ctx):
    assert "u2" in ctx["alert"].operator


@then("升级任务被停用且层级不变")
def _stopped(ctx):
    assert ctx["task"].is_active is False
    assert ctx["task"].current_layer_index == 0
```

- [ ] **Step 3: Run the BDD scenarios**

Run: `cd server && uv run pytest apps/alerts/tests/bdd/test_escalation_bdd.py -v`
Expected: PASS（2 scenarios）

- [ ] **Step 4: Commit**

```bash
git add server/apps/alerts/tests/bdd/escalation.feature server/apps/alerts/tests/bdd/test_escalation_bdd.py
git commit -m "test(alerts): BDD scenarios for alert escalation"
```

---

## Task 13: 最终验收 — 全栈回归

**Files:** —（仅运行）

- [ ] **Step 1: Backend full suite**

Run: `cd server && uv run pytest apps/alerts/ -v`
Expected: PASS（全部，含 BDD）。

- [ ] **Step 2: Web type-check + lint**

Run: `cd web && pnpm type-check && pnpm lint`
Expected: 无新增错误。

- [ ] **Step 3: 对照 spec 验收口径逐条自检**

打开 `spec/requirements/告警中心/20260531.告警中心-新增告警升级策略.md` §5，逐条对应到测试：
- 可配置升级链 → Task 8 + Task 10/11
- 超时进下一层、末层不再升级 → Task 4
- 按时间不按次数、提醒跳过仍推进 → Task 4（时间驱动，独立扫描）
- 认领资格累加 → Task 3/4（`_union_into_operator`）
- 跨层提醒计数重置 → Task 4（`_reset_reminder_for_new_roster`）
- 认领/解决/关闭终止、改派重置 → Task 6
- 升级不改级别 → 实现中从不写 `alert.level`（自检 grep 确认）
- 提醒并存、共享发送出口 → Task 5
- 屏蔽不交叉 → 设计层面成立（升级不调用屏蔽，告警级通知本不过屏蔽）
- 即时告警覆盖 → 升级任务由分派创建，与告警来源无关，天然覆盖
- 规则停用即停升级 → 末层/状态变更终止；规则停用使 `create/reset` 不再续期

Run（确认升级路径从不改级别）: `cd server && grep -n "\.level" apps/alerts/service/escalation_service.py`
Expected: 无对 `alert.level` 的赋值（只读不写）。

- [ ] **Step 4: Final commit (if any leftover)**

```bash
git add -A && git commit -m "chore(alerts): finalize alert escalation feature" || echo "clean"
```

---

## Self-Review 注记（写计划时已核对）

- **Spec 覆盖**：§2 配置、§3.1 配置项、§3.2 触发/终止/改派、§3.3 不改级别、§3.4 认领累加、§3.5 两时钟+计数重置+去重、§3.6 屏蔽不交叉、§3.7 即时告警、§4 架构（已改为独立表，Task 0 同步 spec）、§5 验收（Task 13 逐条）、§6 边界——均有对应任务。
- **去重口径**：在岗集合用 `dict.fromkeys` 去重保序，提醒按集合发送，天然满足"同一在岗集合一轮只发一次"。
- **命名一致性**：`AlertEscalationTask`、`EscalationService.{parse_escalation_config, compute_roster, create_escalation_task, stop_escalation_task, reset_escalation_task, active_roster_for_reminder, check_and_process_escalations, _advance_layer, _send_escalation_notification, _reset_reminder_for_new_roster, _union_into_operator, cleanup_expired_escalations}`、celery `check_and_send_escalations`、beat key `check_and_send_escalations`、config 键 `escalation/enabled/mode/layers/personnel/wait_minutes/notify_channels`——前后任务一致。
- **已知边界**：改派后升级按链从第 0 层重走（非手选新分派人逐层），与 spec §3.2"再按完整升级链走"一致；前端以"启用升级时 personnel=第0层"保证初始分派与升级链单一来源。
