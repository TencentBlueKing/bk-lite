"""Publish durable RUM projection outbox rows to the controller."""

from __future__ import annotations

from django.utils import timezone

from apps.core.logger import rum_logger as logger
from apps.rum.constants import (
    SUBJECT_ERASURE_FENCE_RELEASE,
    SUBJECT_ERASURE_SUBMIT,
    SUBJECT_PROJECTION_APPLY,
    SUBJECT_PROJECTION_RECONCILE,
)
from apps.rum.services.control import get_control_plane


class PublishService:
    def __init__(self, control=None):
        self.control = control or get_control_plane()

    def publish(self, outbox_id: str) -> tuple[bool, object]:
        from apps.rum.models import RumProjectionOutbox

        row = RumProjectionOutbox.objects.filter(id=outbox_id).first()
        if row is None:
            return False, None
        if row.status == "published":
            return True, row.payload_json
        try:
            _revision, data = self._send(row)
        except Exception as exc:
            row.attempts += 1
            row.last_error_type = type(exc).__name__
            row.save(update_fields=["attempts", "last_error_type", "updated_at"])
            logger.warning(
                "rum projection publish failed outbox_id=%s failed_stage=%s error_type=%s",
                row.id,
                "publish",
                type(exc).__name__,
            )
            return False, None
        row.status = "published"
        row.published_at = timezone.now()
        row.last_error_type = ""
        row.save(update_fields=["status", "published_at", "last_error_type", "updated_at"])
        return True, data

    def reconcile(self) -> None:
        from apps.rum.models import RumApplication, RumEraseJob

        applications = [
            {"application": row.name, "revision": int(row.revision)}
            for row in RumApplication.objects.all().order_by("name")
        ]
        fences = []
        open_jobs = RumEraseJob.objects.exclude(status__in=["completed", "failed"]).order_by("created_at")
        for job in open_jobs:
            result = job.result_json if isinstance(job.result_json, dict) else {}
            identities = result.get("identities") or [{"kind": "user", "value": job.end_user_id}]
            fences.append({"application": job.application, "identities": identities})
        _revision, data = self.control.request(
            SUBJECT_PROJECTION_RECONCILE,
            "system",
            {"applications": applications, "fences": fences},
        )
        stale = data.get("staleApplications") if isinstance(data, dict) else []
        for name in stale or []:
            self._republish_application(str(name), force=True)

    def _republish_application(self, name: str, *, force: bool = False) -> None:
        from apps.rum.models import RumApplication, RumApplicationKey, RumApplicationOrigin

        app = RumApplication.objects.filter(name=name).first()
        if app is None:
            return
        origins = list(
            RumApplicationOrigin.objects.filter(application=name).order_by("origin").values_list("origin", flat=True)
        )
        digests = list(
            RumApplicationKey.objects.filter(application=name, status="active")
            .order_by("created_at")
            .values_list("key_digest", flat=True)
        )
        payload = {
            "application": app.name,
            "tenantId": app.tenant_id,
            "orgId": app.org_id,
            "enabled": app.enabled,
            "revision": int(app.revision),
            "budgets": {
                "requestsPerMinute": int(app.requests_per_minute),
                "compressedBytesPerMinute": int(app.compressed_bytes_per_minute),
                "decompressedBytesPerMinute": int(app.decompressed_bytes_per_minute),
                "eventsPerMinute": int(app.events_per_minute),
            },
            "origins": origins,
            "browserKeyDigests": digests,
        }
        if force:
            payload["force"] = True
        try:
            self.control.request(SUBJECT_PROJECTION_APPLY, "system", payload, expected_revision=int(app.revision))
        except Exception as exc:
            logger.warning(
                "rum projection reconcile republish failed application=%s failed_stage=%s error_type=%s",
                name,
                "reconcile",
                type(exc).__name__,
            )

    def _send(self, row) -> tuple[int, object]:
        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        if row.kind == "application":
            return self.control.request(SUBJECT_PROJECTION_APPLY, "system", payload, expected_revision=int(row.revision))
        if row.kind == "fence_add":
            return self.control.request(
                SUBJECT_ERASURE_SUBMIT,
                "system",
                payload,
                expected_revision=int(payload.get("expectedRevision") or row.revision or 0),
            )
        if row.kind == "fence_release":
            return self.control.request(SUBJECT_ERASURE_FENCE_RELEASE, "system", payload)
        raise ValueError(f"unsupported outbox kind {row.kind}")
