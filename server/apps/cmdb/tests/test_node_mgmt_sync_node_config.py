from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.node_mgmt_sync import NodeMgmtSyncConfig, NodeMgmtSyncRegionState
from apps.cmdb.services.collect_service import CollectModelService
from apps.cmdb.services.node_mgmt_sync_reconciler import NodeMgmtSyncReconciler
from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

pytestmark = pytest.mark.django_db


@pytest.fixture
def config():
    return NodeMgmtSyncConfig.objects.create(
        auto_sync_enabled=True, auto_collect_enabled=True, schedule_status="healthy", node_config_status="unknown",
    )


@pytest.fixture
def region_task():
    return _create_region_task(7)


def _create_region_task(region_id, *, system_code=None):
    return CollectModels.objects.create(
        name=f"区域采集-{region_id}",
        task_type="host",
        driver_type="job",
        model_id="host",
        cycle_value_type="cycle",
        cycle_value="30",
        scan_cycle="*/30 * * * *",
        instances=[],
        access_point=[],
        credential=[],
        params={},
        team=[],
        is_system=True,
        is_visible=False,
        system_code=system_code or f"{NodeMgmtSyncService.SYSTEM_TASK_PREFIX}{region_id}",
    )


def _reconcile(config):
    with patch.object(NodeMgmtSyncReconciler, "_reconcile_periodic_task"):
        return NodeMgmtSyncReconciler.reconcile(config, reconcile_node_configs=True,)


def _state(config, region_id=7):
    return NodeMgmtSyncRegionState.objects.get(config=config, config_version=config.version, cloud_region_id=str(region_id),)


def test_disable_collect_only_deletes_node_params(config, region_task):
    config.auto_collect_enabled = False
    config.save(update_fields=["auto_collect_enabled", "updated_at"])

    with patch.object(CollectModelService, "delete_butch_node_params") as delete:
        with patch.object(CollectModelService, "push_butch_node_params") as push:
            result = _reconcile(config)

    delete.assert_called_once_with(region_task)
    push.assert_not_called()
    config.refresh_from_db()
    state = _state(config)
    assert result.node_config_status == "disabled"
    assert config.node_config_status == "disabled"
    assert state.node_config_status == "disabled"
    assert state.scope_key == f"config:{config.version}:region:7"


def test_disable_collect_restarts_old_push_pending_from_delete(config, region_task):
    config.auto_collect_enabled = False
    config.save(update_fields=["auto_collect_enabled", "updated_at"])
    NodeMgmtSyncRegionState.objects.create(
        config=config,
        config_version=config.version,
        cloud_region_id="7",
        collect_task=region_task,
        scope_key=f"config:{config.version}:region:7",
        node_config_status="push_pending",
    )

    with patch.object(CollectModelService, "delete_butch_node_params") as delete:
        with patch.object(CollectModelService, "push_butch_node_params") as push:
            result = _reconcile(config)

    delete.assert_called_once_with(region_task)
    push.assert_not_called()
    assert result.node_config_status == "disabled"
    assert _state(config).node_config_status == "disabled"


def test_disable_collect_old_push_pending_delete_failure_is_retryable(config, region_task):
    config.auto_collect_enabled = False
    config.save(update_fields=["auto_collect_enabled", "updated_at"])
    NodeMgmtSyncRegionState.objects.create(
        config=config,
        config_version=config.version,
        cloud_region_id="7",
        collect_task=region_task,
        scope_key=f"config:{config.version}:region:7",
        node_config_status="push_pending",
    )

    with patch.object(CollectModelService, "delete_butch_node_params", side_effect=[RuntimeError("delete-secret"), None],) as delete:
        with patch.object(CollectModelService, "push_butch_node_params") as push:
            first = _reconcile(config)
            pending_state = _state(config)
            second = _reconcile(config)

    assert first.node_config_status == "degraded"
    assert pending_state.node_config_status == "delete_pending"
    assert pending_state.reason_code == "NODE_CONFIG_DELETE_FAILED"
    assert "delete-secret" not in pending_state.error_message
    assert delete.call_count == 2
    push.assert_not_called()
    assert second.node_config_status == "disabled"
    assert _state(config).node_config_status == "disabled"


def test_enable_collect_deletes_then_pushes(config, region_task):
    calls = []
    with patch.object(
        CollectModelService, "delete_butch_node_params", side_effect=lambda task: calls.append(("delete", task.id)),
    ):
        with patch.object(
            CollectModelService, "push_butch_node_params", side_effect=lambda task: calls.append(("push", task.id)),
        ):
            result = _reconcile(config)

    assert calls == [("delete", region_task.id), ("push", region_task.id)]
    config.refresh_from_db()
    assert result.node_config_status == "healthy"
    assert config.node_config_status == "healthy"
    assert _state(config).node_config_status == "healthy"


def test_delete_failure_stays_delete_pending_and_is_retryable(config, region_task):
    delete_calls = []
    with patch.object(CollectModelService, "delete_butch_node_params", side_effect=[RuntimeError("delete-secret"), None],) as delete:
        with patch.object(CollectModelService, "push_butch_node_params") as push:
            first = _reconcile(config)
            delete_calls.append(delete.call_count)
            second = _reconcile(config)

    assert first.node_config_status == "degraded"
    assert delete_calls == [1]
    assert delete.call_count == 2
    push.assert_called_once_with(region_task)
    assert second.node_config_status == "healthy"
    assert _state(config).node_config_status == "healthy"


def test_push_failure_stays_push_pending_and_retries_from_push(config, region_task):
    with patch.object(CollectModelService, "delete_butch_node_params") as delete:
        with patch.object(CollectModelService, "push_butch_node_params", side_effect=[RuntimeError("push-secret"), None],) as push:
            first = _reconcile(config)
            pending_state = _state(config)
            second = _reconcile(config)

    assert first.node_config_status == "degraded"
    assert pending_state.node_config_status == "push_pending"
    assert pending_state.reason_code == "NODE_CONFIG_PUSH_FAILED"
    assert "push-secret" not in pending_state.error_message
    delete.assert_called_once_with(region_task)
    assert push.call_count == 2
    assert second.node_config_status == "healthy"
    assert _state(config).node_config_status == "healthy"


def test_concurrent_degraded_recovery_claims_region_side_effect_once(config, region_task):
    state = NodeMgmtSyncRegionState.objects.create(
        config=config,
        config_version=config.version,
        cloud_region_id="7",
        collect_task=region_task,
        scope_key=f"config:{config.version}:region:7",
        node_config_status="delete_pending",
    )
    config.node_config_status = "degraded"
    config.save(update_fields=["node_config_status", "updated_at"])
    calls = []

    def delete(task):
        calls.append(task.pk)
        if len(calls) == 1:
            _reconcile(NodeMgmtSyncConfig.objects.get(pk=config.pk))

    with patch.object(CollectModelService, "delete_butch_node_params", side_effect=delete):
        with patch.object(CollectModelService, "push_butch_node_params") as push:
            _reconcile(config)

    assert calls == [region_task.pk]
    push.assert_called_once_with(region_task)
    state.refresh_from_db()
    assert state.node_config_status == "healthy"


def test_stale_node_config_claim_can_be_recovered(config, region_task):
    state = NodeMgmtSyncRegionState.objects.create(
        config=config,
        config_version=config.version,
        cloud_region_id="7",
        collect_task=region_task,
        scope_key=f"config:{config.version}:region:7",
        node_config_status="delete_in_progress",
        reason_code="NODE_CONFIG_CLAIM:stale-token",
    )
    NodeMgmtSyncRegionState.objects.filter(pk=state.pk).update(updated_at=timezone.now() - timedelta(minutes=6))

    with patch.object(CollectModelService, "delete_butch_node_params") as delete:
        with patch.object(CollectModelService, "push_butch_node_params") as push:
            result = _reconcile(config)

    assert result.node_config_status == "healthy"
    delete.assert_called_once_with(region_task)
    push.assert_called_once_with(region_task)
    assert _state(config).node_config_status == "healthy"


def test_old_node_config_claim_cannot_overwrite_new_claim(config, region_task):
    state = NodeMgmtSyncRegionState.objects.create(
        config=config,
        config_version=config.version,
        cloud_region_id="7",
        collect_task=region_task,
        scope_key=f"config:{config.version}:region:7",
        node_config_status="delete_pending",
    )

    def replace_claim(_task):
        NodeMgmtSyncRegionState.objects.filter(pk=state.pk).update(
            node_config_status="delete_in_progress", reason_code="NODE_CONFIG_CLAIM:new-worker",
        )

    with patch.object(CollectModelService, "delete_butch_node_params", side_effect=replace_claim):
        with patch.object(CollectModelService, "push_butch_node_params") as push:
            result = _reconcile(config)

    state.refresh_from_db()
    assert result.node_config_status == "degraded"
    push.assert_not_called()
    assert state.node_config_status == "delete_in_progress"
    assert state.reason_code == "NODE_CONFIG_CLAIM:new-worker"


def test_collect_enabled_without_sync_waits_and_does_not_dispatch(config, region_task):
    config.auto_sync_enabled = False
    config.save(update_fields=["auto_sync_enabled", "updated_at"])

    with patch.object(CollectModelService, "delete_butch_node_params") as delete:
        with patch.object(CollectModelService, "push_butch_node_params") as push:
            result = _reconcile(config)

    assert result.node_config_status == "waiting_sync"
    delete.assert_not_called()
    push.assert_not_called()
    config.refresh_from_db()
    assert config.node_config_status == "waiting_sync"
    assert NodeMgmtSyncRegionState.objects.count() == 0


def test_no_region_task_reports_unknown_instead_of_healthy(config):
    result = _reconcile(config)

    config.refresh_from_db()
    assert result.node_config_status == "unknown"
    assert config.node_config_status == "unknown"
    assert NodeMgmtSyncRegionState.objects.count() == 0


def test_invalid_region_system_code_degrades_without_guessing_or_leaking(config, caplog):
    _create_region_task("invalid", system_code=f"{NodeMgmtSyncService.SYSTEM_TASK_PREFIX}bad-id")

    with patch.object(CollectModelService, "delete_butch_node_params") as delete:
        with patch.object(CollectModelService, "push_butch_node_params") as push:
            result = _reconcile(config)

    assert result.node_config_status == "degraded"
    assert result.error_code == "NODE_CONFIG_RECONCILE_FAILED"
    assert "bad-id" not in result.error_message
    assert "bad-id" not in caplog.text
    delete.assert_not_called()
    push.assert_not_called()
    assert NodeMgmtSyncRegionState.objects.count() == 0


def test_one_region_failure_degrades_aggregate_but_keeps_other_region_healthy(config, region_task):
    other_task = _create_region_task(8)

    def push(task):
        if task.pk == other_task.pk:
            raise TimeoutError("credential-secret")

    with patch.object(CollectModelService, "delete_butch_node_params"):
        with patch.object(CollectModelService, "push_butch_node_params", side_effect=push):
            result = _reconcile(config)

    assert result.node_config_status == "degraded"
    assert _state(config, 7).node_config_status == "healthy"
    failed = _state(config, 8)
    assert failed.node_config_status == "push_pending"
    assert "credential-secret" not in failed.error_message


def test_stale_config_version_cannot_overwrite_current_health(config, region_task):
    stale_config = NodeMgmtSyncConfig.objects.get(pk=config.pk)
    NodeMgmtSyncConfig.objects.filter(pk=config.pk).update(
        version=config.version + 1, node_config_status="waiting_sync",
    )

    with patch.object(CollectModelService, "delete_butch_node_params"):
        with patch.object(CollectModelService, "push_butch_node_params"):
            _reconcile(stale_config)

    config.refresh_from_db()
    assert config.version == stale_config.version + 1
    assert config.node_config_status == "waiting_sync"
    assert _state(stale_config).node_config_status == "healthy"


def test_collect_service_logs_do_not_include_node_payload_or_rpc_result(region_task):
    node = SimpleNamespace(main=lambda **kwargs: {"credential": "node-secret"})
    client = SimpleNamespace(
        batch_add_node_child_config=lambda payload: {"raw": "push-secret"}, delete_child_configs=lambda payload: {"raw": "delete-secret"},
    )
    with patch(
        "apps.cmdb.services.collect_service.NodeParamsFactory.get_node_params", return_value=node,
    ):
        with patch("apps.cmdb.services.collect_service.NodeMgmt", return_value=client):
            with patch("apps.cmdb.services.collect_service.logger.debug") as debug:
                CollectModelService.push_butch_node_params(region_task)
                CollectModelService.delete_butch_node_params(region_task)

    rendered = " ".join(str(value) for call in debug.call_args_list for value in call.args)
    assert "node-secret" not in rendered
    assert "push-secret" not in rendered
    assert "delete-secret" not in rendered
