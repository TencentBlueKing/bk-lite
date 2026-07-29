from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, local
from unittest.mock import Mock, patch

import pytest
from django.db import IntegrityError, OperationalError, close_old_connections, connections

from apps.alerts.models import IncidentIMGroup
from apps.base.models import User as AuthUser

pytestmark = [pytest.mark.integration, pytest.mark.django_db]
pytest_plugins = ["apps.alerts.tests.incident_im_group_fixtures"]


@pytest.mark.django_db(transaction=True)
def test_sqlite_independent_connections_translate_busy_loser_after_active_winner(operator, incident, channel, operator_mapping, monkeypatch):
    database_vendor = connections["default"].vendor
    if database_vendor != "sqlite":
        pytest.skip(f"SQLite 锁竞争合同不适用于 {database_vendor}")

    from apps.alerts.service.incident_im import groups

    barrier = Barrier(2)
    worker_state = local()
    original_resolve = groups.resolve_incident_members

    def synchronized_resolve(*args, **kwargs):
        if not getattr(worker_state, "synchronized", False):
            worker_state.synchronized = True
            barrier.wait(timeout=10)
        return original_resolve(*args, **kwargs)

    monkeypatch.setattr(groups, "resolve_incident_members", synchronized_resolve)

    def create_from_independent_connection():
        close_old_connections()
        try:
            actor = AuthUser.objects.get(pk=operator.pk)
            group = groups.IncidentIMGroupService.create(
                incident_id=incident.id,
                actor=actor,
                channel_id=channel.id,
                group_name="并发测试群",
                owner_username="operator",
                continuous_sync_enabled=True,
            )
            return ("created", str(group.id), "")
        except Exception as exc:
            return (type(exc).__name__, getattr(exc, "code", ""), str(exc))
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = [future.result(timeout=20) for future in [executor.submit(create_from_independent_connection) for _ in range(2)]]

    assert sorted(outcome[0] for outcome in outcomes) == ["IncidentIMError", "created",], outcomes
    assert {outcome[1] for outcome in outcomes if outcome[0] == "IncidentIMError"} == {"IM_GROUP_ACTIVE_EXISTS"}
    assert IncidentIMGroup.objects.filter(incident=incident, active_slot=1).count() == 1


@pytest.mark.django_db
def test_sqlite_lock_retries_entire_create_transaction_after_no_winner(monkeypatch):
    from apps.alerts.service.incident_im import groups

    created_group = Mock()
    lock_error = OperationalError("database is locked")
    monkeypatch.setattr(groups.IncidentIMGroupService, "_is_sqlite_lock_error", lambda exc: True)
    monkeypatch.setattr(groups.IncidentIMGroupService, "_has_active_group", lambda incident_id: False)

    with patch.object(groups.IncidentIMGroupService, "_create_once", side_effect=[lock_error, created_group],) as create_once, patch(
        "apps.alerts.service.incident_im.groups.sleep"
    ) as sleep_mock:
        result = groups.IncidentIMGroupService.create(
            incident_id=1, actor=Mock(), channel_id=1, group_name="重试测试群", owner_username="operator", continuous_sync_enabled=True,
        )

    assert result is created_group
    assert create_once.call_count == 2
    sleep_mock.assert_called_once_with(groups.IncidentIMGroupService.SQLITE_LOCK_RETRY_DELAYS[0])


@pytest.mark.django_db
def test_sqlite_lock_reraises_last_error_after_retry_budget_exhausted(monkeypatch):
    from apps.alerts.service.incident_im import groups

    lock_errors = [OperationalError("database is locked") for _ in range(len(groups.IncidentIMGroupService.SQLITE_LOCK_RETRY_DELAYS) + 1)]
    monkeypatch.setattr(groups.IncidentIMGroupService, "_is_sqlite_lock_error", lambda exc: True)
    monkeypatch.setattr(groups.IncidentIMGroupService, "_has_active_group", lambda incident_id: False)

    with patch.object(groups.IncidentIMGroupService, "_create_once", side_effect=lock_errors) as create_once:
        with pytest.raises(OperationalError) as raised:
            groups.IncidentIMGroupService.create(
                incident_id=1, actor=Mock(), channel_id=1, group_name="重试耗尽测试群", owner_username="operator", continuous_sync_enabled=True,
            )

    assert raised.value is lock_errors[-1]
    assert create_once.call_count == len(lock_errors)


@pytest.mark.django_db
def test_non_sqlite_lock_operational_error_is_reraised_without_retry(monkeypatch):
    from apps.alerts.service.incident_im import groups

    lock_error = OperationalError("database is locked")
    monkeypatch.setattr(groups.connection, "vendor", "postgresql")

    with patch.object(groups.IncidentIMGroupService, "_create_once", side_effect=lock_error) as create_once:
        with pytest.raises(OperationalError) as raised:
            groups.IncidentIMGroupService.create(
                incident_id=1, actor=Mock(), channel_id=1, group_name="非 SQLite 测试群", owner_username="operator", continuous_sync_enabled=True,
            )

    assert raised.value is lock_error
    assert create_once.call_count == 1


@pytest.mark.django_db
@pytest.mark.parametrize("failure_target", ["bulk_create", "enqueue_outbox"])
def test_non_group_integrity_error_is_not_translated_to_active_conflict(operator, incident, channel, operator_mapping, failure_target):
    from apps.alerts.service.incident_im import groups

    target = (
        "apps.alerts.models.IncidentIMMember.objects.bulk_create"
        if failure_target == "bulk_create"
        else "apps.alerts.service.incident_im.groups.enqueue_outbox"
    )
    with patch(target, side_effect=IntegrityError("unrelated constraint")):
        with pytest.raises(IntegrityError):
            groups.IncidentIMGroupService.create(
                incident_id=incident.id,
                actor=operator,
                channel_id=channel.id,
                group_name="约束异常测试群",
                owner_username="operator",
                continuous_sync_enabled=True,
            )

    assert not IncidentIMGroup.objects.filter(incident=incident, active_slot=1).exists()
