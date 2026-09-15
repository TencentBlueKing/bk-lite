"""评估任务创建应对重复 target_list 按首次出现顺序去重。"""

import pytest
from rest_framework import status

from apps.monitor.models import MonitorPlugin  # noqa: F401  INSTALL_APPS 需含 monitor
from apps.node_mgmt.models import Node  # noqa: F401  列表 URL 加载依赖 node_mgmt
from apps.patch_mgmt.constants import OSType
from apps.patch_mgmt.models import GovernanceTask, PatchTarget

GOVERNANCE_URL = "/api/v1/patch_mgmt/api/governance/"


@pytest.mark.django_db
def test_create_assess_task_deduplicates_repeated_target_ids(su_client, mocker):
    trigger = mocker.patch("apps.patch_mgmt.services.governance_service._trigger_async")
    target = PatchTarget.objects.create(name="web-01", ip="10.0.0.1", os_type=OSType.WINDOWS, team=[1])

    resp = su_client.post(
        GOVERNANCE_URL,
        {"task_type": "assess", "target_list": [target.id, target.id], "execution_mode": "now"},
        format="json",
    )

    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.data["target_list"] == [target.id]
    assert resp.data["host_count"] == 1
    assert "1 台" in resp.data["name"]

    task = GovernanceTask.objects.get(pk=resp.data["id"])
    assert task.target_list == [target.id]
    hosts = list(task.host_results.order_by("id"))
    assert len(hosts) == 1
    assert hosts[0].target_id == target.id
    trigger.assert_called_once_with(resp.data["id"])


@pytest.mark.django_db
def test_create_assess_task_keeps_first_occurrence_order(su_client, mocker):
    trigger = mocker.patch("apps.patch_mgmt.services.governance_service._trigger_async")
    host_a = PatchTarget.objects.create(name="host-a", ip="10.0.0.2", os_type=OSType.WINDOWS, team=[1])
    host_b = PatchTarget.objects.create(name="host-b", ip="10.0.0.3", os_type=OSType.WINDOWS, team=[1])

    resp = su_client.post(
        GOVERNANCE_URL,
        {
            "task_type": "assess",
            "target_list": [host_a.id, host_b.id, host_a.id],
            "execution_mode": "now",
        },
        format="json",
    )

    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.data["target_list"] == [host_a.id, host_b.id]
    assert resp.data["host_count"] == 2
    assert "2 台" in resp.data["name"]

    task = GovernanceTask.objects.get(pk=resp.data["id"])
    assert task.target_list == [host_a.id, host_b.id]
    assert list(task.host_results.order_by("id").values_list("target_id", flat=True)) == [host_a.id, host_b.id]
    trigger.assert_called_once_with(resp.data["id"])
