"""节点管理同步默认打开后，与推送联动共用身份，不再硬阻断拉取。"""

import pytest
from django_celery_beat.models import PeriodicTask

from apps.cmdb.services import node_mgmt_sync_service as node_mgmt_sync_service_mod
from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

pytestmark = pytest.mark.django_db


def test_push_linkage_gate_no_longer_blocks_pull_sync():
    assert node_mgmt_sync_service_mod.PUSH_LINKAGE_REPLACES_PULL_SYNC is False


def test_reconciler_enables_sync_schedule_when_auto_sync_on():
    NodeMgmtSyncService.update_task({"auto_sync_enabled": True, "auto_collect_enabled": True})
    payload = NodeMgmtSyncService.get_task_payload(reconcile=True)

    assert payload["auto_sync_enabled"] is True
    assert NodeMgmtSyncService.SYNC_PERIODIC_TASK_NAME in set(
        PeriodicTask.objects.values_list("name", flat=True)
    )
    assert NodeMgmtSyncService.COLLECT_PERIODIC_TASK_NAME in set(
        PeriodicTask.objects.values_list("name", flat=True)
    )


def test_auto_sync_enabled_defaults_to_true_for_new_config():
    task = NodeMgmtSyncService.get_task()
    assert task.auto_sync_enabled is True
    assert task.auto_collect_enabled is True
