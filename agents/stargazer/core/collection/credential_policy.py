"""跨采集运行复用的凭据亲和与冷冻策略。"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from core.collection.runtime import CollectionRequest
from core.logger import logger


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

    async def load_target_state(
        self,
        scope: CredentialScope,
        credential_ids: tuple[str, ...] | list[str],
    ) -> tuple[str, dict[str, CredentialFailure | None]]: ...

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
    # S1：5min → 30min → 4h → 24h
    COOLDOWN_SECONDS = {
        1: 5 * 60,
        2: 30 * 60,
        3: 4 * 3600,
        4: 24 * 3600,
    }

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
        credentials = self.matching_credentials(request, target)
        scope = self._scope(request, target)
        credential_ids = tuple(
            str(credential.get("credential_id") or "")
            for credential in credentials
        )
        success_id, failures = await self._store.load_target_state(
            scope, credential_ids
        )
        eligible = []
        now = self._now()
        for credential, credential_id in zip(credentials, credential_ids):
            failure = failures.get(credential_id)
            if failure and failure.next_retry_at > now:
                logger.info(
                    "⏸️ event=credential_cooldown_skipped task_id=%s target=%s "
                    "credential_id=%s cooldown_level=%s next_retry_at=%s "
                    "error_code=%s",
                    request.task_id,
                    target,
                    credential_id or "-",
                    failure.cooldown_level,
                    failure.next_retry_at,
                    failure.error_code,
                )
                continue
            eligible.append(credential)
        if success_id:
            eligible.sort(
                key=lambda credential: (
                    str(credential.get("credential_id") or "") != success_id
                )
            )
        return tuple(eligible)

    def matching_credentials(
        self, request: CollectionRequest, target: str
    ) -> tuple[Mapping[str, Any], ...]:
        return tuple(
            credential
            for credential in tuple(request.credentials) or ({},)
            if self._matches_target(credential, target)
        )

    async def next_retry_at(
        self, request: CollectionRequest, target: str
    ) -> float | None:
        scope = self._scope(request, target)
        credentials = self.matching_credentials(request, target)
        credential_ids = tuple(
            str(credential.get("credential_id") or "")
            for credential in credentials
        )
        _success_id, failures = await self._store.load_target_state(
            scope, credential_ids
        )
        retry_times = [
            failure.next_retry_at
            for failure in failures.values()
            if failure and failure.next_retry_at > self._now()
        ]
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
        await self._store.clear_failure(scope, credential_id)

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
        level = min(consecutive, max(self.COOLDOWN_SECONDS))
        cooldown = self.COOLDOWN_SECONDS[level]
        jitter = self._jitter(0, min(60, cooldown * 0.05))
        next_retry_at = self._now() + cooldown + jitter
        await self._store.set_failure(
            scope,
            credential_id,
            CredentialFailure(
                error_code=error_code,
                consecutive_failures=consecutive,
                cooldown_level=level,
                next_retry_at=next_retry_at,
            ),
        )
        logger.info(
            "🧊 event=credential_frozen task_id=%s target=%s credential_id=%s "
            "cooldown_level=%s consecutive_failures=%s next_retry_at=%s "
            "error_code=%s",
            request.task_id,
            target,
            credential_id,
            level,
            consecutive,
            next_retry_at,
            error_code,
        )

    @staticmethod
    def _matches_target(
        credential: Mapping[str, Any], target: str
    ) -> bool:
        bound_target = str(
            credential.get("target_host") or credential.get("host") or ""
        ).strip()
        return not bound_target or bound_target == target

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

    async def load_target_state(
        self,
        scope: CredentialScope,
        credential_ids: tuple[str, ...] | list[str],
    ) -> tuple[str, dict[str, CredentialFailure | None]]:
        async with self._lock:
            success_id = self._success.get(scope, "")
            failures = {
                str(credential_id or ""): self._failures.get(
                    (scope, str(credential_id or ""))
                )
                for credential_id in credential_ids
            }
            return success_id, failures

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
