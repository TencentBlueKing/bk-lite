# -*- coding: utf-8 -*-
"""PC 权威采集任务状态机合同测试。

锁定设计 §11：一台 PC 同一时间只由一个权威任务写入和删除；
首次发现绑定来源，其他任务命中返回 SOURCE_TASK_CONFLICT；
显式移交期间新任务可写不可删，只有完整快照落地后才切换权威。
"""
from datetime import datetime, timezone

import pytest

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.pc_discovery import PCDiscoveryAuthority
from apps.cmdb.services.pc_discovery import PCAuthorityService

T1 = datetime(2026, 7, 22, 10, 0, 0, tzinfo=timezone.utc)
T2 = datetime(2026, 7, 22, 11, 0, 0, tzinfo=timezone.utc)
T3 = datetime(2026, 7, 22, 12, 0, 0, tzinfo=timezone.utc)


def _task(name):
    return CollectModels.objects.create(
        name=name,
        task_type=CollectPluginTypes.HOST,
        driver_type=CollectDriverTypes.JOB,
        model_id="pc",
        cycle_value_type="cycle",
    )


@pytest.fixture
def task_a(db):
    return _task("pc-task-a")


@pytest.fixture
def task_b(db):
    return _task("pc-task-b")


@pytest.fixture
def authority(task_a):
    decision = PCAuthorityService.authorize(task_a, "WIN-ABC", "s1", T1)
    PCAuthorityService.mark_applied(decision.authority, "s1", T1)
    return PCDiscoveryAuthority.objects.get(pc_inst_name="WIN-ABC")


@pytest.mark.django_db
def test_first_task_binds_and_second_task_conflicts(task_a, task_b):
    decision = PCAuthorityService.authorize(task_a, "WIN-ABC", "s1", T1)
    assert decision.mode == "owner"
    assert decision.allow_delete is True
    assert decision.authority.authoritative_task_id == task_a.id

    conflict = PCAuthorityService.authorize(task_b, "WIN-ABC", "s2", T2)
    assert conflict.mode == "conflict"
    assert conflict.error_code == "SOURCE_TASK_CONFLICT"
    assert conflict.allow_delete is False


@pytest.mark.django_db
def test_owner_stale_snapshot_is_ignored(authority, task_a):
    stale = PCAuthorityService.authorize(task_a, "WIN-ABC", "s0", T1)
    assert stale.mode == "stale"
    assert stale.allow_delete is False

    fresh = PCAuthorityService.authorize(task_a, "WIN-ABC", "s2", T2)
    assert fresh.mode == "owner"


@pytest.mark.django_db
def test_pending_task_writes_without_delete(authority, task_b):
    PCAuthorityService.request_handover("WIN-ABC", task_b)

    decision = PCAuthorityService.authorize(task_b, "WIN-ABC", "s2", T2)
    assert decision.mode == "pending_handover"
    assert decision.allow_delete is False


@pytest.mark.django_db
def test_partial_snapshot_cannot_complete_handover(authority, task_b):
    PCAuthorityService.request_handover("WIN-ABC", task_b)

    assert PCAuthorityService.complete_handover(authority, task_b, snapshot_status="partial") is False
    authority.refresh_from_db()
    assert authority.authoritative_task_id != task_b.id
    assert authority.pending_task_id == task_b.id


@pytest.mark.django_db
def test_complete_snapshot_switches_authority_and_old_task_conflicts(authority, task_a, task_b):
    PCAuthorityService.request_handover("WIN-ABC", task_b)

    assert PCAuthorityService.complete_handover(authority, task_b, snapshot_status="complete") is True
    authority.refresh_from_db()
    assert authority.authoritative_task_id == task_b.id
    assert authority.pending_task_id is None

    old = PCAuthorityService.authorize(task_a, "WIN-ABC", "s3", T3)
    assert old.mode == "conflict"
    assert old.error_code == "SOURCE_TASK_CONFLICT"


@pytest.mark.django_db
def test_non_pending_task_cannot_complete_handover(authority, task_b):
    assert PCAuthorityService.complete_handover(authority, task_b, snapshot_status="complete") is False
    authority.refresh_from_db()
    assert authority.pending_task_id is None


@pytest.mark.django_db
def test_handover_requires_existing_authority(task_b):
    with pytest.raises(PCDiscoveryAuthority.DoesNotExist):
        PCAuthorityService.request_handover("WIN-MISSING", task_b)
