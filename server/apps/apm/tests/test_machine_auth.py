import pytest
from django.db import OperationalError

from apps.apm.services import DjangoIngestSourceService


pytestmark = pytest.mark.django_db


def _create_source():
    return DjangoIngestSourceService().create(
        name="edge-source",
        ingest_type="otlp_http",
        organization_ids=[10],
        actor="tester",
    )


def test_machine_auth_returns_only_trusted_source_header(client):
    created = _create_source()

    response = client.get(
        "/api/v1/apm/machine-auth/",
        HTTP_AUTHORIZATION=f"Bearer {created.credential}",
        HTTP_X_BK_INGEST_SOURCE_ID="forged",
    )

    assert response.status_code == 204
    assert response.headers["X-BK-Ingest-Source-Id"] == str(created.source.id)
    assert response.headers["Cache-Control"] == "private, max-age=10"
    assert response.content == b""


@pytest.mark.parametrize("authorization", [None, "", "Basic bad", "Bearer bad"])
def test_machine_auth_rejects_missing_or_invalid_bearer(client, authorization):
    headers = {"HTTP_AUTHORIZATION": authorization} if authorization is not None else {}

    response = client.get("/api/v1/apm/machine-auth/", **headers)

    assert response.status_code == 401


def test_machine_auth_revocation_is_immediate_at_control_plane(client):
    service = DjangoIngestSourceService()
    created = _create_source()
    service.disable(created.source.id, actor="tester")

    response = client.get(
        "/api/v1/apm/machine-auth/",
        HTTP_AUTHORIZATION=f"Bearer {created.credential}",
    )

    assert response.status_code == 401


def test_machine_auth_old_credential_fails_after_rotation(client):
    service = DjangoIngestSourceService()
    created = _create_source()
    rotated = service.rotate(created.source.id, actor="tester")

    old_response = client.get(
        "/api/v1/apm/machine-auth/",
        HTTP_AUTHORIZATION=f"Bearer {created.credential}",
    )
    new_response = client.get(
        "/api/v1/apm/machine-auth/",
        HTTP_AUTHORIZATION=f"Bearer {rotated.credential}",
    )

    assert old_response.status_code == 401
    assert new_response.status_code == 204


def test_machine_auth_returns_503_when_database_is_unavailable(client, mocker):
    mocker.patch(
        "apps.apm.views.machine_auth.DjangoIngestSourceService.validate_credential",
        side_effect=OperationalError("database unavailable"),
    )

    response = client.get(
        "/api/v1/apm/machine-auth/",
        HTTP_AUTHORIZATION="Bearer uncached-token",
    )

    assert response.status_code == 503
