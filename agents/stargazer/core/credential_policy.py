"""跨采集运行复用的凭据亲和与冷冻策略。"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from core.collection_runtime import CollectionRequest


@dataclass(frozen=True)
class CredentialScope:
    scope_id: str
    plugin_ref: str
    target_id: str
    credential_set_version: str


@dataclass(frozen=True)
class CredentialFailure:
    error_code: str
    consecutive_failures: int
    cooldown_level: int
    next_retry_at: float


class CredentialStateStore(Protocol):
    async def get_success(self, scope: CredentialScope) -> str: ...

    async def set_success(
        self, scope: CredentialScope, credential_id: str
    ) -> None: ...

    async def get_failure(
        self, scope: CredentialScope, credential_id: str
    ) -> CredentialFailure | None: ...

    async def set_failure(
        self,
        scope: CredentialScope,
        credential_id: str,
        failure: CredentialFailure,
    ) -> None: ...

    async def clear_failure(
        self, scope: CredentialScope, credential_id: str
    ) -> None: ...

    async def clear_scope_failures(self, scope: CredentialScope) -> None: ...


class CredentialPolicy:
    COOLDOWN_SECONDS = {1: 3600, 2: 4 * 3600, 3: 24 * 3600}

    def __init__(
        self,
        *,
        store: CredentialStateStore,
        now: Callable[[], float] = time.time,
        jitter: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self._store = store
        self._now = now
        self._jitter = jitter

    async def eligible_credentials(
        self, request: CollectionRequest, target: str
    ) -> tuple[Mapping[str, Any], ...]:
        credentials = tuple(request.credentials) or ({},)
        scope = self._scope(request, target)
        success_id = await self._store.get_success(scope)
        eligible = []
        now = self._now()
        for credential in credentials:
            credential_id = str(credential.get("credential_id") or "")
            failure = await self._store.get_failure(scope, credential_id)
            if failure and failure.next_retry_at > now:
                continue
            eligible.append(credential)
        if success_id:
            eligible.sort(
                key=lambda credential: (
                    str(credential.get("credential_id") or "") != success_id
                )
            )
        return tuple(eligible)

    async def next_retry_at(
        self, request: CollectionRequest, target: str
    ) -> float | None:
        scope = self._scope(request, target)
        retry_times = []
        for credential in tuple(request.credentials) or ({},):
            credential_id = str(credential.get("credential_id") or "")
            failure = await self._store.get_failure(scope, credential_id)
            if failure and failure.next_retry_at > self._now():
                retry_times.append(failure.next_retry_at)
        return min(retry_times) if retry_times else None

    async def record_success(
        self,
        request: CollectionRequest,
        target: str,
        credential: Mapping[str, Any],
    ) -> None:
        credential_id = str(credential.get("credential_id") or "")
        if not credential_id:
            return
        scope = self._scope(request, target)
        await self._store.set_success(scope, credential_id)
        await self._store.clear_scope_failures(scope)

    async def record_auth_failure(
        self,
        request: CollectionRequest,
        target: str,
        credential: Mapping[str, Any],
        *,
        error_code: str,
    ) -> None:
        credential_id = str(credential.get("credential_id") or "")
        if not credential_id:
            return
        scope = self._scope(request, target)
        previous = await self._store.get_failure(scope, credential_id)
        consecutive = (previous.consecutive_failures if previous else 0) + 1
        level = 1 if consecutive == 1 else 2 if consecutive == 2 else 3
        cooldown = self.COOLDOWN_SECONDS[level]
        jitter = self._jitter(0, min(300, cooldown * 0.05))
        await self._store.set_failure(
            scope,
            credential_id,
            CredentialFailure(
                error_code=error_code,
                consecutive_failures=consecutive,
                cooldown_level=level,
                next_retry_at=self._now() + cooldown + jitter,
            ),
        )

    @staticmethod
    def _scope(request: CollectionRequest, target: str) -> CredentialScope:
        return CredentialScope(
            scope_id=str(request.params.get("scope_id") or "default"),
            plugin_ref=request.plugin_ref,
            target_id=target,
            credential_set_version=str(
                request.params.get("credential_set_version") or "default"
            ),
        )


class InMemoryCredentialStateStore:
    def __init__(self) -> None:
        self._success: dict[CredentialScope, str] = {}
        self._failures: dict[tuple[CredentialScope, str], CredentialFailure] = {}
        self._lock = asyncio.Lock()

    async def get_success(self, scope: CredentialScope) -> str:
        async with self._lock:
            return self._success.get(scope, "")

    async def set_success(
        self, scope: CredentialScope, credential_id: str
    ) -> None:
        async with self._lock:
            self._success[scope] = credential_id

    async def get_failure(
        self, scope: CredentialScope, credential_id: str
    ) -> CredentialFailure | None:
        async with self._lock:
            return self._failures.get((scope, credential_id))

    async def set_failure(
        self,
        scope: CredentialScope,
        credential_id: str,
        failure: CredentialFailure,
    ) -> None:
        async with self._lock:
            self._failures[(scope, credential_id)] = failure

    async def clear_failure(
        self, scope: CredentialScope, credential_id: str
    ) -> None:
        async with self._lock:
            self._failures.pop((scope, credential_id), None)

    async def clear_scope_failures(self, scope: CredentialScope) -> None:
        async with self._lock:
            keys = [key for key in self._failures if key[0] == scope]
            for key in keys:
                self._failures.pop(key, None)
