from __future__ import annotations

import json
from typing import Any

from apps.rpc.system_mgmt import SystemMgmt
from apps.system_mgmt.models import User
from apps.workflow.atom_packages.runtime import trusted_execution_id, trusted_organization_id
from apps.workflow.models import ExecutionArtifact
from apps.workflow.services.report_links import build_report_download_link


def _is_absolute_http_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _report_link(inputs: dict[str, Any], team: int, execution_id: str) -> str:
    artifact_ref = inputs.get("report_artifact")
    if not artifact_ref:
        return ""
    if not isinstance(artifact_ref, dict) or not str(artifact_ref.get("id") or ""):
        raise ValueError("报告文件引用非法")
    artifact = ExecutionArtifact.objects.filter(pk=str(artifact_ref["id"])).first()
    if artifact is None or artifact.team != [team]:
        raise ValueError("报告文件不存在或无权访问")
    if execution_id and str(artifact.execution_id) != execution_id:
        raise ValueError("报告文件不属于当前执行")
    return build_report_download_link(
        artifact_id=str(artifact.id),
        execution_id=str(artifact.execution_id),
        team=team,
    )


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
    report_link = _report_link(inputs, team, execution_id)
    if report_link and notification_type != "EMAIL":
        body = f"{body}\n报告下载（24 小时内有效）：{report_link}"
    elif report_link and notification_type == "EMAIL" and not _is_absolute_http_url(report_link):
        # 未配置 WEB_BASE_URL 时链接不是绝对地址，渠道不会把它写成可点击下载。邮件正文仍要发出。
        report_link = ""
    if (notification_type == "EMAIL" and not title) or len(title) > 200 or not body or len(body) > 10000:
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
            "debug": bool(inputs.get("debug")),
        },
        producer="workflow",
        internal_caller="workflow",
    )
    if not isinstance(delivery, dict) or delivery.get("result") is not True:
        message = delivery.get("message") if isinstance(delivery, dict) else ""
        raise ValueError(str(message or "通知渠道投递失败"))
    return {"delivery": delivery}
