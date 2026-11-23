from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from django.utils import timezone

from apps.rpc.system_mgmt import SystemMgmt
from apps.system_mgmt.models import User
from apps.workflow.atom_packages.runtime import trusted_execution_id, trusted_organization_id
from apps.workflow.models import ExecutionArtifact
from apps.workflow.services.object_store import MAX_ARTIFACT_DOWNLOAD_BYTES
from apps.workflow.services.report_links import build_report_download_link


def _is_absolute_http_url(value: str) -> bool:
    parts = urlsplit(value)
    return parts.scheme in {"http", "https"} and bool(parts.hostname)


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _artifact_links(inputs: dict[str, Any], team: int, execution_id: str) -> list[dict[str, str]]:
    refs = inputs.get("artifacts", [])
    if not isinstance(refs, list) or len(refs) > 10:
        raise ValueError("通知附件最多支持 10 个文件引用")
    if inputs.get("report_artifact"):
        refs = [*refs, inputs["report_artifact"]]
    if not refs:
        return []
    if not execution_id:
        raise ValueError("原子缺少可信执行上下文")
    try:
        ids = list(dict.fromkeys(UUID(str(ref["id"])) for ref in refs))
    except (ValueError, TypeError, KeyError) as error:
        raise ValueError("报告文件引用非法") from error
    if len(ids) > 10:
        raise ValueError("通知附件最多支持 10 个文件引用")
    records = ExecutionArtifact.objects.filter(
        team=[team], deleted_at__isnull=True, expires_at__gt=timezone.now(), size__lte=MAX_ARTIFACT_DOWNLOAD_BYTES
    ).in_bulk(ids)
    links = []
    for artifact_id in ids:
        artifact = records.get(artifact_id)
        if artifact is None:
            raise ValueError("报告文件不存在或无权访问")
        if str(artifact.execution_id) != execution_id:
            raise ValueError("报告文件不属于当前执行")
        links.append(
            {
                "id": str(artifact.id),
                "filename": artifact.filename,
                "url": build_report_download_link(artifact_id=str(artifact.id), execution_id=execution_id, team=team),
            }
        )
    return links


def _resolve_recipients(recipients: list[Any], team: int) -> list[str]:
    """Normalize designer values to system_user ids expected by notification dispatch."""
    if len(recipients) > 100:
        raise ValueError("recipients 最多支持 100 个收件人")
    resolved: list[str] = []
    for item in recipients:
        value = str(item).strip()
        if not value or len(value) > 255:
            raise ValueError("通知接收人无效")
        if value.isdigit():
            resolved.append(value)
            continue
        user = User.objects.filter(disabled=False, username=value).only("id", "group_list").first()
        if user is None:
            raise ValueError("通知接收人不存在或已失效")
        group_ids = {str(entry.get("id") if isinstance(entry, dict) else entry) for entry in (user.group_list or [])}
        if str(team) not in group_ids:
            raise ValueError("通知接收人不存在或已失效")
        resolved.append(str(user.id))
    return resolved


def _default_email_recipients(inputs: dict[str, Any]) -> list[str]:
    """邮件未配置收件人时回落到本次执行启动人（与内置流程 actor 引用一致）。"""
    context = inputs.get("__bklite_context")
    actor = context.get("actor") if isinstance(context, dict) else None
    if not isinstance(actor, dict):
        actor = inputs.get("actor") if isinstance(inputs.get("actor"), dict) else {}
    username = str(actor.get("username") or "").strip()
    return [username] if username else []


def execute(inputs: dict[str, Any]) -> dict[str, Any]:
    team = trusted_organization_id(inputs)
    execution_id = trusted_execution_id(inputs, required=False)
    notification_type = str(inputs.get("notification_type") or "EMAIL")
    raw_recipients = inputs.get("recipients") or []
    if not isinstance(raw_recipients, list):
        raise ValueError("recipients 最多支持 100 个收件人")
    if notification_type == "EMAIL" and not raw_recipients:
        raw_recipients = _default_email_recipients(inputs)
    recipients = _resolve_recipients(raw_recipients, team)
    if notification_type == "EMAIL" and not recipients:
        raise ValueError("邮件通知必须选择收件人")
    if notification_type == "EMAIL" and (inputs.get("channel_id") in (None, "")):
        raise ValueError("邮件通知必须选择通知方式")
    title = _as_text(inputs.get("title")).strip()
    body = _as_text(inputs.get("body")).strip()
    links = _artifact_links(inputs, team, execution_id)
    report_link = ""
    if links and notification_type == "EMAIL" and not inputs.get("artifacts"):
        # 内置巡检流程沿用单报告邮件；未配置站点地址时仍允许投递原邮件正文。
        url = links.pop()["url"]
        report_link = url if _is_absolute_http_url(url) else ""
    if any(not _is_absolute_http_url(link["url"]) for link in links):
        raise ValueError("发送附件下载链接需要配置 WEB_BASE_URL")
    message_length = len(body) + sum(len(link["filename"]) + len(link["url"]) + 4 for link in links)
    if (notification_type == "EMAIL" and not title) or len(title) > 200 or not body or message_length > 10000:
        raise ValueError("通知标题或正文超出限额")
    delivery = SystemMgmt().dispatch_notification(
        delivery_key=f"workflow:{execution_id}:{inputs.get('task_reference') or 'notification'}"[:255],
        channel_id=inputs.get("channel_id"),
        organization_ids=[team],
        recipients=recipients,
        title=title,
        body=body,
        event_payload={
            "execution_id": execution_id,
            "notification_type": notification_type,
            "report_link": report_link,
            **({"artifact_links": links} if links else {}),
            "debug": bool(inputs.get("debug")),
        },
        producer="workflow",
        internal_caller="workflow",
    )
    if not isinstance(delivery, dict) or delivery.get("result") is not True:
        message = delivery.get("message") if isinstance(delivery, dict) else ""
        raise ValueError(str(message or "通知渠道投递失败"))
    return {"delivery": delivery}
