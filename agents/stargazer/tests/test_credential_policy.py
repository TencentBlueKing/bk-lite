import pytest

from core.collection_runtime import CollectionRequest
from core.credential_policy import CredentialPolicy, InMemoryCredentialStateStore


@pytest.mark.asyncio
async def test_auth_failed_credential_is_cooled_and_successful_credential_gets_affinity():
    store = InMemoryCredentialStateStore()
    policy = CredentialPolicy(store=store, jitter=lambda _start, _end: 0)
    request = CollectionRequest(
        task_id="collect-credential-policy",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
        credentials=(
            {"credential_id": "credential-1", "username": "root"},
            {"credential_id": "credential-2", "username": "readonly"},
            {"credential_id": "credential-3", "username": "backup"},
        ),
        params={
            "scope_id": "tenant-a",
            "credential_set_version": "v1",
        },
    )

    await policy.record_auth_failure(
        request,
        "10.10.24.1",
        request.credentials[0],
        error_code="unauthorized",
    )
    await policy.record_success(
        request,
        "10.10.24.1",
        request.credentials[1],
    )

    eligible = await policy.eligible_credentials(request, "10.10.24.1")

    assert [item["credential_id"] for item in eligible] == [
        "credential-2",
        "credential-1",
        "credential-3",
    ]


@pytest.mark.asyncio
async def test_all_cooled_credentials_expose_nearest_retry_time():
    now = 1_000.0
    store = InMemoryCredentialStateStore()
    policy = CredentialPolicy(
        store=store,
        now=lambda: now,
        jitter=lambda _start, _end: 0,
    )
    request = CollectionRequest(
        task_id="all-cooled",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
        credentials=(
            {"credential_id": "credential-1"},
            {"credential_id": "credential-2"},
        ),
    )
    for credential in request.credentials:
        await policy.record_auth_failure(
            request,
            "10.10.24.1",
            credential,
            error_code="unauthorized",
        )

    assert await policy.eligible_credentials(request, "10.10.24.1") == ()
    assert await policy.next_retry_at(request, "10.10.24.1") == 4_600.0
