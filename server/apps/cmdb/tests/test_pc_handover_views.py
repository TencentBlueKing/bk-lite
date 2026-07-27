# -*- coding: utf-8 -*-
"""PC 权威移交 API 与任务删除保护合同测试。

锁定：
- 非 PC 任务调用移交 → 400；
- 对象级权限不足 → 拒绝；
- 不存在的 PC（无权威记录）→ 400；
- 当前 owner 重复移交 → 幂等成功；
- 移交写入 pending_task；
- 仍拥有 PC 的权威任务删除被拒（明确业务错误），完成移交后可删；
- 仅为 pending_task 的任务删除后自动取消待移交（SET_NULL）。
"""
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.pc_discovery import PCDiscoveryAuthority
from apps.cmdb.tests.test_collect_views_actions import _bypass_permission
from apps.cmdb.views.collect import CollectModelViewSet
from apps.core.exceptions.base_app_exception import BaseAppException


def _task(name, model_id="pc"):
    return CollectModels.objects.create(
        name=name,
        task_type=CollectPluginTypes.HOST,
        driver_type=CollectDriverTypes.JOB,
        model_id=model_id,
        cycle_value_type="cycle",
        team=[1],
    )


@pytest.fixture
def superuser(authenticated_user):
    u = authenticated_user
    u.is_superuser = True
    u.group_list = [{"id": 1}]
    u.roles = ["admin"]
    u.domain = "domain.com"
    return u


def _handover(user, task_id, pc_inst_names):
    factory = APIRequestFactory()
    request = factory.post("/x/", data={"pc_inst_names": pc_inst_names}, format="json")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)
    return CollectModelViewSet.as_view({"post": "pc_handover"})(request, pk=task_id)


@pytest.mark.django_db
def test_non_pc_task_rejects_handover(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    task = _task("host-task", model_id="host")

    with pytest.raises(BaseAppException, match="PC"):
        _handover(superuser, task.id, ["WIN-ABC"])


@pytest.mark.django_db
def test_handover_without_object_permission_denied(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    monkeypatch.setattr(CollectModelViewSet, "get_has_permission", lambda *a, **k: False)
    task = _task("pc-task")

    with pytest.raises(BaseAppException, match="权限"):
        _handover(superuser, task.id, ["WIN-ABC"])


@pytest.mark.django_db
def test_handover_unknown_pc_rejected(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    monkeypatch.setattr(CollectModelViewSet, "get_has_permission", lambda *a, **k: True)
    task = _task("pc-task")

    with pytest.raises(BaseAppException, match="WIN-MISSING"):
        _handover(superuser, task.id, ["WIN-MISSING"])


@pytest.mark.django_db
def test_handover_sets_pending_and_owner_repeat_is_idempotent(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    monkeypatch.setattr(CollectModelViewSet, "get_has_permission", lambda *a, **k: True)
    owner = _task("owner")
    new_task = _task("new")
    PCDiscoveryAuthority.objects.create(pc_inst_name="WIN-ABC", authoritative_task=owner)

    response = _handover(superuser, new_task.id, ["WIN-ABC"])
    assert response.status_code == 200
    authority = PCDiscoveryAuthority.objects.get(pc_inst_name="WIN-ABC")
    assert authority.pending_task_id == new_task.id
    assert authority.authoritative_task_id == owner.id

    # 当前 owner 重复发起移交：幂等成功，不生成 pending
    response = _handover(superuser, owner.id, ["WIN-ABC"])
    assert response.status_code == 200
    authority.refresh_from_db()
    assert authority.pending_task_id is None


@pytest.mark.django_db
def test_destroy_blocked_while_task_owns_pc(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    monkeypatch.setattr("apps.cmdb.services.collect_service.CollectModelService.has_permission", lambda *a, **k: True)
    task = _task("owner")
    PCDiscoveryAuthority.objects.create(pc_inst_name="WIN-ABC", authoritative_task=task)

    view = CollectModelViewSet()
    view.get_object = lambda: task
    with pytest.raises(BaseAppException, match="移交"):
        from apps.cmdb.services.collect_service import CollectModelService
        CollectModelService.destroy(None, view)
    assert CollectModels.objects.filter(pk=task.pk).exists()


@pytest.mark.django_db
def test_pending_task_delete_clears_pending_via_set_null(superuser):
    owner = _task("owner")
    pending = _task("pending")
    authority = PCDiscoveryAuthority.objects.create(
        pc_inst_name="WIN-ABC", authoritative_task=owner, pending_task=pending
    )

    pending.delete()

    authority.refresh_from_db()
    assert authority.pending_task_id is None
