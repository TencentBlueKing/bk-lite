# -- coding: utf-8 --
"""通知收口出口(Q1)。

统一三处通知(分派/提醒/升级)的两段机械重复:
1. build_channel_params：把 (接收人, 渠道列表, 告警) 构建为 sync_notify 期望的 list[dict]，一渠道一条；
2. enqueue_notifications：统一投递时机——事务内则 on_commit 后投递，否则立即。

不统一"渠道选择"逻辑（分派用默认渠道、提醒用 assignment 渠道、升级用层级渠道，按场景不同，是合理差异）。
"""
from typing import Any, Dict, List, Optional

from django.db import transaction

from apps.alerts.common.notify.base import NotifyParamsFormat


def build_channel_params(
    username_list: List[str],
    channels: List[Dict[str, Any]],
    alerts: List,
    object_id: str,
    notify_action_object: str = "alert",
    title: Optional[str] = None,
    content: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """构建 sync_notify 入参(list[dict])。username_list 或 channels 为空 → 返回 []。"""
    if not username_list or not channels:
        return []

    param_format = NotifyParamsFormat(username_list=username_list, alerts=alerts)
    resolved_title = param_format.format_title() if title is None else title
    resolved_content = param_format.format_content() if content is None else content

    params: List[Dict[str, Any]] = []
    for channel in channels:
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


def enqueue_notifications(params: List[Dict[str, Any]]) -> bool:
    """统一投递出口:事务内则提交后投递,否则立即。空入参 → 不投递,返回 False。"""
    if not params:
        return False

    # 延迟导入避免循环依赖
    from apps.alerts.tasks import sync_notify

    def _enqueue():
        sync_notify.delay(params)

    if transaction.get_connection().in_atomic_block:
        transaction.on_commit(_enqueue)
    else:
        _enqueue()
    return True
