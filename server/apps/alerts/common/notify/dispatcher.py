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
    resolved_title = param_format.format_title() if title is None else title
    resolved_content = param_format.format_content() if content is None else content

    # NATS 触发只接受单个组织上下文；单条告警时取其归属组织(告警必定单一组织)
    nats_team = None
    if len(alerts) == 1:
        alert_team = getattr(alerts[0], "team", None) or []
        if alert_team:
            nats_team = alert_team[0]

    params: List[Dict[str, Any]] = []
    for channel in channels:
        if channel["channel_type"] == ChannelChoices.NATS:
            if nats_team is None:
                logger.warning(
                    "[AlertNotify] 无单一组织上下文，跳过 OpsPilot NATS 通道 %s (object_id=%s)",
                    channel["id"], object_id,
                )
                continue
            logger.info(
                "[AlertNotify] 构造 OpsPilot NATS 通知参数: object_id=%s, channel_id=%s, team=%s, user_ids=%s",
                object_id, channel["id"], nats_team, username_list,
            )
            params.append(
                {
                    "username_list": username_list,
                    "channel_type": channel["channel_type"],
                    "channel_id": channel["id"],
                    "title": "",
                    "content": {
                        "message": resolved_content,
                        "team": nats_team,
                        "user_ids": username_list,
                    },
                    "object_id": object_id,
                    "notify_action_object": notify_action_object,
                }
            )
            continue
        params.append(
            {
                "username_list": username_list,
                "channel_type": channel["channel_type"],
                "channel_id": channel["id"],
                "title": resolved_title,
                "content": resolved_content,
                "object_id": object_id,
                "notify_action_object": notify_action_object,
            }
        )
    return params


def enqueue_notifications(
    params: List[Dict[str, Any]], idempotency_key: Optional[str] = None
) -> bool:
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
