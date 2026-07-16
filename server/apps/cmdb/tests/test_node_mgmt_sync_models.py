import pytest
from django.db import IntegrityError, transaction

from apps.cmdb.models import NodeMgmtSyncConfig, NodeMgmtSyncRegionState, NodeMgmtSyncRun

pytestmark = pytest.mark.django_db


def test_config_is_database_singleton():
    NodeMgmtSyncConfig.objects.create(singleton_key="default")

    with pytest.raises(IntegrityError), transaction.atomic():
        NodeMgmtSyncConfig.objects.create(singleton_key="default")


def test_only_one_run_can_hold_global_active_scope():
    config = NodeMgmtSyncConfig.objects.create(singleton_key="default")
    NodeMgmtSyncRun.objects.create(
        task=config, run_type="sync", status="running", active_scope="node_mgmt_sync",
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        NodeMgmtSyncRun.objects.create(
            task=config, run_type="collect", status="waiting_sync", active_scope="node_mgmt_sync",
        )


def test_region_state_is_unique_per_run_and_region():
    config = NodeMgmtSyncConfig.objects.create(singleton_key="default")
    run = NodeMgmtSyncRun.objects.create(task=config, run_type="collect", status="submitted")
    scope_key = f"run:{run.generation}:region:1"
    NodeMgmtSyncRegionState.objects.create(
        config=config, run=run, scope_key=scope_key, cloud_region_id="1", status="submitted",
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        NodeMgmtSyncRegionState.objects.create(
            config=config, run=run, scope_key=scope_key, cloud_region_id="1", status="submitted",
        )
