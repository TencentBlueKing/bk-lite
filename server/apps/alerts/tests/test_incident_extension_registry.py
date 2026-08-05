import uuid
from types import SimpleNamespace
from unittest import mock

import pytest

from apps.alerts.constants.constants import IncidentStatus
from apps.alerts.extensions.incident import incident_extensions
from apps.alerts.models import Incident
from apps.alerts.serializers.incident import IncidentModelSerializer
from apps.alerts.service.incident_operator import IncidentOperator


@pytest.fixture(autouse=True)
def preserve_incident_extension_registry():
    original_handlers = dict(incident_extensions._handlers)
    try:
        yield
    finally:
        incident_extensions.clear()
        incident_extensions._handlers.update(original_handlers)


def test_incident_extension_is_a_safe_noop_without_enterprise_handlers():
    incident_extensions.clear()

    assert incident_extensions.participants_changed(incident_id=101) == []
    assert incident_extensions.incident_closed(incident_id=101) == []
    assert incident_extensions.incident_reopened(incident_id=101) == []


def test_incident_extension_dispatches_registered_handler_by_public_interface():
    calls = []

    class EnterpriseIncidentHandler:
        def participants_changed(self, incident_id):
            calls.append(("participants_changed", incident_id))
            return "participants"

        def incident_closed(self, incident_id):
            calls.append(("incident_closed", incident_id))
            return "closed"

        def incident_reopened(self, incident_id):
            calls.append(("incident_reopened", incident_id))
            return "reopened"

    incident_extensions.clear()
    incident_extensions.register("incident-im-group", EnterpriseIncidentHandler())

    assert incident_extensions.participants_changed(101) == ["participants"]
    assert incident_extensions.incident_closed(101) == ["closed"]
    assert incident_extensions.incident_reopened(101) == ["reopened"]
    assert calls == [
        ("participants_changed", 101),
        ("incident_closed", 101),
        ("incident_reopened", 101),
    ]


def test_incident_extension_isolates_handler_failure_and_continues_dispatch(caplog):
    class BrokenHandler:
        def participants_changed(self, incident_id):
            raise RuntimeError("enterprise handler failed")

    class HealthyHandler:
        def participants_changed(self, incident_id):
            return f"handled-{incident_id}"

    incident_extensions.clear()
    incident_extensions.register("broken", BrokenHandler())
    incident_extensions.register("healthy", HealthyHandler())

    assert incident_extensions.participants_changed(101) == ["handled-101"]
    assert "incident extension handler failed" in caplog.text


@pytest.mark.django_db
def test_incident_member_change_publishes_after_commit(
    django_capture_on_commit_callbacks,
):
    calls = []

    class EnterpriseIncidentHandler:
        def participants_changed(self, incident_id):
            calls.append(incident_id)

    incident_extensions.clear()
    incident_extensions.register("incident-im-group", EnterpriseIncidentHandler())
    incident = Incident.objects.create(
        incident_id=f"INC-{uuid.uuid4().hex}",
        level="warning",
        title="扩展事件测试",
        status=IncidentStatus.PROCESSING,
        operator=["alice"],
        collaborators=[],
    )
    request = SimpleNamespace(user=SimpleNamespace(group_list=[]), COOKIES={})
    with mock.patch(
        "apps.core.utils.serializers.get_permission_rules",
        return_value={"team": [], "instance": []},
    ):
        serializer = IncidentModelSerializer(
            incident,
            data={"collaborators": ["bob"]},
            partial=True,
            context={"request": request},
        )
        assert serializer.is_valid(), serializer.errors
        with django_capture_on_commit_callbacks(execute=True):
            serializer.save()

    assert calls == [incident.pk]


@pytest.mark.django_db
def test_incident_close_and_reopen_publish_after_commit(
    django_capture_on_commit_callbacks,
):
    calls = []

    class EnterpriseIncidentHandler:
        def incident_closed(self, incident_id):
            calls.append(("closed", incident_id))

        def incident_reopened(self, incident_id):
            calls.append(("reopened", incident_id))

    incident_extensions.clear()
    incident_extensions.register("incident-im-group", EnterpriseIncidentHandler())
    incident = Incident.objects.create(
        incident_id=f"INC-{uuid.uuid4().hex}",
        level="warning",
        title="生命周期扩展事件测试",
        status=IncidentStatus.PROCESSING,
        operator=["alice"],
    )
    operator = IncidentOperator(user="alice")

    with django_capture_on_commit_callbacks(execute=True):
        assert operator.operate("close", incident.incident_id, {})["result"] is True
    with django_capture_on_commit_callbacks(execute=True):
        assert operator.operate("reopen", incident.incident_id, {})["result"] is True

    assert calls == [
        ("closed", incident.pk),
        ("reopened", incident.pk),
    ]
