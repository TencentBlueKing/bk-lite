import pytest
from core.collection.credential_policy import CredentialPolicy, CredentialScope, InMemoryCredentialStateStore
from core.collection.runtime import CollectionRequest


@pytest.mark.asyncio
async def test_success_clears_only_current_credential_failure_and_keeps_others_cooled():
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
        "credential-3",
    ]


@pytest.mark.asyncio
async def test_versioned_success_credential_is_prioritized_next_round():
    store = InMemoryCredentialStateStore()
    policy = CredentialPolicy(store=store)
    request = CollectionRequest(
        task_id="versioned-affinity",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
        credentials=(
            {"credential_id": "credential-1", "credential_version": 1},
            {"credential_id": "credential-2", "credential_version": 3},
        ),
    )

    await policy.record_success(request, "10.10.24.1", request.credentials[1])

    eligible = await policy.eligible_credentials(request, "10.10.24.1")
    assert [(item["credential_id"], item["credential_version"]) for item in eligible] == [
        ("credential-2", 3),
        ("credential-1", 1),
    ]


@pytest.mark.asyncio
async def test_auth_failure_uses_s1_cooldown_gradient():
    now = 1_000.0
    store = InMemoryCredentialStateStore()
    policy = CredentialPolicy(
        store=store,
        now=lambda: now,
        jitter=lambda _start, _end: 0,
    )
    request = CollectionRequest(
        task_id="s1-cooldown",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
        credentials=({"credential_id": "credential-1"},),
    )
    credential = request.credentials[0]

    scope = CredentialScope(
        scope_id="default",
        plugin_ref="mysql.config",
        target_id="10.10.24.1",
        credential_set_version="default",
    )
    expected = (
        (1, 5 * 60),
        (2, 30 * 60),
        (3, 4 * 3600),
        (4, 24 * 3600),
    )
    for level, cooldown in expected:
        await policy.record_auth_failure(request, "10.10.24.1", credential, error_code="unauthorized")
        failure = await store.get_failure(scope, "credential-1")
        assert failure is not None
        assert failure.cooldown_level == level
        assert failure.next_retry_at == 1_000.0 + cooldown


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
    assert await policy.next_retry_at(request, "10.10.24.1") == 1_000.0 + 5 * 60


@pytest.mark.asyncio
async def test_cooled_credential_skip_is_logged(monkeypatch):
    logged = []

    def capture(message, *args):
        logged.append(message % args if args else message)

    monkeypatch.setattr("core.collection.credential_policy.logger.debug", capture)
    now = 1_000.0
    store = InMemoryCredentialStateStore()
    policy = CredentialPolicy(
        store=store,
        now=lambda: now,
        jitter=lambda _start, _end: 0,
    )
    request = CollectionRequest(
        task_id="cooldown-skip-log",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
        credentials=({"credential_id": "credential-1"},),
    )
    await policy.record_auth_failure(
        request,
        "10.10.24.1",
        request.credentials[0],
        error_code="unauthorized",
    )

    assert await policy.eligible_credentials(request, "10.10.24.1") == ()
    assert any("event=credential_cooldown_skipped" in item for item in logged)
    assert any("credential_id=credential-1" in item for item in logged)
    assert any("task_id=cooldown-skip-log" in item for item in logged)
    assert any("event=credential_frozen" in item for item in logged)


@pytest.mark.asyncio
async def test_target_bound_credentials_are_not_used_for_other_targets():
    policy = CredentialPolicy(store=InMemoryCredentialStateStore())
    request = CollectionRequest(
        task_id="target-bound-credentials",
        plugin_ref="network.config",
        targets=("10.10.69.245", "10.10.69.246"),
        credentials=(
            {
                "credential_id": "credential-247",
                "target_host": "10.10.69.247",
            },
            {
                "credential_id": "credential-245",
                "host": "10.10.69.245",
            },
            {"credential_id": "credential-shared"},
        ),
    )

    for_245 = await policy.eligible_credentials(request, "10.10.69.245")
    for_246 = await policy.eligible_credentials(request, "10.10.69.246")

    assert [item["credential_id"] for item in for_245] == [
        "credential-245",
        "credential-shared",
    ]
    assert [item["credential_id"] for item in for_246] == [
        "credential-shared",
    ]
