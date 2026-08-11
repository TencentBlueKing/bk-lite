"""Stargazer 无状态统一异步采集运行时。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Awaitable, Callable, Mapping, Protocol, Sequence

from core.collection.constants import SECRET_KEYS
from core.collection.enums import (
    LeaseAcquireStatus,
    RunStatus,
    SubmissionStatus,
)
from core.logger import logger

# 兼容：历史调用方从 runtime 导入枚举
__all__ = [
    "CollectionRequest",
    "CollectionRuntime",
    "CollectionRuntimeSettings",
    "InMemoryRunStateStore",
    "LeaseAcquisition",
    "LeaseAcquireStatus",
    "RunLease",
    "RunStateStore",
    "RunStatus",
    "Submission",
    "SubmissionStatus",
]


@dataclass(frozen=True)
class CollectionRequest:
    task_id: str
    plugin_ref: str
    targets: tuple[str, ...]
    credentials: tuple[Mapping[str, Any], ...] = ()
    params: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.task_id).strip():
            raise ValueError("task_id is required")
        if not str(self.plugin_ref).strip():
            raise ValueError("plugin_ref is required")
        if not self.targets:
            raise ValueError("at least one target is required")

    @property
    def digest(self) -> str:
        credential_refs = []
        for credential in self.credentials:
            credential_refs.append(
                {
                    "credential_id": credential.get("credential_id"),
                    "credential_version": credential.get("credential_version"),
                    "target_host": (
                        credential.get("target_host")
                        or credential.get("host")
                    ),
                }
            )
        canonical = {
            "plugin_ref": self.plugin_ref,
            "targets": list(self.targets),
            "credentials": credential_refs,
            "params": _redact_secrets(self.params),
        }
        payload = json.dumps(
            canonical,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class RunLease:
    task_id: str
    request_digest: str
    owner_id: str
    fence: int
    expires_at: float


@dataclass(frozen=True)
class LeaseAcquisition:
    status: LeaseAcquireStatus
    lease: RunLease | None = None
    summary: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Submission:
    task_id: str
    status: SubmissionStatus
    fence: int = 0
    reason: str = ""
    summary: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CollectionRuntimeSettings:
    max_active_runs: int = 16
    lease_ttl_seconds: float = 600.0
    lease_heartbeat_seconds: float = 30.0
    run_deadline_seconds: float = 0.0

    def __post_init__(self) -> None:
        if self.max_active_runs <= 0:
            raise ValueError("max_active_runs must be greater than zero")
        if self.lease_ttl_seconds <= 0:
            raise ValueError("lease_ttl_seconds must be greater than zero")
        if self.lease_heartbeat_seconds <= 0:
            raise ValueError("lease_heartbeat_seconds must be greater than zero")
        if self.lease_heartbeat_seconds >= self.lease_ttl_seconds:
            raise ValueError(
                "lease_heartbeat_seconds must be less than lease_ttl_seconds"
            )
        if self.run_deadline_seconds < 0:
            raise ValueError("run_deadline_seconds cannot be negative")


class RunStateStore(Protocol):
    async def acquire(
        self,
        *,
        task_id: str,
        request_digest: str,
        owner_id: str,
        ttl_seconds: float,
    ) -> LeaseAcquisition: ...

    async def heartbeat(
        self, lease: RunLease, *, ttl_seconds: float
    ) -> bool: ...

    async def finish(
        self,
        lease: RunLease,
        status: RunStatus,
        summary: Mapping[str, Any] | None = None,
    ) -> bool: ...


@dataclass
class _InMemoryRunRecord:
    request_digest: str
    lease: RunLease
    status: RunStatus
    summary: Mapping[str, Any] = field(default_factory=dict)


class InMemoryRunStateStore:
    """供接口测试和本地运行使用的 RunStateStore Adapter。"""

    def __init__(self) -> None:
        self._records: dict[str, _InMemoryRunRecord] = {}
        self._lock = asyncio.Lock()

    async def acquire(
        self,
        *,
        task_id: str,
        request_digest: str,
        owner_id: str,
        ttl_seconds: float,
    ) -> LeaseAcquisition:
        async with self._lock:
            now = time.monotonic()
            record = self._records.get(task_id)
            if (
                record
                and record.status == RunStatus.RUNNING
                and record.lease.expires_at > now
            ):
                return LeaseAcquisition(
                    LeaseAcquireStatus.DUPLICATE_ACTIVE, record.lease
                )

            # 薄租约：固定 fence=1 仅作回调身份，不做递增接管
            lease = RunLease(
                task_id=task_id,
                request_digest=request_digest,
                owner_id=owner_id,
                fence=1,
                expires_at=now + ttl_seconds,
            )
            self._records[task_id] = _InMemoryRunRecord(
                request_digest=request_digest,
                lease=lease,
                status=RunStatus.RUNNING,
            )
            return LeaseAcquisition(LeaseAcquireStatus.ACQUIRED, lease)

    async def finish(
        self,
        lease: RunLease,
        status: RunStatus,
        summary: Mapping[str, Any] | None = None,
    ) -> bool:
        async with self._lock:
            record = self._records.get(lease.task_id)
            if not record:
                return False
            if (
                record.lease.owner_id != lease.owner_id
                or record.lease.fence != lease.fence
            ):
                return False
            # 结束后释放，允许同 task_id 下周期重新接纳
            self._records.pop(lease.task_id, None)
            return True

    async def heartbeat(
        self, lease: RunLease, *, ttl_seconds: float
    ) -> bool:
        async with self._lock:
            record = self._records.get(lease.task_id)
            if not record or record.status != RunStatus.RUNNING:
                return False
            if (
                record.lease.owner_id != lease.owner_id
                or record.lease.fence != lease.fence
            ):
                return False
            record.lease = RunLease(
                task_id=lease.task_id,
                request_digest=lease.request_digest,
                owner_id=lease.owner_id,
                fence=lease.fence,
                expires_at=time.monotonic() + ttl_seconds,
            )
            return True


ExecuteCollectionRun = Callable[[CollectionRequest, RunLease], Awaitable[Any]]
ScheduleTask = Callable[..., asyncio.Task]


class CollectionRuntime:
    """接纳、登记并运行 CollectionRun 的深模块。"""

    def __init__(
        self,
        *,
        state_store: RunStateStore,
        execute: ExecuteCollectionRun,
        schedule: ScheduleTask,
        settings: CollectionRuntimeSettings | None = None,
        owner_id: str,
    ) -> None:
        self._state_store = state_store
        self._execute = execute
        self._schedule = schedule
        self._settings = settings or CollectionRuntimeSettings()
        self._owner_id = str(owner_id).strip()
        if not self._owner_id:
            raise ValueError("owner_id is required")
        self._active_runs = 0
        self._accepting = True
        self._admission_lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()

    @property
    def active_runs(self) -> int:
        return self._active_runs

    async def submit(self, request: CollectionRequest) -> Submission:
        async with self._admission_lock:
            if not self._accepting:
                return Submission(
                    task_id=request.task_id,
                    status=SubmissionStatus.BUSY,
                    reason="collection runtime is shutting down",
                )
        acquisition = await self._state_store.acquire(
            task_id=request.task_id,
            request_digest=request.digest,
            owner_id=self._owner_id,
            ttl_seconds=self._settings.lease_ttl_seconds,
        )
        lease = acquisition.lease
        if acquisition.status == LeaseAcquireStatus.DUPLICATE_ACTIVE:
            return Submission(
                task_id=request.task_id,
                status=SubmissionStatus.DUPLICATE_ACTIVE,
                fence=lease.fence if lease else 0,
            )
        if lease is None:
            raise RuntimeError("state store acquired a run without a lease")

        if not await self._try_admit():
            await self._state_store.finish(lease, RunStatus.ABANDONED)
            return Submission(
                task_id=request.task_id,
                status=SubmissionStatus.BUSY,
                fence=lease.fence,
                reason="collection runtime capacity is full",
            )

        try:
            task = self._schedule(
                self._run(request, lease),
                name=f"collection-run:{request.task_id}:{lease.fence}",
            )
        except Exception:
            await self._release_admission()
            await self._state_store.finish(lease, RunStatus.ABANDONED)
            raise
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return Submission(
            task_id=request.task_id,
            status=SubmissionStatus.ACCEPTED,
            fence=lease.fence,
        )

    async def _try_admit(self) -> bool:
        async with self._admission_lock:
            if not self._accepting:
                return False
            if self._active_runs >= self._settings.max_active_runs:
                return False
            self._active_runs += 1
            return True

    async def _release_admission(self) -> None:
        async with self._admission_lock:
            self._active_runs = max(0, self._active_runs - 1)

    async def _run(self, request: CollectionRequest, lease: RunLease) -> None:
        status = RunStatus.COMPLETED
        summary: Mapping[str, Any] = {}
        run_task = asyncio.current_task()
        heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(lease, run_task),
            name=f"collection-heartbeat:{request.task_id}:{lease.fence}",
        )
        try:
            if self._settings.run_deadline_seconds:
                async with asyncio.timeout(
                    self._settings.run_deadline_seconds
                ):
                    result = await self._execute(request, lease)
            else:
                result = await self._execute(request, lease)
            summary = _normalize_summary(result)
        except asyncio.CancelledError:
            status = RunStatus.ABANDONED
            raise
        except Exception:
            status = RunStatus.FAILED
            logger.exception(
                "collection run failed task_id=%s fence=%s",
                request.task_id,
                lease.fence,
            )
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            await self._state_store.finish(lease, status, summary)
            await self._release_admission()

    async def shutdown(self, *, grace_seconds: float = 30.0) -> None:
        """停止接纳，宽限等待后取消仍在运行的顶层任务。"""
        async with self._admission_lock:
            self._accepting = False
        tasks = tuple(task for task in self._tasks if not task.done())
        if not tasks:
            return
        _done, pending = await asyncio.wait(tasks, timeout=max(grace_seconds, 0))
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    async def _heartbeat_loop(
        self, lease: RunLease, run_task: asyncio.Task | None
    ) -> None:
        while True:
            await asyncio.sleep(self._settings.lease_heartbeat_seconds)
            try:
                renewed = await self._state_store.heartbeat(
                    lease,
                    ttl_seconds=self._settings.lease_ttl_seconds,
                )
            except asyncio.CancelledError:
                raise
            except Exception:  # Redis 故障时 fail closed，停止失去保护的执行
                logger.exception(
                    "collection run heartbeat failed task_id=%s fence=%s",
                    lease.task_id,
                    lease.fence,
                )
                renewed = False
            if renewed:
                continue
            logger.warning(
                "collection run lost lease task_id=%s fence=%s",
                lease.task_id,
                lease.fence,
            )
            if run_task is not None:
                run_task.cancel()
            return


def _redact_secrets(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "<redacted>" if str(key).lower() in SECRET_KEYS else _redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_redact_secrets(item) for item in value]
    return value


def _normalize_summary(value: Any) -> Mapping[str, Any]:
    if value is None:
        return {}
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, Mapping):
        return dict(value)
    return {"result": str(value)}
