import io

import pytest
from django.contrib.auth.hashers import check_password
from django.core.management import call_command
from django.urls import reverse

from apps.log.models import SystemVectorConfigState, SystemVectorToken


@pytest.mark.integration
@pytest.mark.django_db
def test_config_open_api_requires_deployment_token(client):
    SystemVectorConfigState.objects.create(
        desired_generation=1,
        published_generation=1,
        status=SystemVectorConfigState.Status.PUBLISHED,
        published_content="sources: {}\n",
        published_checksum="sha256:abc",
    )

    response = client.get(reverse("log-system-vector-config"))

    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Bearer"

    wrong = client.get(reverse("log-system-vector-config"), HTTP_AUTHORIZATION="Bearer wrong-token")
    assert wrong.status_code == 401
    assert wrong["WWW-Authenticate"] == "Bearer"


@pytest.mark.integration
@pytest.mark.django_db
def test_config_open_api_returns_exact_snapshot_and_headers(client, mocker):
    token = "deployment-token"
    from django.contrib.auth.hashers import make_password

    SystemVectorToken.objects.create(token_digest=make_password(token))
    SystemVectorConfigState.objects.create(
        desired_generation=2,
        published_generation=1,
        status=SystemVectorConfigState.Status.FAILED,
        published_content="sources:\n  nats: {}\n",
        published_checksum="sha256:abc",
    )
    compiler = mocker.patch("apps.log.services.log_extractor.compiler.compile_system_vector_config")

    response = client.get(reverse("log-system-vector-config"), HTTP_AUTHORIZATION=f"Bearer {token}")

    assert response.status_code == 200
    assert response.content == b"sources:\n  nats: {}\n"
    assert response["Content-Type"] == "application/yaml; charset=utf-8"
    assert response["X-Config-Checksum"] == "sha256:abc"
    assert response["X-Config-Generation"] == "1"
    assert response["Cache-Control"] == "no-store"
    assert "ETag" not in response
    compiler.assert_not_called()


@pytest.mark.integration
@pytest.mark.django_db
def test_config_open_api_returns_503_without_snapshot(client):
    from django.contrib.auth.hashers import make_password

    SystemVectorToken.objects.create(token_digest=make_password("token"))

    response = client.get(reverse("log-system-vector-config"), HTTP_AUTHORIZATION="Bearer token")

    assert response.status_code == 503


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_management_command_rotates_digest_and_never_stores_plaintext(mocker):
    mocker.patch("apps.log.management.commands.system_vector_token.ensure_initial_snapshot")
    first_output = io.StringIO()
    call_command("system_vector_token", stdout=first_output)
    first_token = first_output.getvalue().split("token=", 1)[1].splitlines()[0]
    first_digest = SystemVectorToken.objects.get().token_digest

    second_output = io.StringIO()
    call_command("system_vector_token", stdout=second_output)
    second_token = second_output.getvalue().split("token=", 1)[1].splitlines()[0]
    second_digest = SystemVectorToken.objects.get().token_digest

    assert first_token != second_token
    assert first_token not in first_digest
    assert second_token not in second_digest
    assert not check_password(first_token, second_digest)
    assert check_password(second_token, second_digest)
