from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from apps.core.logger import rum_logger as logger
from apps.rum.constants import OPERATION_TERMINAL_STATUSES, SUBJECT_APPLICATION_GET, SUBJECT_ERASURE_SUBMIT, SUBJECT_OPERATION_GET
from apps.rum.services.control import ControlError, ControlPlane, control_unavailable, get_control_plane
from apps.rum.services.validation import ValidationError, valid_application

# Upper bound on controller lookups a single ledger listing may trigger.
MAX_STATUS_REFRESH_PER_LIST = 50


class EraseJobStore(Protocol):
    def list(
        self,
        *,
        application: str = "",
        end_user_id: str = "",
        limit: int = 200,
    ) -> list[dict]:
        ...

    def create(self, job: dict) -> dict:
        ...

    def update_status(self, job_id: str, status: str, result: dict) -> dict | None:
        ...


class MemoryEraseJobStore:
    def __init__(self):
        self._items: list[dict] = []

    def list(
        self,
        *,
        application: str = "",
        end_user_id: str = "",
        limit: int = 200,
    ) -> list[dict]:
        rows = list(self._items)
        if application and application != "all":
            rows = [row for row in rows if row.get("application") == application]
        if end_user_id:
            needle = end_user_id.strip().lower()
            rows = [row for row in rows if needle in str(row.get("endUserId") or "").lower()]
        return [dict(row) for row in rows[: max(1, min(limit, 500))]]

    def create(self, job: dict) -> dict:
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        item = {
            "id": job.get("id") or f"erase-{len(self._items) + 1}",
            "application": job["application"],
            "endUserId": job["endUserId"],
            "scope": job.get("scope") or "all",
            "status": job.get("status") or "accepted",
            "requestedBy": job.get("requestedBy") or "",
            "result": dict(job.get("result") or {}),
            "createdAt": job.get("createdAt") or now,
            "updatedAt": job.get("updatedAt") or now,
        }
        self._items.insert(0, item)
        return dict(item)

    def update_status(self, job_id: str, status: str, result: dict) -> dict | None:
        for item in self._items:
            if item["id"] == job_id:
                item["status"] = status
                item["result"] = dict(result)
                item["updatedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                return dict(item)
        return None


class DjangoEraseJobStore:
    def list(
        self,
        *,
        application: str = "",
        end_user_id: str = "",
        limit: int = 200,
    ) -> list[dict]:
        from apps.rum.models import RumEraseJob

        qs = RumEraseJob.objects.all().order_by("-created_at")
        if application and application != "all":
            qs = qs.filter(application=application)
        if end_user_id:
            qs = qs.filter(end_user_id__icontains=end_user_id.strip())
        limit = max(1, min(int(limit or 200), 500))
        return [_serialize(item) for item in qs[:limit]]

    def create(self, job: dict) -> dict:
        from apps.rum.models import RumEraseJob

        item = RumEraseJob(
            application=job["application"],
            end_user_id=job["endUserId"],
            status=job.get("status") or "accepted",
            requested_by=job.get("requestedBy") or "",
            result_json=dict(job.get("result") or {}),
        )
        if job.get("id"):
            item.id = job["id"]
        item.save()
        return _serialize(item)

    def update_status(self, job_id: str, status: str, result: dict) -> dict | None:
        from apps.rum.models import RumEraseJob

        item = RumEraseJob.objects.filter(id=job_id).first()
        if item is None:
            return None
        item.status = status
        item.result_json = dict(result)
        item.save(update_fields=["status", "result_json", "updated_at"])
        return _serialize(item)


def _serialize(item) -> dict:
    created = item.created_at
    updated = item.updated_at
    return {
        "id": item.id,
        "application": item.application,
        "endUserId": item.end_user_id,
        "scope": "all",
        "status": item.status,
        "requestedBy": item.requested_by,
        "result": dict(item.result_json or {}),
        "createdAt": created.isoformat().replace("+00:00", "Z") if created else None,
        "updatedAt": updated.isoformat().replace("+00:00", "Z") if updated else None,
    }


class ComplianceService:
    def __init__(
        self,
        control: ControlPlane | None = None,
        store: EraseJobStore | None = None,
    ):
        self.control = control or get_control_plane()
        self.store = store or DjangoEraseJobStore()

    def list_jobs(self, params: dict[str, Any] | None = None, actor: str = "") -> list[dict]:
        params = params or {}
        try:
            limit = int(params.get("limit") or 200)
        except (TypeError, ValueError) as exc:
            raise ValidationError("invalid limit") from exc
        jobs = self.store.list(
            application=(params.get("application") or "").strip(),
            end_user_id=(params.get("endUserId") or params.get("q") or "").strip(),
            limit=limit,
        )
        return self._refresh_statuses(actor, jobs)

    def _refresh_statuses(self, actor: str, jobs: list[dict]) -> list[dict]:
        """Pull the controller's current status for ledger rows still in flight.

        The submit call only records that the controller accepted the erasure;
        the maintainer finishes it asynchronously. Listing is the natural point
        to reconcile, bounded so one page cannot fan out into unbounded NATS
        requests. Controller outages leave the stored status untouched.
        """
        refreshed = 0
        out: list[dict] = []
        for job in jobs:
            if refreshed >= MAX_STATUS_REFRESH_PER_LIST or job.get("status") in OPERATION_TERMINAL_STATUSES:
                out.append(job)
                continue
            operation_id = str((job.get("result") or {}).get("operationId") or "").strip()
            if not operation_id:
                out.append(job)
                continue
            refreshed += 1
            try:
                _, data = self.control.request(SUBJECT_OPERATION_GET, actor or "system", {"operationId": operation_id})
            except ControlError as exc:
                if control_unavailable(exc):
                    out.append(job)
                    continue
                if exc.code == "not_found":
                    # Operation record expired or was never persisted; keep the
                    # ledger row but stop polling it.
                    updated = self.store.update_status(job["id"], "failed", {**(job.get("result") or {}), "error": "operation not found"})
                    out.append(updated or job)
                    continue
                logger.warning("rum erase ledger refresh failed job_id=%s error_code=%s", job.get("id"), exc.code)
                out.append(job)
                continue
            operation = data if isinstance(data, dict) else {}
            status = str(operation.get("status") or "").strip()
            if not status or status == job.get("status"):
                out.append(job)
                continue
            updated = self.store.update_status(job["id"], status, {**(job.get("result") or {}), **operation})
            out.append(updated or job)
        return out

    def erase(self, actor: str, body: dict) -> tuple[int, dict]:
        application = (body.get("application") or "").strip()
        end_user_id = (body.get("endUserId") or "").strip()
        if not application or not end_user_id:
            raise ValidationError("application and endUserId are required")
        if not valid_application(application):
            raise ValidationError("invalid application")
        if len(end_user_id) > 256:
            raise ValidationError("endUserId is too long")

        # Controller SubmitOperation requires expectedRevision matching the
        # application registry revision (optimistic concurrency). Fetch it
        # first so the console erase path does not omit the envelope field.
        try:
            _, app = self.control.request(SUBJECT_APPLICATION_GET, actor, {"application": application})
        except ControlError as exc:
            if control_unavailable(exc):
                raise ControlError("unavailable", "RUM controller is unavailable") from exc
            raise
        if not isinstance(app, dict) or not app.get("enabled", True):
            raise ControlError("not_found", "application not found")

        revision, data = self.control.request(
            SUBJECT_ERASURE_SUBMIT,
            actor,
            {
                "application": application,
                "identities": [{"kind": "user", "value": end_user_id}],
            },
            expected_revision=int(app.get("revision") or 0),
        )
        result = data if isinstance(data, dict) else {"data": data}
        job = self.store.create(
            {
                "application": application,
                "endUserId": end_user_id,
                "scope": "all",
                "status": str(result.get("status") or "accepted"),
                "requestedBy": actor,
                "result": result,
            }
        )
        # Upstream returns the control-plane operation payload; BK-Lite also attaches
        # the durable ledger record so the console can stop using localStorage.
        response = dict(result)
        response["ledger"] = job
        return revision, response
