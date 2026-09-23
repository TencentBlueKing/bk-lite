from __future__ import annotations

import time

from apps.rum.constants import EVIDENCE_WINDOW_SECONDS


def layer_status(at: int, now: int | None = None) -> dict:
    now = int(now if now is not None else time.time())
    at = int(at or 0)
    if at > 0 and now - at <= EVIDENCE_WINDOW_SECONDS:
        return {"state": "ok", "at": at}
    payload = {"state": "waiting"}
    if at:
        payload["at"] = at
    return payload


def build_status(view: dict | None, *, application: str, now: int | None = None, controller_unreachable: bool = False) -> dict:
    now = int(now if now is not None else time.time())
    if controller_unreachable or view is None:
        return {
            "application": application,
            "status": "waiting",
            "gateway": {"state": "waiting"},
            "store": {"state": "waiting"},
            "controllerUnreachable": True,
            "checkedAt": now,
        }
    gateway = layer_status(int(view.get("lastAcceptedAt") or 0), now)
    store = layer_status(int(view.get("lastStoredAt") or 0), now)
    enabled = bool(view.get("enabled"))
    if not enabled:
        status = "disabled"
    elif gateway["state"] == "ok" and store["state"] == "ok":
        status = "connected"
    else:
        status = "waiting"
    return {
        "application": view.get("application") or application,
        "enabled": enabled,
        "status": status,
        "gateway": gateway,
        "store": store,
        "checkedAt": now,
    }
