"""使用普通 redis.asyncio Client 保存采集运行状态。"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict

from core.collection_runtime import (
    LeaseAcquisition,
    LeaseAcquireStatus,
    RunLease,
    RunStatus,
)
from core.credential_policy import CredentialFailure, CredentialScope


_ACQUIRE_RUN_LUA = """
local run_key = KEYS[1]
local fence_key = KEYS[2]
local request_digest = ARGV[1]
local owner_id = ARGV[2]
local ttl_ms = tonumber(ARGV[3])
local now_ms = tonumber(ARGV[4])
local fence_ttl_ms = tonumber(ARGV[5])

local existing_digest = redis.call('HGET', run_key, 'request_digest')
local existing_owner = redis.call('HGET', run_key, 'owner_id') or ''
local existing_fence = tonumber(redis.call('HGET', run_key, 'fence') or '0')
local existing_expires = tonumber(redis.call('HGET', run_key, 'expires_at_ms') or '0')
local existing_status = redis.call('HGET', run_key, 'status') or ''
local existing_summary = redis.call('HGET', run_key, 'summary') or ''

if existing_digest and existing_digest ~= request_digest then
    return {'conflict', existing_owner, existing_fence, existing_expires, existing_summary}
end
if existing_status == 'completed' then
    return {'completed', existing_owner, existing_fence, existing_expires, existing_summary}
end
if existing_status == 'running' and existing_expires > now_ms then
    return {'duplicate_active', existing_owner, existing_fence, existing_expires, existing_summary}
end

local fence = redis.call('INCR', fence_key)
local expires_at_ms = now_ms + ttl_ms
redis.call(
    'HSET',
    run_key,
    'request_digest', request_digest,
    'owner_id', owner_id,
    'fence', fence,
    'expires_at_ms', expires_at_ms,
    'status', 'running'
)
redis.call('PEXPIRE', run_key, ttl_ms * 2)
redis.call('PEXPIRE', fence_key, fence_ttl_ms)
return {'acquired', owner_id, fence, expires_at_ms, ''}
"""


_FINISH_RUN_LUA = """
local run_key = KEYS[1]
local owner_id = ARGV[1]
local fence = tostring(ARGV[2])
local status = ARGV[3]
local retention_ms = tonumber(ARGV[4])
local summary = ARGV[5]

if redis.call('HGET', run_key, 'owner_id') ~= owner_id then
    return 0
end
if redis.call('HGET', run_key, 'fence') ~= fence then
    return 0
end
redis.call('HSET', run_key, 'status', status, 'summary', summary)
redis.call('PEXPIRE', run_key, retention_ms)
return 1
"""


_HEARTBEAT_RUN_LUA = """
local run_key = KEYS[1]
local owner_id = ARGV[1]
local fence = tostring(ARGV[2])
local ttl_ms = tonumber(ARGV[3])
local now_ms = tonumber(ARGV[4])

if redis.call('HGET', run_key, 'owner_id') ~= owner_id then
    return 0
end
if redis.call('HGET', run_key, 'fence') ~= fence then
    return 0
end
if redis.call('HGET', run_key, 'status') ~= 'running' then
    return 0
end
redis.call('HSET', run_key, 'expires_at_ms', now_ms + ttl_ms)
redis.call('PEXPIRE', run_key, ttl_ms * 2)
return 1
"""


_MARK_TARGET_COMPLETED_LUA = """
local run_key = KEYS[1]
local checkpoint_key = KEYS[2]
local owner_id = ARGV[1]
local fence = tostring(ARGV[2])
local payload = ARGV[3]
local retention_seconds = tonumber(ARGV[4])
local now_ms = tonumber(ARGV[5])

if redis.call('HGET', run_key, 'owner_id') ~= owner_id then
    return 0
end
if redis.call('HGET', run_key, 'fence') ~= fence then
    return 0
end
if redis.call('HGET', run_key, 'status') ~= 'running' then
    return 0
end
if tonumber(redis.call('HGET', run_key, 'expires_at_ms') or '0') <= now_ms then
    return 0
end
redis.call('SET', checkpoint_key, payload, 'EX', retention_seconds)
return 1
"""

_BEGIN_TARGET_PUBLISH_LUA = """
local run_key = KEYS[1]
local owner_id = ARGV[1]
local fence = tostring(ARGV[2])
local now_ms = tonumber(ARGV[3])
local guard_ms = tonumber(ARGV[4])
if redis.call('HGET', run_key, 'owner_id') ~= owner_id or
   redis.call('HGET', run_key, 'fence') ~= fence or
   redis.call('HGET', run_key, 'status') ~= 'running' then return 0 end
local expires = tonumber(redis.call('HGET', run_key, 'expires_at_ms') or '0')
if expires <= now_ms then return 0 end
local guarded = math.max(expires, now_ms + guard_ms)
redis.call('HSET', run_key, 'expires_at_ms', guarded)
redis.call('PEXPIRE', run_key, math.max(1, (guarded - now_ms) * 2))
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
            self._fence_retention_ms,
        )
        status_value, lease_owner, fence, expires_at_ms, summary_value = raw
        status = LeaseAcquireStatus(self._text(status_value))
        lease = RunLease(
            task_id=task_id,
            request_digest=request_digest,
            owner_id=self._text(lease_owner),
            fence=int(fence),
            expires_at=int(expires_at_ms) / 1000,
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
            status.value,
            self._completed_retention_ms,
            json.dumps(summary or {}, separators=(",", ":"), default=str),
        )
        return bool(result)

    async def heartbeat(
        self, lease: RunLease, *, ttl_seconds: float
    ) -> bool:
        ttl_ms = max(1, int(ttl_seconds * 1000))
        result = await self._redis.eval(
            _HEARTBEAT_RUN_LUA,
            1,
            self._run_key(lease.task_id),
            lease.owner_id,
            lease.fence,
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

    async def set_success(
        self, scope: CredentialScope, credential_id: str
    ) -> None:
        await self._redis.set(
            self._success_key(scope),
            credential_id,
            ex=self._affinity_ttl_seconds,
        )

    async def get_failure(
        self, scope: CredentialScope, credential_id: str
    ) -> CredentialFailure | None:
        value = await self._redis.get(self._failure_key(scope, credential_id))
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

    async def clear_failure(
        self, scope: CredentialScope, credential_id: str
    ) -> None:
        await self._redis.delete(self._failure_key(scope, credential_id))

    async def clear_scope_failures(self, scope: CredentialScope) -> None:
        pattern = (
            f"{self._key_prefix}:scope:{self._scope_digest(scope)}:"
            "credential:*:failure"
        )
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

    def _failure_key(
        self, scope: CredentialScope, credential_id: str
    ) -> str:
        credential_digest = hashlib.sha256(
            credential_id.encode("utf-8")
        ).hexdigest()
        return (
            f"{self._key_prefix}:scope:{self._scope_digest(scope)}:"
            f"credential:{credential_digest}:failure"
        )

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


class RedisTargetCheckpointStore:
    """保存可重建的目标完成断点，并以运行 fencing 拒绝迟到写入。"""

    def __init__(
        self,
        redis_client,
        *,
        key_prefix: str = "stargazer:collection:v1",
        retention_seconds: int = 24 * 3600,
        now=time.time,
    ) -> None:
        self._redis = redis_client
        self._key_prefix = key_prefix.rstrip(":")
        self._retention_seconds = retention_seconds
        self._now = now

    async def is_completed(
        self, *, task_id: str, plugin_ref: str, target: str
    ) -> bool:
        value = await self._redis.get(
            self._checkpoint_key(task_id, plugin_ref, target)
        )
        if not value:
            return False
        payload = json.loads(self._text(value))
        return payload.get("state", "completed") == "completed"

    async def load_pending(
        self, *, task_id: str, plugin_ref: str, target: str
    ):
        from core.target_collection_executor import TargetCollectionResult

        value = await self._redis.get(
            self._checkpoint_key(task_id, plugin_ref, target)
        )
        if not value:
            return None
        payload = json.loads(self._text(value))
        if payload.get("state") != "pending":
            return None
        return TargetCollectionResult(**payload["result"])

    async def is_current(self, lease: RunLease) -> bool:
        values = await self._redis.hmget(
            self._run_key(lease.task_id),
            "owner_id",
            "fence",
            "status",
            "expires_at_ms",
        )
        owner_id, fence, status, expires_at_ms = (
            self._text(value) for value in values
        )
        return (
            owner_id == lease.owner_id
            and fence == str(lease.fence)
            and status == RunStatus.RUNNING.value
            and int(expires_at_ms or 0) > int(self._now() * 1000)
        )

    async def mark_completed(
        self, *, plugin_ref: str, result, lease: RunLease
    ) -> bool:
        payload = self._result_payload(
            state="completed", plugin_ref=plugin_ref, result=result, lease=lease
        )
        saved = await self._save_checkpoint(plugin_ref, result, lease, payload)
        return bool(saved)

    async def mark_publish_pending(
        self, *, plugin_ref: str, result, lease: RunLease
    ) -> bool:
        payload = self._result_payload(
            state="pending", plugin_ref=plugin_ref, result=result, lease=lease
        )
        return bool(await self._save_checkpoint(plugin_ref, result, lease, payload))

    async def begin_publish(
        self, lease: RunLease, *, guard_seconds: float
    ) -> bool:
        result = await self._redis.eval(
            _BEGIN_TARGET_PUBLISH_LUA,
            1,
            self._run_key(lease.task_id),
            lease.owner_id,
            lease.fence,
            int(self._now() * 1000),
            max(1, int(guard_seconds * 1000)),
        )
        return bool(result)

    def _result_payload(self, *, state, plugin_ref, result, lease) -> str:
        return json.dumps(
            {
                "state": state,
                "fence": lease.fence,
                "plugin_ref": plugin_ref,
                "result": asdict(result),
                "task_id": lease.task_id,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        )

    async def _save_checkpoint(self, plugin_ref, result, lease, payload):
        return await self._redis.eval(
            _MARK_TARGET_COMPLETED_LUA,
            2,
            self._run_key(lease.task_id),
            self._checkpoint_key(
                lease.task_id, plugin_ref, str(result.target)
            ),
            lease.owner_id,
            lease.fence,
            payload,
            self._retention_seconds,
            int(self._now() * 1000),
        )

    def _run_key(self, task_id: str) -> str:
        return f"{self._key_prefix}:run:{task_id}"

    def _checkpoint_key(
        self, task_id: str, plugin_ref: str, target: str
    ) -> str:
        identity = json.dumps(
            [task_id, plugin_ref, target],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        return f"{self._key_prefix}:checkpoint:{digest}"

    @staticmethod
    def _text(value) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)
