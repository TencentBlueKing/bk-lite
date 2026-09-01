"""使用普通 redis.asyncio Client 保存采集运行状态。"""

from __future__ import annotations

import hashlib
import json
import time
import uuid

from core.collection.credential_policy import CredentialFailure, CredentialScope
from core.collection.runtime import LeaseAcquireStatus, LeaseAcquisition, RunLease, RunStatus

_ACQUIRE_RUN_LUA = """
-- 薄租约：执行中则 duplicate_active；否则取得租约。不做 digest 冲突、不做 fencing 接管续跑。
local run_key = KEYS[1]
local generation_key = KEYS[2]
local request_digest = ARGV[1]
local owner_id = ARGV[2]
local ttl_ms = tonumber(ARGV[3])
local now_ms = tonumber(ARGV[4])
local attempt_id = ARGV[5]
local generation_retention_ms = tonumber(ARGV[6])

local existing_owner = redis.call('HGET', run_key, 'owner_id') or ''
local existing_expires = tonumber(redis.call('HGET', run_key, 'expires_at_ms') or '0')
local existing_status = redis.call('HGET', run_key, 'status') or ''
local existing_fence = tonumber(redis.call('HGET', run_key, 'fence') or '1')
local existing_attempt_id = redis.call('HGET', run_key, 'attempt_id') or ''

if existing_status == 'running' and existing_expires > now_ms then
    return {'duplicate_active', existing_owner, existing_fence, existing_expires, '', existing_attempt_id}
end

local expires_at_ms = now_ms + ttl_ms
redis.call(
    'HSET',
    run_key,
    'request_digest', request_digest,
    'owner_id', owner_id,
    'fence', 1,
    'attempt_id', attempt_id,
    'expires_at_ms', expires_at_ms,
    'status', 'running'
)
redis.call('HDEL', run_key, 'summary')
redis.call('PEXPIRE', run_key, ttl_ms * 2)
redis.call(
    'HSET',
    generation_key,
    'owner_id', owner_id,
    'fence', 1,
    'attempt_id', attempt_id
)
redis.call('PEXPIRE', generation_key, generation_retention_ms)
return {'acquired', owner_id, 1, expires_at_ms, '', attempt_id}
"""


_FINISH_RUN_LUA = """
local run_key = KEYS[1]
local owner_id = ARGV[1]
local fence = tostring(ARGV[2])
local attempt_id = ARGV[3]
local status = ARGV[4]
local retention_ms = tonumber(ARGV[5])
local summary = ARGV[6]

if redis.call('HGET', run_key, 'owner_id') ~= owner_id then
    return 0
end
if redis.call('HGET', run_key, 'fence') ~= fence then
    return 0
end
if redis.call('HGET', run_key, 'attempt_id') ~= attempt_id then
    return 0
end
-- 薄模型：结束后删除租约，下周期整轮重采；不保留 completed 汇总供同 task_id 回读
redis.call('DEL', run_key)
return 1
"""


_HEARTBEAT_RUN_LUA = """
local run_key = KEYS[1]
local owner_id = ARGV[1]
local fence = tostring(ARGV[2])
local attempt_id = ARGV[3]
local ttl_ms = tonumber(ARGV[4])
local now_ms = tonumber(ARGV[5])

if redis.call('HGET', run_key, 'owner_id') ~= owner_id then
    return 0
end
if redis.call('HGET', run_key, 'fence') ~= fence then
    return 0
end
if redis.call('HGET', run_key, 'attempt_id') ~= attempt_id then
    return 0
end
if redis.call('HGET', run_key, 'status') ~= 'running' then
    return 0
end
redis.call('HSET', run_key, 'expires_at_ms', now_ms + ttl_ms)
redis.call('PEXPIRE', run_key, ttl_ms * 2)
return 1
"""


_SET_CREDENTIAL_SUCCESS_LUA = """
redis.call('SET', KEYS[1], ARGV[1], 'EX', tonumber(ARGV[2]))
redis.call('DEL', KEYS[2])
return 1
"""


class RedisRunStateStore:
    def __init__(
        self,
        redis_client,
        *,
        key_prefix: str = "stargazer:collection:v1",
        completed_retention_seconds: int = 24 * 3600,
        fence_retention_seconds: int = 7 * 24 * 3600,
        now=time.time,
    ) -> None:
        self._redis = redis_client
        self._key_prefix = key_prefix.rstrip(":")
        self._completed_retention_ms = int(completed_retention_seconds * 1000)
        self._fence_retention_ms = int(fence_retention_seconds * 1000)
        self._now = now

    async def acquire(
        self,
        *,
        task_id: str,
        request_digest: str,
        owner_id: str,
        ttl_seconds: float,
    ) -> LeaseAcquisition:
        now_ms = int(self._now() * 1000)
        ttl_ms = max(1, int(ttl_seconds * 1000))
        raw = await self._redis.eval(
            _ACQUIRE_RUN_LUA,
            2,
            self._run_key(task_id),
            self._fence_key(task_id),
            request_digest,
            owner_id,
            ttl_ms,
            now_ms,
            uuid.uuid4().hex,
            self._fence_retention_ms,
        )
        status_value, lease_owner, fence, expires_at_ms, summary_value, attempt_id = raw
        status = LeaseAcquireStatus(self._text(status_value))
        lease = RunLease(
            task_id=task_id,
            request_digest=request_digest,
            owner_id=self._text(lease_owner),
            fence=int(fence),
            expires_at=int(expires_at_ms) / 1000,
            attempt_id=self._text(attempt_id),
        )
        summary_text = self._text(summary_value)
        summary = json.loads(summary_text) if summary_text else {}
        return LeaseAcquisition(status=status, lease=lease, summary=summary)

    async def finish(
        self,
        lease: RunLease,
        status: RunStatus,
        summary=None,
    ) -> bool:
        result = await self._redis.eval(
            _FINISH_RUN_LUA,
            1,
            self._run_key(lease.task_id),
            lease.owner_id,
            lease.fence,
            lease.attempt_id,
            status.value,
            self._completed_retention_ms,
            json.dumps(summary or {}, separators=(",", ":"), default=str),
        )
        return bool(result)

    async def heartbeat(self, lease: RunLease, *, ttl_seconds: float) -> bool:
        ttl_ms = max(1, int(ttl_seconds * 1000))
        result = await self._redis.eval(
            _HEARTBEAT_RUN_LUA,
            1,
            self._run_key(lease.task_id),
            lease.owner_id,
            lease.fence,
            lease.attempt_id,
            ttl_ms,
            int(self._now() * 1000),
        )
        return bool(result)

    def _run_key(self, task_id: str) -> str:
        return f"{self._key_prefix}:run:{task_id}"

    def _fence_key(self, task_id: str) -> str:
        return f"{self._key_prefix}:fence:{task_id}"

    @staticmethod
    def _text(value) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)


class RedisCredentialStateStore:
    """只持久化凭据引用与失败状态，不接收或保存凭据正文。"""

    def __init__(
        self,
        redis_client,
        *,
        key_prefix: str = "stargazer:collection:v1:credential",
        affinity_ttl_seconds: int = 7 * 24 * 3600,
        failure_ttl_seconds: int = 25 * 3600,
    ) -> None:
        self._redis = redis_client
        self._key_prefix = key_prefix.rstrip(":")
        self._affinity_ttl_seconds = affinity_ttl_seconds
        self._failure_ttl_seconds = failure_ttl_seconds

    async def get_success(self, scope: CredentialScope) -> str:
        value = await self._redis.get(self._success_key(scope))
        return self._text(value)

    async def load_target_state(
        self,
        scope: CredentialScope,
        credential_ids: tuple[str, ...] | list[str],
    ) -> tuple[str, dict[str, CredentialFailure | None]]:
        """一次 MGET 拉取 success + 各凭据 failure，降低并发占连接时间。"""
        keys = [self._success_key(scope)]
        normalized_ids = [str(item or "") for item in credential_ids]
        keys.extend(self._failure_key(scope, credential_id) for credential_id in normalized_ids)
        values = await self._redis.mget(keys)
        success_id = self._text(values[0] if values else None)
        failures: dict[str, CredentialFailure | None] = {}
        for index, credential_id in enumerate(normalized_ids, start=1):
            raw = values[index] if values and index < len(values) else None
            failures[credential_id] = self._parse_failure(raw)
        return success_id, failures

    async def set_success(self, scope: CredentialScope, credential_id: str) -> None:
        await self._redis.eval(
            _SET_CREDENTIAL_SUCCESS_LUA,
            2,
            self._success_key(scope),
            self._failure_key(scope, credential_id),
            credential_id,
            self._affinity_ttl_seconds,
        )

    async def get_failure(self, scope: CredentialScope, credential_id: str) -> CredentialFailure | None:
        value = await self._redis.get(self._failure_key(scope, credential_id))
        return self._parse_failure(value)

    def _parse_failure(self, value) -> CredentialFailure | None:
        if not value:
            return None
        payload = json.loads(self._text(value))
        return CredentialFailure(
            error_code=str(payload["error_code"]),
            consecutive_failures=int(payload["consecutive_failures"]),
            cooldown_level=int(payload["cooldown_level"]),
            next_retry_at=float(payload["next_retry_at"]),
        )

    async def set_failure(
        self,
        scope: CredentialScope,
        credential_id: str,
        failure: CredentialFailure,
    ) -> None:
        payload = json.dumps(
            {
                "error_code": failure.error_code,
                "consecutive_failures": failure.consecutive_failures,
                "cooldown_level": failure.cooldown_level,
                "next_retry_at": failure.next_retry_at,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        await self._redis.set(
            self._failure_key(scope, credential_id),
            payload,
            ex=self._failure_ttl_seconds,
        )

    async def clear_failure(self, scope: CredentialScope, credential_id: str) -> None:
        await self._redis.delete(self._failure_key(scope, credential_id))

    async def clear_scope_failures(self, scope: CredentialScope) -> None:
        pattern = f"{self._key_prefix}:scope:{self._scope_digest(scope)}:" "credential:*:failure"
        batch = []
        async for key in self._redis.scan_iter(match=pattern, count=100):
            batch.append(key)
            if len(batch) >= 100:
                await self._redis.delete(*batch)
                batch.clear()
        if batch:
            await self._redis.delete(*batch)

    def _success_key(self, scope: CredentialScope) -> str:
        return f"{self._key_prefix}:scope:{self._scope_digest(scope)}:success"

    def _failure_key(self, scope: CredentialScope, credential_id: str) -> str:
        credential_digest = hashlib.sha256(credential_id.encode("utf-8")).hexdigest()
        return f"{self._key_prefix}:scope:{self._scope_digest(scope)}:" f"credential:{credential_digest}:failure"

    @staticmethod
    def _scope_digest(scope: CredentialScope) -> str:
        payload = json.dumps(
            {
                "credential_set_version": scope.credential_set_version,
                "plugin_ref": scope.plugin_ref,
                "scope_id": scope.scope_id,
                "target_id": scope.target_id,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _text(value) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)
