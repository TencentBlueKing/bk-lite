from __future__ import annotations

import time
from typing import Any

from apps.rum.constants import SUBJECT_APPLICATION_LIST
from apps.rum.services.analytics import Analytics, get_analytics
from apps.rum.services.control import ControlError, ControlPlane, control_unavailable, get_control_plane
from apps.rum.services.query import empty_replay_manifest, empty_session_journey, empty_session_list, empty_session_trend, parse_range_params
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

    def _list_enabled_apps(self, actor: str) -> tuple[list[str], str | None]:
        try:
            _, data = self.control.request(SUBJECT_APPLICATION_LIST, actor, {})
        except ControlError as exc:
            if control_unavailable(exc):
                return [], "control"
            raise
        registry = data if isinstance(data, list) else []
        enabled = [item.get("application") for item in registry if item.get("application") and item.get("enabled", True)]
        return enabled, None

    def _resolve_applications(self, actor: str, requested: list[str]) -> tuple[list[str], str | None]:
        enabled, reason = self._list_enabled_apps(actor)
        if reason:
            return [], reason
        if requested:
            scoped = [name for name in requested if name in enabled]
        else:
            scoped = enabled
        if not self.analytics.available():
            return scoped, "analytics"
        return scoped, None

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
        apps, reason = self._resolve_applications(actor, self._requested_apps(params))
        if reason == "control":
            return empty_session_list(reason="control")
        if reason == "analytics":
            return empty_session_list(reason="analytics")
        opts = {
            "from": start,
            "to": end,
            "applications": apps,
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
        page = self.analytics.list_sessions(self.settings.tenant_id, opts)
        if self.replay_index.available() and page.get("sessions"):
            replayed = 0
            for row in page["sessions"]:
                has = self.replay_index.has_ready(row.get("application", ""), row.get("sessionId", ""))
                row["hasReplay"] = has
                if has:
                    replayed += 1
            page.setdefault("summary", {})["replayed"] = replayed
            if opts["hasReplay"]:
                page["sessions"] = [row for row in page["sessions"] if row.get("hasReplay")]
        return page

    def session_trend(self, actor: str, params: dict[str, Any]) -> dict:
        try:
            start, end = parse_range_params(params)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        apps, reason = self._resolve_applications(actor, self._requested_apps(params))
        if reason == "control":
            return empty_session_trend(reason="control")
        if reason == "analytics":
            return empty_session_trend(reason="analytics")
        opts = {
            "from": start,
            "to": end,
            "applications": apps,
            "route": params.get("route") or "",
            "userId": params.get("userId") or "",
            "device": params.get("device") or "",
            "browser": params.get("browser") or "",
            "country": params.get("country") or "",
            "hasError": params.get("hasError") in {"1", "true", True},
            "hasReplay": params.get("hasReplay") in {"1", "true", True},
            "traffic": params.get("traffic") or "visitors",
        }
        return self.analytics.session_trend(self.settings.tenant_id, opts)

    def get_session(self, actor: str, session_id: str, params: dict[str, Any]) -> dict:
        application = (params.get("application") or "").strip()
        if not application or not valid_application(application) or not session_id:
            raise ValidationError("application and sessionId are required")
        try:
            start, end = parse_range_params(params)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        apps, reason = self._resolve_applications(actor, [application])
        if reason == "control":
            return empty_session_journey(reason="control")
        if reason == "analytics":
            return empty_session_journey(reason="analytics")
        if application not in apps:
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
        return journey

    def replay_manifest(self, actor: str, params: dict[str, Any]) -> dict:
        application = (params.get("application") or "").strip()
        session = (params.get("session") or "").strip()
        if not application or not session:
            raise ValidationError("application and session are required")
        if not valid_application(application):
            raise ValidationError("invalid application")
        enabled, reason = self._list_enabled_apps(actor)
        if reason == "control":
            return empty_replay_manifest(reason="control")
        if application not in enabled:
            raise ControlError("not_found", "application not found")
        if not self.replay_index.available():
            return empty_replay_manifest(reason="analytics")
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
        return manifest

    def replay_grant(self, actor: str, body: dict) -> dict:
        application = (body.get("application") or "").strip()
        session = (body.get("session") or "").strip()
        target_ref = (body.get("targetRef") or "").strip()
        if not application or not session or not target_ref:
            raise ValidationError("application, session and targetRef are required")
        enabled, reason = self._list_enabled_apps(actor)
        if reason == "control":
            return {"controlUnavailable": True}
        if application not in enabled:
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
