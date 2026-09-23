from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Protocol
from urllib.parse import quote

from apps.core.logger import rum_logger as logger

NOTIFY_FIRE = "fire"
NOTIFY_RECOVER = "recover"
NOTIFY_RENOTIFY = "renotify"

_DEFAULT_TITLE = "[{{alert.severity}}] {{object.name}} {{alert.kind}}={{alert.value}}（阈 {{alert.threshold}}）"
_DEFAULT_BODY = "{{alert.name}}\n{{object.name}} {{alert.kind}}={{alert.value}}"
_MUSTACHE = re.compile(r"\{\{([a-zA-Z0-9_.]+)\}\}")


def render_template(tpl: str, vars: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        value = (vars.get(key) or "").strip()
        return value if value else "—"

    out = _MUSTACHE.sub(repl, tpl)
    return _MUSTACHE.sub("—", out)


def format_num(value: float) -> str:
    text = f"{value:.12g}"
    return text


def template_vars(policy: dict, event: dict | None, status: str, now: datetime) -> dict[str, str]:
    value = ""
    if event is not None and event.get("metricValue") is not None:
        value = format_num(float(event["metricValue"]))
    severity = policy.get("severity") or "warning"
    if event and (event.get("severity") or "").strip():
        severity = event["severity"]
    comparator = (policy.get("comparator") or ">=").strip() or ">="
    object_name = (policy.get("application") or policy.get("name") or "").strip()
    link = "/rum/alert-events"
    if event and event.get("id"):
        link = f"/rum/alert-events/{event['id']}"
    return {
        "alert.name": policy.get("name") or "",
        "alert.severity": severity,
        "alert.status": status,
        "alert.kind": policy.get("metric") or "",
        "alert.value": value,
        "alert.threshold": comparator + format_num(float(policy.get("criticalThreshold") or 0)),
        "alert.baseline": "",
        "alert.change": value,
        "alert.consecutive": "1",
        "alert.time": now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "alert.link": link,
        "object.name": object_name,
    }


def render_message(policy: dict, event: dict | None, status: str, now: datetime) -> tuple[str, str]:
    vars = template_vars(policy, event, status, now)
    return render_template(_DEFAULT_TITLE, vars), render_template(_DEFAULT_BODY, vars)


class Notifier(Protocol):
    def send(self, channel_id: str, title: str, body: str) -> None:
        ...


class MemoryNotifier:
    def __init__(self):
        self.sent: list[dict] = []

    def send(self, channel_id: str, title: str, body: str) -> None:
        self.sent.append({"channelId": channel_id, "title": title, "body": body})


class SystemMgmtNotifier:
    def send(self, channel_id: str, title: str, body: str) -> None:
        from apps.monitor.utils.system_mgmt_api import SystemMgmtUtils

        SystemMgmtUtils.send_msg_with_channel(channel_id, title, body, [], internal_caller="lite-rum")


def deliver_notify(
    notifier: Notifier,
    policy: dict,
    event: dict,
    action: str,
    now: datetime | None = None,
) -> None:
    now = now or datetime.now(timezone.utc)
    channels = list(policy.get("notifyChannels") or [])
    if not channels:
        return
    status = "firing"
    if action == NOTIFY_RECOVER:
        status = "resolved"
    elif action == NOTIFY_RENOTIFY:
        status = "renotify"
    title, body = render_message(policy, event, status, now)
    for channel_id in channels:
        channel_id = str(channel_id).strip()
        if not channel_id:
            continue
        try:
            notifier.send(channel_id, title, body)
        except Exception as exc:
            logger.exception(
                "rum alert notify failed policy=%s event=%s channel=%s",
                policy.get("id"),
                event.get("id"),
                channel_id,
                extra={
                    "failed_stage": "notify_send",
                    "error_type": type(exc).__name__,
                },
            )


def overview_link(application: str) -> str:
    app = (application or "").strip()
    if not app:
        return "/rum/alerts"
    return f"/rum/applications/{quote(app, safe='')}/overview"
