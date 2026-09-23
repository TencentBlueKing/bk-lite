from apps.rum.constants import SUBJECT_ERASURE_SUBMIT
from apps.rum.services.applications import ApplicationsService
from apps.rum.services.compliance import ComplianceService, MemoryEraseJobStore
from apps.rum.services.control import MemoryControl, UnavailableControl
from apps.rum.services.settings import RumRuntimeSettings
from apps.rum.services.validation import ValidationError


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


def _seed_app(control: MemoryControl) -> None:
    ApplicationsService(control, _settings()).create_application(
        "tester",
        {"application": "checkout", "origins": ["https://shop.example.test"]},
    )


def test_erase_submits_user_identity_and_writes_ledger():
    control = MemoryControl()
    _seed_app(control)
    store = MemoryEraseJobStore()
    service = ComplianceService(control=control, store=store)
    app_revision = int(control._apps["checkout"]["revision"])

    calls: list[tuple[str, int | None]] = []
    original = control.request

    def spy(subject, actor, payload=None, expected_revision=None):
        calls.append((subject, expected_revision))
        return original(subject, actor, payload, expected_revision)

    control.request = spy  # type: ignore[method-assign]

    revision, data = service.erase(
        "tester",
        {"application": "checkout", "endUserId": "user-123"},
    )
    assert revision >= 0
    assert data["type"] == "erasure"
    assert data["status"] == "accepted"
    assert data["application"] == "checkout"
    assert data["identities"] == [{"kind": "user", "value": "user-123"}]
    assert data["ledger"]["endUserId"] == "user-123"
    assert data["ledger"]["status"] == "accepted"
    assert data["ledger"]["scope"] == "all"
    assert (SUBJECT_ERASURE_SUBMIT, app_revision) in calls

    jobs = service.list_jobs({"application": "checkout"})
    assert len(jobs) == 1
    assert jobs[0]["endUserId"] == "user-123"


def _submit(service: ComplianceService) -> dict:
    _, data = service.erase("tester", {"application": "checkout", "endUserId": "user-123"})
    return data


def test_list_refreshes_in_flight_ledger_status_from_controller():
    control = MemoryControl()
    _seed_app(control)
    store = MemoryEraseJobStore()
    service = ComplianceService(control=control, store=store)
    data = _submit(service)
    operation_id = data["operationId"]

    # Maintainer finished the erasure on the controller side.
    control._operations[operation_id]["status"] = "completed"

    jobs = service.list_jobs({"application": "checkout"}, actor="tester")
    assert jobs[0]["status"] == "completed"
    assert jobs[0]["result"]["operationId"] == operation_id
    # Persisted, not just decorated on the way out.
    assert store.list()[0]["status"] == "completed"


def test_list_stops_polling_terminal_jobs():
    control = MemoryControl()
    _seed_app(control)
    store = MemoryEraseJobStore()
    service = ComplianceService(control=control, store=store)
    data = _submit(service)
    control._operations[data["operationId"]]["status"] = "failed"
    service.list_jobs({}, actor="tester")

    calls = []
    original = control.request

    def spy(subject, actor, payload=None, expected_revision=None):
        calls.append(subject)
        return original(subject, actor, payload, expected_revision)

    control.request = spy  # type: ignore[method-assign]
    jobs = service.list_jobs({}, actor="tester")
    assert jobs[0]["status"] == "failed"
    assert "rum.v1.control.operation.get" not in calls


def test_list_keeps_stored_status_when_controller_unavailable():
    control = MemoryControl()
    _seed_app(control)
    store = MemoryEraseJobStore()
    ComplianceService(control=control, store=store).erase("tester", {"application": "checkout", "endUserId": "user-123"})
    offline = ComplianceService(control=UnavailableControl(), store=store)
    jobs = offline.list_jobs({}, actor="tester")
    assert jobs[0]["status"] == "accepted"


def test_list_marks_job_failed_when_controller_forgot_operation():
    control = MemoryControl()
    _seed_app(control)
    store = MemoryEraseJobStore()
    service = ComplianceService(control=control, store=store)
    data = _submit(service)
    del control._operations[data["operationId"]]
    jobs = service.list_jobs({}, actor="tester")
    assert jobs[0]["status"] == "failed"
    assert jobs[0]["result"]["error"] == "operation not found"


def test_list_rejects_non_numeric_limit():
    service = ComplianceService(control=MemoryControl(), store=MemoryEraseJobStore())
    try:
        service.list_jobs({"limit": "many"})
        assert False
    except ValidationError:
        pass


def test_erase_requires_fields():
    service = ComplianceService(control=MemoryControl(), store=MemoryEraseJobStore())
    try:
        service.erase("tester", {"application": "checkout"})
        assert False
    except ValidationError:
        pass


def test_erase_control_unavailable():
    service = ComplianceService(control=UnavailableControl(), store=MemoryEraseJobStore())
    try:
        service.erase("tester", {"application": "checkout", "endUserId": "u1"})
        assert False
    except Exception as exc:
        assert getattr(exc, "code", "") == "unavailable"


def test_erasure_subject_constant():
    assert SUBJECT_ERASURE_SUBMIT == "rum.v1.control.erasure.submit"
