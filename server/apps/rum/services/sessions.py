from __future__ import annotations

import time
from typing import Any

from apps.core.logger import rum_logger as logger
from apps.rum.services.analytics import Analytics, get_analytics
from apps.rum.services.control import ControlError, ControlPlane, get_control_plane
from apps.rum.services.health import EnabledApplications, list_enabled_applications
from apps.rum.services.query import (
    empty_replay_manifest,
    empty_session_journey,
    empty_session_list,
    empty_session_trend,
    parse_range_params,
    stamp_pipeline_flags,
)
from apps.rum.services.replay import ReplayIndex, get_replay_index, sign_payload, verify_payload
from apps.rum.services.settings import load_rum_settings
from apps.rum.services.validation import ValidationError, valid_application


class SessionsService:
    def __init__(
        self,
        control: ControlPlane | None = None,
        analytics: Analytics | None = None,
        replay_index: ReplayIndex | None = None,
    ):
        self.control = control or get_control_plane()
        self.analytics = analytics or get_analytics()
        self.replay_index = replay_index or get_replay_index()
        self.settings = load_rum_settings()

    def _resolve_applications(self, actor: str, requested: list[str]) -> EnabledApplications:
        return list_enabled_applications(self.control, actor, requested)

    def _requested_apps(self, params: dict[str, Any]) -> list[str]:
        apps: list[str] = []
        single = (params.get("application") or "").strip()
        if single:
            apps.append(single)
        multi = params.get("applications")
        if isinstance(multi, str) and multi.strip():
            apps.extend([part.strip() for part in multi.split(",") if part.strip()])
        elif isinstance(multi, list):
            apps.extend([str(part).strip() for part in multi if str(part).strip()])
        return apps

    def list_sessions(self, actor: str, params: dict[str, Any]) -> dict:
        try:
            start, end = parse_range_params(params)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        found = self._resolve_applications(actor, self._requested_apps(params))
        if found.control_down and found.catalog_empty:
            return empty_session_list(reason="control")
        if not self.analytics.available():
            return stamp_pipeline_flags(empty_session_list(reason="analytics"), control=found.control_down)
        opts = {
            "from": start,
            "to": end,
            "applications": found.applications,
            "sessionId": params.get("sessionId") or "",
            "sessionIdPrefix": params.get("sessionIdPrefix") or "",
            "route": params.get("route") or "",
            "userId": params.get("userId") or "",
            "device": params.get("device") or "",
            "browser": params.get("browser") or "",
            "country": params.get("country") or "",
            "hasError": params.get("hasError") in {"1", "true", True},
            "hasReplay": params.get("hasReplay") in {"1", "true", True},
            "traffic": params.get("traffic") or "visitors",
            "orderBy": params.get("orderBy") or "impact",
            "limit": int(params.get("limit") or 0),
            "offset": int(params.get("offset") or 0),
        }
        try:
            if opts["hasReplay"] and self.replay_index.available():
                return stamp_pipeline_flags(self._list_replay_sessions(opts), control=found.control_down)
            page = self.analytics.list_sessions(self.settings.tenant_id, opts)
        except Exception as exc:  # noqa: BLE001 — degrade; do not 500 the BFF
            logger.warning(
                "rum sessions list analytics failed failed_stage=list_sessions error_type=%s",
                type(exc).__name__,
            )
            return stamp_pipeline_flags(empty_session_list(reason="analytics"), control=found.control_down)
        if self.replay_index.available() and page.get("sessions"):
            ready = self._ready_sessions(page["sessions"])
            replayed = 0
            for row in page["sessions"]:
                has = _session_pair(row) in ready
                row["hasReplay"] = has
                if has:
                    replayed += 1
            page.setdefault("summary", {})["replayed"] = replayed
        return stamp_pipeline_flags(page, control=found.control_down)

    def _ready_sessions(self, rows: list[dict]) -> set[tuple[str, str]]:
        return self.replay_index.ready_sessions([_session_pair(row) for row in rows])

    def _list_replay_sessions(self, opts: dict) -> dict:
        page_limit = int(opts.get("limit") or 0) or 200
        page_offset = max(0, int(opts.get("offset") or 0))
        needed = page_offset + page_limit
        matched: list[dict] = []
        scanned = 0
        truncated = False
        exhausted = False
        while scanned < 2000 and len(matched) < needed:
            chunk = self.analytics.list_sessions(
                self.settings.tenant_id,
                {**opts, "hasReplay": False, "includeSummary": False, "limit": 200, "offset": scanned},
            )
            rows = chunk.get("sessions") or []
            if not rows:
                exhausted = True
                break
            ready = self._ready_sessions(rows)
            for row in rows:
                if scanned >= 2000:
                    truncated = True
                    break
                if len(matched) >= needed:
                    break
                scanned += 1
                has = _session_pair(row) in ready
                row["hasReplay"] = bool(has)
                if has:
                    matched.append(row)
            if truncated:
                break
            if len(rows) < 200:
                exhausted = True
                break
        if scanned >= 2000 and not exhausted:
            truncated = True
        visible = matched[page_offset : page_offset + page_limit]
        page = {"sessions": visible, "replayScanTruncated": truncated}
        if not truncated and exhausted:
            errored = sum(1 for row in matched if int(row.get("errorCount") or 0) > 0)
            page["summary"] = {
                "total": len(matched),
                "errored": errored,
                "replayed": len(matched),
                "medianDurationMs": 0,
            }
        return page

    def session_trend(self, actor: str, params: dict[str, Any]) -> dict:
        try:
            start, end = parse_range_params(params)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        found = self._resolve_applications(actor, self._requested_apps(params))
        if found.control_down and found.catalog_empty:
            return empty_session_trend(reason="control")
        if not self.analytics.available():
            return stamp_pipeline_flags(empty_session_trend(reason="analytics"), control=found.control_down)
        opts = {
            "from": start,
            "to": end,
            "applications": found.applications,
            "route": params.get("route") or "",
            "userId": params.get("userId") or "",
            "device": params.get("device") or "",
            "browser": params.get("browser") or "",
            "country": params.get("country") or "",
            "hasError": params.get("hasError") in {"1", "true", True},
            "hasReplay": params.get("hasReplay") in {"1", "true", True},
            "traffic": params.get("traffic") or "visitors",
        }
        try:
            page = self.analytics.session_trend(self.settings.tenant_id, opts)
        except Exception as exc:  # noqa: BLE001 — degrade; do not 500 the BFF
            logger.warning(
                "rum sessions trend analytics failed failed_stage=session_trend error_type=%s",
                type(exc).__name__,
            )
            return stamp_pipeline_flags(empty_session_trend(reason="analytics"), control=found.control_down)
        return stamp_pipeline_flags(page, control=found.control_down)

    def get_session(self, actor: str, session_id: str, params: dict[str, Any]) -> dict:
        application = (params.get("application") or "").strip()
        if not application or not valid_application(application) or not session_id:
            raise ValidationError("application and sessionId are required")
        try:
            start, end = parse_range_params(params)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        found = self._resolve_applications(actor, [application])
        if found.control_down and found.catalog_empty:
            return empty_session_journey(reason="control")
        if not self.analytics.available():
            return stamp_pipeline_flags(empty_session_journey(reason="analytics"), control=found.control_down)
        if application not in found.applications:
            raise ControlError("not_found", "application not found")
        journey = self.analytics.session_journey(
            self.settings.tenant_id,
            application,
            session_id,
            {"from": start, "to": end},
        )
        session = journey.get("session") or {}
        if not session.get("sessionId"):
            raise ControlError("not_found", "session not found")
        return stamp_pipeline_flags(journey, control=found.control_down)

    def replay_manifest(self, actor: str, params: dict[str, Any]) -> dict:
        application = (params.get("application") or "").strip()
        session = (params.get("session") or "").strip()
        if not application or not session:
            raise ValidationError("application and session are required")
        if not valid_application(application):
            raise ValidationError("invalid application")
        found = list_enabled_applications(self.control, actor)
        if application not in found.applications:
            if found.control_down and found.catalog_empty:
                return empty_replay_manifest(reason="control")
            raise ControlError("not_found", "application not found")
        if not self.replay_index.available():
            return stamp_pipeline_flags(empty_replay_manifest(reason="analytics"), control=found.control_down)
        manifest = self.replay_index.replay_manifest(self.settings.tenant_id, application, session)
        for recording in manifest.get("recordings") or []:
            for segment in recording.get("segments") or []:
                object_key = segment.pop("objectKey", "") or ""
                if object_key:
                    segment["ref"] = sign_payload(
                        "ref",
                        {
                            "application": application,
                            "session": session,
                            "objectKey": object_key,
                        },
                    )
                else:
                    segment["ref"] = segment.get("ref") or ""
        return stamp_pipeline_flags(manifest, control=found.control_down)

    def replay_grant(self, actor: str, body: dict) -> dict:
        application = (body.get("application") or "").strip()
        session = (body.get("session") or "").strip()
        target_ref = (body.get("targetRef") or "").strip()
        if not application or not session or not target_ref:
            raise ValidationError("application, session and targetRef are required")
        found = list_enabled_applications(self.control, actor)
        if application not in found.applications:
            if found.control_down and found.catalog_empty:
                return {"controlUnavailable": True}
            raise ControlError("not_found", "application not found")
        claims = verify_payload(target_ref, "ref")
        if not claims or claims.get("application") != application or claims.get("session") != session or not claims.get("objectKey"):
            raise ValidationError("invalid targetRef")
        expires = int(time.time() * 1000) + 5 * 60 * 1000
        token = sign_payload(
            "segment",
            {
                "application": application,
                "session": session,
                "objectKey": claims["objectKey"],
                "expiresAtMs": expires,
            },
        )
        return {
            "targetRef": target_ref,
            "targetIncluded": True,
            "segments": [
                {
                    "ref": target_ref,
                    "sequence": 0,
                    "url": f"/api/v1/rum/replay/segments/{token}",
                    "expiresAtMs": expires,
                }
            ],
        }

    def replay_segment_claims(self, token: str) -> dict:
        claims = verify_payload(token, "segment")
        if not claims:
            raise ControlError("forbidden", "invalid or expired replay segment token")
        return claims


def _session_pair(row: dict) -> tuple[str, str]:
    return (row.get("application") or "", row.get("sessionId") or "")
