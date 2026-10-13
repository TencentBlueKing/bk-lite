import json

import pytest

pytestmark = pytest.mark.django_db
from django.db import transaction

from apps.rum.constants import MAX_ORIGINS
from apps.rum.services.applications import ApplicationsService
from apps.rum.services.compliance import ComplianceService, MemoryEraseJobStore
from apps.rum.services.control import ControlError, MemoryControl
from apps.rum.services.projection import PublishService
from apps.rum.services.settings import RumRuntimeSettings
from apps.rum.services.validation import ValidationError
from apps.rum.tasks import publish_pending_rum_outbox


def _settings() -> RumRuntimeSettings:
    return RumRuntimeSettings(
        collect_url="https://telemetry.example.test/rum/v1/collect",
        replay_url="https://telemetry.example.test/rum/v1/replay",
        sdk_cdn_url="https://cdn.example.test/rum/bklite-rum-sdk.js",
        nats_url="",
        nats_timeout_seconds=5,
        tenant_id="core",
        victoria_logs_url="",
        victoria_traces_url="",
        victoria_account_id=0,
        victoria_project_id=0,
        victoria_timeout_seconds=15,
    )


class _Down(MemoryControl):
    def request(self, subject, actor, payload=None, expected_revision=None):
        raise ControlError("unavailable", "rum-projection-payload-sentinel-9f3c")


def test_transaction_rollback_leaves_no_outbox():
    from apps.rum.models import RumApplication, RumProjectionOutbox

    service = ApplicationsService(MemoryControl(), _settings())
    with pytest.raises(RuntimeError):
        with transaction.atomic():
            service.create_application(
                "tester",
                {"application": "checkout", "origins": ["https://shop.example.test"]},
            )
            raise RuntimeError("boom")
    assert RumApplication.objects.count() == 0
    assert RumProjectionOutbox.objects.count() == 0


def test_publish_failure_keeps_outbox_pending_and_logs_type_only(caplog):
    from apps.rum.models import RumProjectionOutbox

    service = ApplicationsService(_Down(), _settings())
    with caplog.at_level("WARNING", logger="rum"):
        revision, created = service.create_application(
            "tester",
            {"application": "checkout", "origins": ["https://shop.example.test"]},
        )
    assert revision == 1
    assert created["projectionPending"] is True
    assert created["browserKeys"]
    row = RumProjectionOutbox.objects.get(application="checkout", kind="application")
    assert row.status == "pending"
    assert row.attempts == 1
    assert row.last_error_type == "ControlError"
    record = next(item for item in caplog.records if item.name == "rum")
    assert record.msg == "rum projection publish failed outbox_id=%s failed_stage=%s error_type=%s"
    assert record.args[1:] == ("publish", "ControlError")
    assert "rum-projection-payload-sentinel-9f3c" not in caplog.text
    rendered = record.getMessage()
    assert "failed_stage=publish" in rendered
    assert "error_type=ControlError" in rendered


def test_republish_pending_outbox_is_idempotent(monkeypatch):
    from apps.rum.models import RumProjectionOutbox

    down = ApplicationsService(_Down(), _settings())
    _, created = down.create_application(
        "tester",
        {"application": "checkout", "origins": ["https://shop.example.test"]},
    )
    assert created["projectionPending"] is True
    control = MemoryControl()
    monkeypatch.setattr("apps.rum.tasks.PublishService", lambda: PublishService(control))
    first = publish_pending_rum_outbox()
    row = RumProjectionOutbox.objects.get(application="checkout")
    assert first["published"] == 1
    assert row.status == "published"
    attempts = row.attempts
    PublishService(control).publish(row.id)
    row.refresh_from_db()
    assert row.attempts == attempts
    assert row.status == "published"
    assert control._apps["checkout"]["revision"] == 1
    listed = json.dumps(down.list_applications("tester"), ensure_ascii=False)
    assert created["browserKeys"][0] not in listed


def test_browser_key_is_encrypted_and_hidden_from_list():
    from apps.rum.models import RumApplicationKey

    service = ApplicationsService(MemoryControl(), _settings())
    _, created = service.create_application(
        "tester",
        {"application": "checkout", "origins": ["https://shop.example.test"]},
    )
    plain = created["browserKeys"][0]
    stored = RumApplicationKey.objects.get(application="checkout")
    assert stored.key_cipher != plain
    assert plain not in stored.key_cipher
    assert plain not in json.dumps(service.list_applications("tester"), ensure_ascii=False)
    assert service.get_application("tester", "checkout")["browserKeys"] == [plain]


def test_active_key_and_origin_limits_are_rejected():
    service = ApplicationsService(MemoryControl(), _settings())
    service.create_application("tester", {"application": "checkout", "origins": ["https://shop.example.test"]})
    service.reissue_key("tester", "checkout")
    with pytest.raises(ValidationError, match="retire one before issuing another"):
        service.reissue_key("tester", "checkout")
    origins = [f"https://shop{index}.example.test" for index in range(MAX_ORIGINS + 1)]
    with pytest.raises(ValidationError):
        service.create_application("tester", {"application": "catalog", "origins": origins})


def test_reconcile_republishes_apps_missing_from_the_projection():
    control = MemoryControl()
    service = ApplicationsService(control, _settings())
    service.create_application("tester", {"application": "checkout", "origins": ["https://shop.example.test"]})
    del control._apps["checkout"]
    PublishService(control).reconcile()
    assert control._apps["checkout"]["revision"] == 1


def test_reconcile_overwrites_projection_ahead_of_the_database():
    control = MemoryControl()
    service = ApplicationsService(control, _settings())
    service.create_application("tester", {"application": "checkout", "origins": ["https://shop.example.test"]})
    control._apps["checkout"]["revision"] = 9
    PublishService(control).reconcile()
    assert control._apps["checkout"]["revision"] == 1
    assert control._apps["checkout"]["status"] == "applied"


def test_fence_outbox_follows_erase_job_status():
    from apps.rum.models import RumProjectionOutbox

    control = MemoryControl()
    service = ApplicationsService(control, _settings())
    service.create_application("tester", {"application": "checkout", "origins": ["https://shop.example.test"]})
    compliance = ComplianceService(control=control, store=MemoryEraseJobStore())
    _, data = compliance.erase("tester", {"application": "checkout", "endUserId": "user-123"})
    added = RumProjectionOutbox.objects.get(kind="fence_add", application="checkout")
    assert added.status == "published"
    assert added.payload_json["identities"] == [{"kind": "user", "value": "user-123"}]
    control._operations[data["operationId"]]["status"] = "completed"
    jobs = compliance.list_jobs({}, actor="tester")
    assert jobs[0]["status"] == "completed"
    released = RumProjectionOutbox.objects.get(kind="fence_release", application="checkout")
    assert released.status == "published"
    assert released.payload_json["identities"] == [{"kind": "user", "value": "user-123"}]
