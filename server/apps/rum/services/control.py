from __future__ import annotations

import asyncio
import json
import os
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from apps.core.logger import rum_logger as logger
from apps.rum.constants import API_VERSION
from apps.rum.services.settings import load_rum_settings


class ControlError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message

    def control_code(self) -> str:
        return self.code


def control_unavailable(exc: BaseException | None) -> bool:
    return isinstance(exc, ControlError) and exc.code == "unavailable"


class ControlPlane(Protocol):
    def available(self) -> bool:
        ...

    def request(
        self,
        subject: str,
        actor: str,
        payload: dict | list | None = None,
        expected_revision: int | None = None,
    ) -> tuple[int, Any]:
        ...


@dataclass
class UnavailableControl:
    message: str = "RUM controller is not configured"

    def available(self) -> bool:
        return False

    def request(
        self,
        subject: str,
        actor: str,
        payload: dict | list | None = None,
        expected_revision: int | None = None,
    ) -> tuple[int, Any]:
        raise ControlError("unavailable", self.message)


class MemoryControl:
    """In-memory controller stand-in for unit tests."""

    def __init__(self):
        self._apps: dict[str, dict] = {}
        self._operations: dict[str, dict] = {}
        self._revision = 0

    def available(self) -> bool:
        return True

    def request(
        self,
        subject: str,
        actor: str,
        payload: dict | list | None = None,
        expected_revision: int | None = None,
    ) -> tuple[int, Any]:
        from apps.rum.constants import (
            SUBJECT_APPLICATION_APPLY,
            SUBJECT_APPLICATION_GET,
            SUBJECT_APPLICATION_LIST,
            SUBJECT_ERASURE_SUBMIT,
            SUBJECT_OPERATION_GET,
        )

        if subject == SUBJECT_APPLICATION_LIST:
            return self._revision, list(self._apps.values())
        if subject == SUBJECT_APPLICATION_GET:
            name = (payload or {}).get("application", "")
            view = self._apps.get(name)
            if view is None:
                raise ControlError("not_found", f"application {name!r} not found")
            return self._revision, view
        if subject == SUBJECT_APPLICATION_APPLY:
            body = payload or {}
            name = body["application"]
            current = self._apps.get(name)
            if expected_revision is not None:
                current_rev = 0 if current is None else int(current.get("revision", 0))
                if current_rev != expected_revision:
                    raise ControlError("revision_conflict", "expected revision mismatch")
            self._revision += 1
            view = {
                "application": name,
                "tenantId": body.get("tenantId") or "core",
                "enabled": bool(body.get("enabled", True)),
                "revision": self._revision,
                "browserKeys": list(body.get("browserKeys") or []),
                "browserKeyDigests": [],
                "origins": list(body.get("origins") or []),
                "budgets": body.get("budgets") or {},
                "lastAcceptedAt": body["lastAcceptedAt"] if "lastAcceptedAt" in body else (current or {}).get("lastAcceptedAt", 0),
                "lastStoredAt": body["lastStoredAt"] if "lastStoredAt" in body else (current or {}).get("lastStoredAt", 0),
            }
            if body.get("orgId"):
                view["orgId"] = body["orgId"]
            self._apps[name] = view
            return self._revision, view
        if subject == SUBJECT_ERASURE_SUBMIT:
            body = payload or {}
            application = body.get("application") or ""
            if application not in self._apps:
                raise ControlError("not_found", f"application {application!r} not found")
            if expected_revision is None:
                raise ControlError("invalid_argument", "expectedRevision is required")
            current_rev = int(self._apps[application].get("revision", 0))
            if current_rev != expected_revision:
                raise ControlError("revision_conflict", "expected revision mismatch")
            identities = body.get("identities") or []
            if not identities:
                raise ControlError("invalid_argument", "identities are required")
            operation = {
                "operationId": f"op-{uuid.uuid4()}",
                "type": "erasure",
                "status": "accepted",
                "application": application,
                "actor": actor,
                "identities": identities,
            }
            self._operations[operation["operationId"]] = operation
            return self._revision, dict(operation)
        if subject == SUBJECT_OPERATION_GET:
            operation_id = (payload or {}).get("operationId", "")
            operation = self._operations.get(operation_id)
            if operation is None:
                raise ControlError("not_found", f"operation {operation_id!r} not found")
            return self._revision, dict(operation)
        raise ControlError("invalid_argument", f"unsupported subject {subject}")


class NatsControlClient:
    """NATS request-reply client matching pkg/rum/wire ControlClient envelopes.

    One connection is kept per process on a dedicated event-loop thread so
    request handlers (sync Django views) do not pay a TCP + NATS handshake per
    call. The connection is re-established lazily after a disconnect or fork.
    """

    def __init__(self, url: str, timeout_seconds: float = 5.0):
        self._url = url.strip()
        self._timeout = timeout_seconds
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._pid: int | None = None
        self._nc: Any = None
        self._connect_lock: asyncio.Lock | None = None

    def available(self) -> bool:
        return bool(self._url)

    def request(
        self,
        subject: str,
        actor: str,
        payload: dict | list | None = None,
        expected_revision: int | None = None,
    ) -> tuple[int, Any]:
        if not self._url:
            raise ControlError("unavailable", "RUM controller is not configured")
        envelope = {
            "apiVersion": API_VERSION,
            "requestId": str(uuid.uuid4()),
            "idempotencyKey": str(uuid.uuid4()),
            "actor": actor or "anonymous",
            "payload": payload if payload is not None else {},
        }
        if expected_revision is not None:
            envelope["expectedRevision"] = expected_revision
        last_exc: BaseException | None = None
        # One retry: a long-lived connection can sit in a reconnect loop and
        # time out even while a fresh socket reaches the controller.
        for attempt in range(2):
            try:
                loop = self._ensure_loop()
                future = asyncio.run_coroutine_threadsafe(self._request(subject, envelope), loop)
                # Budget covers one (re)connect plus the request itself.
                return future.result(timeout=self._timeout * 2)
            except ControlError:
                raise
            except Exception as exc:  # noqa: BLE001 — map transport failures
                last_exc = exc
                self._abandon_loop()
                if attempt == 0:
                    continue
        logger.warning(
            "rum control nats request failed failed_stage=request error_type=%s",
            type(last_exc).__name__ if last_exc else "unknown",
        )
        raise ControlError("unavailable", "RUM control NATS connection is unavailable") from last_exc

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            stale = self._loop is None or self._thread is None or not self._thread.is_alive() or self._pid != os.getpid()
            if stale:
                loop = asyncio.new_event_loop()
                thread = threading.Thread(target=loop.run_forever, name="rum-control-nats", daemon=True)
                thread.start()
                self._loop = loop
                self._thread = thread
                self._pid = os.getpid()
                self._nc = None
                self._connect_lock = asyncio.Lock()
            assert self._loop is not None
            return self._loop

    def _abandon_loop(self) -> None:
        with self._lock:
            loop = self._loop
            self._loop = None
            self._thread = None
            self._pid = None
            self._nc = None
            self._connect_lock = None
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(loop.stop)
        except RuntimeError:
            return

    async def _connection(self) -> Any:
        import nats

        assert self._connect_lock is not None
        async with self._connect_lock:
            nc = self._nc
            if nc is not None and nc.is_connected:
                return nc
            if nc is not None:
                self._nc = None
                try:
                    await nc.close()
                except Exception:  # noqa: BLE001 — stale socket; nothing to recover
                    pass
            nc = await nats.connect(self._url, connect_timeout=self._timeout)
            self._nc = nc
            return nc

    async def _request(self, subject: str, envelope: dict) -> tuple[int, Any]:
        from nats.errors import NoRespondersError

        nc = await self._connection()
        try:
            msg = await nc.request(subject, json.dumps(envelope).encode("utf-8"), timeout=self._timeout)
        except NoRespondersError as exc:
            raise ControlError("unavailable", "RUM controller has no running instance") from exc

        body = json.loads(msg.data.decode("utf-8"))
        if body.get("error"):
            err = body["error"]
            raise ControlError(str(err.get("code") or "internal_error"), str(err.get("message") or ""))
        return int(body.get("revision") or 0), body.get("data")


_control: ControlPlane | None = None


def get_control_plane() -> ControlPlane:
    global _control
    if _control is not None:
        return _control
    settings = load_rum_settings()
    if settings.nats_url:
        _control = NatsControlClient(settings.nats_url, settings.nats_timeout_seconds)
    else:
        _control = UnavailableControl()
    return _control


def set_control_plane(control: ControlPlane | None) -> None:
    """Test seam."""
    global _control
    _control = control
