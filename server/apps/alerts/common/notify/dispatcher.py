# -- coding: utf-8 --
"""通知收口出口(Q1)。

统一三处通知(分派/提醒/升级)的两段机械重复:
1. build_channel_params：把 (接收人, 渠道列表, 告警) 构建为 sync_notify 期望的 list[dict]，一渠道一条；
2. enqueue_notifications：统一投递时机——事务内则 on_commit 后投递，否则立即。

不统一"渠道选择"逻辑（分派用默认渠道、提醒用 assignment 渠道、升级用层级渠道，按场景不同，是合理差异）。
"""
import uuid
from typing import Any, Dict, List, Optional

from apps.alerts.common.notify.base import NotifyParamsFormat
from apps.alerts.notification_templates.binding import render_bound_template, select_template_id
from apps.core.logger import alert_logger as logger
from apps.system_mgmt.models.channel import ChannelChoices


def build_channel_params(
    username_list: List[str],
    channels: List[Dict[str, Any]],
    alerts: List,
    object_id: str,
    notify_action_object: str = "alert",
    title: Optional[str] = None,
    content: Optional[str] = None,
    scene: str = "assignment",
    notification_context: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """构建 sync_notify 入参(list[dict])。username_list 或 channels 为空 → 返回 []。

    opspilot 托管的 NATS 触发通道需要 dict content {message, team, user_ids}
    （title/receivers 被忽略），其中 team 是单一组织整数：仅当本次为单条告警且其
    归属组织非空时构造；否则跳过该 NATS 通道（聚合多告警/无组织无单一上下文）。
    其余通道沿用纯文本 content。
    """
    if not username_list or not channels:
        return []

    param_format = NotifyParamsFormat(username_list=username_list, alerts=alerts)
    default_values = None

    def get_default_values():
        nonlocal default_values
        if default_values is None:
            default_title = param_format.format_title() if title is None else title
            if title is None and scene == "recovery":
                default_title = f"【恢复】{default_title}"
            default_values = (
                default_title,
                param_format.format_content() if content is None else content,
            )
        return default_values

    # NATS 触发只接受单个组织上下文；单条告警时取其归属组织(告警必定单一组织)
    nats_team = None
    if len(alerts) == 1:
        alert_team = getattr(alerts[0], "team", None) or []
        if alert_team:
            nats_team = alert_team[0]

    params: List[Dict[str, Any]] = []
    for channel in channels:
        channel_title = None
        channel_content = None
        append_receivers = True
        template_snapshot = None
        template_id = select_template_id(channel, scene)
        if template_id is not None and len(alerts) == 1 and title is None and content is None:
            try:
                rendered = render_bound_template(
                    template_id,
                    channel["channel_type"],
                    alerts[0],
                    username_list,
                    scene,
                    notification_context=notification_context,
                )
                channel_title = rendered.title
                channel_content = rendered.content
                append_receivers = False
                template_snapshot = {
                    "id": rendered.template_id,
                    "revision": rendered.revision,
                    "scene": scene,
                }
                if rendered.missing_fields:
                    template_snapshot["missing_fields"] = rendered.missing_fields
            except Exception as exc:
                logger.warning(
                    "[AlertNotify] 自定义模板渲染失败，使用默认内容: object_id=%s channel_id=%s template_id=%s error_type=%s",
                    object_id,
                    channel.get("id"),
                    template_id,
                    type(exc).__name__,
                )
                template_snapshot = {"id": template_id, "scene": scene, "fallback": True, "error_type": type(exc).__name__}
        if channel_title is None or channel_content is None:
            default_title, default_content = get_default_values()
            channel_title = default_title if channel_title is None else channel_title
            channel_content = default_content if channel_content is None else channel_content
        if channel["channel_type"] == ChannelChoices.NATS:
            if nats_team is None:
                logger.warning(
                    "[AlertNotify] 无单一组织上下文，跳过 OpsPilot NATS 通道 %s (object_id=%s)",
                    channel["id"],
                    object_id,
                )
                continue
            logger.info(
                "[AlertNotify] 构造 OpsPilot NATS 通知参数: object_id=%s, channel_id=%s, team=%s, user_ids=%s",
                object_id,
                channel["id"],
                nats_team,
                username_list,
            )
            item = {
                "username_list": username_list,
                "channel_type": channel["channel_type"],
                "channel_id": channel["id"],
                "title": "",
                "content": {
                    "message": channel_content,
                    "team": nats_team,
                    "user_ids": username_list,
                },
                "object_id": object_id,
                "notify_action_object": notify_action_object,
            }
            if template_snapshot is not None:
                item["append_receivers"] = append_receivers
                item["template_snapshot"] = template_snapshot
            params.append(item)
            continue
        item = {
            "username_list": username_list,
            "channel_type": channel["channel_type"],
            "channel_id": channel["id"],
            "title": channel_title,
            "content": channel_content,
            "object_id": object_id,
            "notify_action_object": notify_action_object,
        }
        if template_snapshot is not None:
            item["append_receivers"] = append_receivers
            item["template_snapshot"] = template_snapshot
        params.append(item)
    return params


def enqueue_notifications(params: List[Dict[str, Any]], idempotency_key: Optional[str] = None) -> bool:
    """把通知意图写入 outbox；空入参不投递。"""
    if not params:
        logger.info("[AlertNotify] enqueue_notifications: 无通知参数，跳过投递")
        return False

    summary = [(p.get("channel_type"), p.get("channel_id")) for p in params]
    from apps.alerts.service.outbox import enqueue_outbox

    key = idempotency_key or f"notification:{uuid.uuid4().hex}"
    record, created = enqueue_outbox("notification", {"params": params}, key)
    logger.info(
        "[AlertNotify] outbox recorded: outbox_id=%s created=%s params=%s channels=%s",
        record.pk,
        created,
        len(params),
        summary,
    )
    return True
