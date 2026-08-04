# flake8: noqa
import html
import re

from .common import *  # noqa: F401,F403
from .users import _get_actor_user_scope


@nats_client.register
def get_channel_detail(channel_id):
    channel_obj = Channel.objects.filter(id=channel_id).first()
    if not channel_obj:
        return {"result": False, "message": "传入的channel_id无法匹配到channel"}
    return_data = {
        "name": channel_obj.name,
        "description": channel_obj.description,
        "config": channel_obj.config,
        "team": channel_obj.team,
        "channel_type": channel_obj.channel_type,
    }
    return {"result": True, "data": return_data}


@nats_client.register
def search_channel_list(channel_type="", teams=None, include_children=False, channel_method=""):
    """
    :param channel_type: str， 目前只有email、enterprise_wechat_bot
    :param teams: list, [1,2,3]
    :param include_children: bool , True、False
    :param channel_method: 可选，仅返回 config.method_name 匹配的通道
    """
    # 空 teams 直接返回空数据
    if not teams:
        return {"result": True, "data": []}

    # 如果 include_children 为 True，递归获取所有子组织
    if include_children:
        # 一次性获取所有组织，避免递归查询数据库
        all_groups = Group.objects.values_list("id", "parent_id")
        # 构建 parent_id -> [child_ids] 的映射
        children_map = {}
        for gid, pid in all_groups:
            if pid is not None:
                children_map.setdefault(pid, []).append(gid)

        # 在内存中递归获取所有子组织
        def get_descendants(group_id, result_set):
            result_set.add(group_id)
            for child_id in children_map.get(group_id, []):
                get_descendants(child_id, result_set)

        all_teams = set()
        for team_id in teams:
            get_descendants(team_id, all_teams)
        teams = list(all_teams)

    # 构建 teams 筛选条件：team 字段与 teams 有交集
    channels = Channel.objects.all()
    if channel_type:
        channels = channels.filter(channel_type=channel_type)
    if channel_method:
        channels = channels.filter(config__method_name=channel_method)

    # 使用 Q 对象构建 OR 条件
    if teams:
        team_filter = Q(team__contains=teams[0])
        for team_id in teams[1:]:
            team_filter |= Q(team__contains=team_id)
        channels = channels.filter(team_filter)

    return {
        "result": True,
        "data": [i for i in channels.values("id", "name", "channel_type", "description")],
    }


@nats_client.register
def search_channel_list_scoped(
    actor_context,
    channel_type="",
    teams=None,
    include_children=False,
    channel_method="",
):
    """
    在调用方授权范围内查询通知通道列表。

    :param actor_context: 调用方上下文，包含 username、domain、current_team、is_superuser 等字段
    :param channel_type: 可选，通道类型过滤条件
    :param teams: 可选，待查询的组织 ID 列表；最终会与调用方授权范围取交集
    :param include_children: 是否包含当前组织下的已授权子组织
    :param channel_method: 可选，仅返回 config.method_name 匹配的通道
    :return: 标准 NATS 返回结构，data 为通知通道列表
    """
    user_obj, authorized_groups = _get_actor_user_scope(actor_context, include_children=include_children)
    if not user_obj or not authorized_groups:
        return {"result": True, "data": []}

    if teams:
        normalized_teams = []
        for team in teams:
            try:
                normalized_teams.append(int(team))
            except (TypeError, ValueError):
                continue
        teams = [team for team in normalized_teams if team in authorized_groups]
    else:
        teams = authorized_groups

    return search_channel_list(
        channel_type=channel_type,
        teams=teams,
        include_children=False,
        channel_method=channel_method,
    )


def _resolve_message_receivers(receivers):
    if not receivers:
        return None

    if all(isinstance(r, int) or (isinstance(r, str) and r.isdigit()) for r in receivers):
        return User.objects.filter(id__in=[int(r) for r in receivers])

    if all(isinstance(r, str) and r.strip() and not r.isdigit() for r in receivers):
        return User.objects.filter(username__in=[receiver.strip() for receiver in receivers])

    return None


def _normalize_nats_content(content):
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return None, {"result": False, "message": "NATS content is not valid JSON"}

    if not isinstance(content, dict):
        return None, {"result": False, "message": "NATS content must be a dict"}

    message = content.get("message")
    if not isinstance(message, str) or not message.strip():
        return None, {"result": False, "message": "NATS content.message must be a non-empty string"}

    team = content.get("team")
    # team 现在只允许单个组织 ID；兼容历史的单元素列表写法
    if isinstance(team, (list, tuple)):
        if len(team) != 1:
            return None, {"result": False, "message": "NATS content.team must be a single team id"}
        team = team[0]
    team_value = str(team).strip()
    if not team_value or not team_value.isdigit():
        return None, {"result": False, "message": "NATS content.team must be a single integer team id"}
    normalized_team = int(team_value)

    user_ids = content.get("user_ids")
    if not isinstance(user_ids, list):
        return None, {"result": False, "message": "NATS content.user_ids must be a list"}

    normalized_user_ids = []
    for user_id in user_ids:
        if user_id is None:
            continue
        normalized_user_id = str(user_id).strip()
        if normalized_user_id:
            normalized_user_ids.append(normalized_user_id)

    return {
        "message": message.strip(),
        "team": normalized_team,
        "user_ids": normalized_user_ids,
    }, None


RAW_PASSTHROUGH_NATS_METHODS = {"receive_alert_events"}

ALERT_EVENT_COPY_METHOD = "receive_alert_events"
SYSTEM_USER_CHANNEL_TYPES = {
    ChannelChoices.EMAIL,
    ChannelChoices.ENTERPRISE_WECHAT,
}
RICH_TEXT_CHANNEL_TYPES = {
    ChannelChoices.EMAIL,
    ChannelChoices.ENTERPRISE_WECHAT_BOT,
    ChannelChoices.FEISHU_BOT,
    ChannelChoices.DINGTALK_BOT,
}
MAX_NOTIFICATION_RECIPIENTS = 100
MAX_NOTIFICATION_RECIPIENT_LENGTH = 150
MAX_NOTIFICATION_TITLE_LENGTH = 512
MAX_NOTIFICATION_BODY_LENGTH = 20_000


def _notification_channel_capabilities(channel):
    is_alert_event_copy = (
        channel.channel_type == ChannelChoices.NATS
        and (channel.config or {}).get("method_name") == ALERT_EVENT_COPY_METHOD
    )
    if is_alert_event_copy:
        delivery_mode = "alert_event_copy"
        recipient_mode = "none"
    else:
        delivery_mode = "message"
        recipient_mode = "system_user" if channel.channel_type in SYSTEM_USER_CHANNEL_TYPES else "free_text"
    return {
        "id": channel.id,
        "name": channel.name,
        "channel_type": channel.channel_type,
        "description": channel.description,
        "delivery_mode": delivery_mode,
        "recipient_mode": recipient_mode,
        "availability": "available",
    }


def _channel_has_organization(channel, organization_ids):
    return _channel_delivery_organization(channel, organization_ids) is not None


def _channel_delivery_organization(channel, organization_ids):
    """返回渠道与事件共同归属的确定性组织，避免多组织事件投递到错误 team。"""
    try:
        allowed = {int(value) for value in channel.team or []}
        requested = {int(value) for value in organization_ids or []}
    except (TypeError, ValueError):
        return None
    shared = allowed.intersection(requested)
    return min(shared) if shared else None


@nats_client.register
def list_notification_channels_scoped(actor_context, teams=None, include_children=False):
    """返回调用方组织范围内可用的公开通知能力，不暴露渠道私有配置。"""
    user_obj, authorized_groups = _get_actor_user_scope(actor_context, include_children=include_children)
    if not user_obj or not authorized_groups:
        return {"result": True, "data": []}
    if teams:
        try:
            requested = {int(value) for value in teams}
        except (TypeError, ValueError):
            requested = set()
        authorized_groups = [group_id for group_id in authorized_groups if group_id in requested]
    if not authorized_groups:
        return {"result": True, "data": []}
    channels = [
        channel
        for channel in Channel.objects.order_by("id")
        if _channel_has_organization(channel, authorized_groups)
    ]
    return {
        "result": True,
        "data": [_notification_channel_capabilities(channel) for channel in channels],
    }


@nats_client.register
def search_notification_recipients_scoped(
    actor_context,
    teams=None,
    include_children=False,
    search="",
    limit=100,
):
    """返回通知配置可引用的组织内系统用户稳定 ID，不暴露用户敏感字段。"""
    user_obj, authorized_groups = _get_actor_user_scope(actor_context, include_children=include_children)
    if not user_obj or not authorized_groups:
        return {"result": True, "data": []}
    try:
        requested = {int(value) for value in teams} if teams else set(authorized_groups)
        bounded_limit = min(max(int(limit), 1), 100)
    except (TypeError, ValueError):
        return _notification_failure("invalid_payload", "接收人查询参数无效。")
    scoped_groups = set(authorized_groups).intersection(requested)
    if not scoped_groups:
        return {"result": True, "data": []}
    needle = str(search or "").strip().casefold()[:100]
    result = []
    for user in User.objects.order_by("id").only("id", "username", "display_name", "group_list"):
        group_ids = set()
        for value in user.group_list or []:
            try:
                group_ids.add(int(value.get("id") if isinstance(value, dict) else value))
            except (TypeError, ValueError):
                continue
        if not group_ids.intersection(scoped_groups):
            continue
        if needle and needle not in user.username.casefold() and needle not in (user.display_name or "").casefold():
            continue
        result.append({"id": user.id, "username": user.username, "display_name": user.display_name})
        if len(result) >= bounded_limit:
            break
    return {"result": True, "data": result}


def _notification_failure(code, message, *, retryable=False):
    return {
        "result": False,
        "code": code,
        "retryable": retryable,
        "message": message,
    }


@nats_client.register
def probe_notification_channel(channel_id):
    """探测内部通知 responder；普通外部渠道只校验公开能力是否仍存在。"""
    channel = Channel.objects.filter(id=channel_id).first()
    if channel is None:
        return _notification_failure("channel_not_found", "通知渠道不存在。")
    capability = _notification_channel_capabilities(channel)
    if capability["delivery_mode"] != "alert_event_copy":
        return {"result": True, "code": "available", "retryable": False, "message": "success"}

    response = send_nats_message(channel, {"health_probe": True}, timeout_override=2)
    if isinstance(response, dict) and response.get("result") is True:
        return {"result": True, "code": "available", "retryable": False, "message": "success"}
    return _notification_failure(
        "responder_unavailable",
        "通知 responder 暂不可用。",
        retryable=True,
    )


def _validate_notification_recipients(recipient_mode, recipients):
    if not isinstance(recipients, list) or len(recipients) > MAX_NOTIFICATION_RECIPIENTS:
        return None
    normalized = []
    for recipient in recipients:
        value = str(recipient).strip()
        if not value or len(value) > MAX_NOTIFICATION_RECIPIENT_LENGTH:
            return None
        normalized.append(value)
    if recipient_mode == "none":
        return [] if not normalized else None
    if not normalized:
        return None
    if recipient_mode == "system_user" and not all(value.isdigit() for value in normalized):
        return None
    return normalized


def _escape_notification_rich_text(value):
    """把外部命名字段作为纯文本嵌入 HTML/Markdown 渠道。"""
    escaped = html.escape(value, quote=True)
    return re.sub(r"([\\`*{}\[\]()#+\-.!|>~_])", r"\\\1", escaped)


@nats_client.register
def dispatch_notification(
    delivery_key,
    channel_id,
    organization_ids,
    recipients,
    title,
    body,
    event_payload,
):
    """按公开渠道能力投递一次通知，并返回稳定、可判定重试的结果。"""
    if not isinstance(delivery_key, str) or not delivery_key.strip() or len(delivery_key) > 384:
        return _notification_failure("invalid_payload", "投递键无效。")
    channel = Channel.objects.filter(id=channel_id).first()
    if channel is None:
        return _notification_failure("channel_not_found", "通知渠道不存在。")
    delivery_organization = _channel_delivery_organization(channel, organization_ids)
    if delivery_organization is None:
        return _notification_failure("channel_forbidden", "通知渠道不属于事件组织范围。")
    capability = _notification_channel_capabilities(channel)
    normalized_recipients = _validate_notification_recipients(capability["recipient_mode"], recipients)
    if normalized_recipients is None:
        return _notification_failure("invalid_recipients", "通知接收人不符合渠道能力。")
    if capability["recipient_mode"] == "system_user":
        requested_user_ids = {int(value) for value in normalized_recipients}
        if User.objects.filter(id__in=requested_user_ids).count() != len(requested_user_ids):
            return _notification_failure("invalid_recipients", "通知接收人不存在或已失效。")
    if (
        not isinstance(title, str)
        or len(title) > MAX_NOTIFICATION_TITLE_LENGTH
        or not isinstance(body, str)
        or not body.strip()
        or len(body) > MAX_NOTIFICATION_BODY_LENGTH
        or not isinstance(event_payload, dict)
    ):
        return _notification_failure("invalid_payload", "通知内容无效。")

    if capability["delivery_mode"] == "alert_event_copy":
        content = {
            "source_id": "nats",
            "pusher": "lite-apm",
            "events": [event_payload],
        }
        send_title = ""
        send_recipients = []
    elif channel.channel_type == ChannelChoices.NATS:
        content = {
            "message": body.strip(),
            "team": delivery_organization,
            "user_ids": normalized_recipients,
        }
        send_title = title
        send_recipients = normalized_recipients
    else:
        if channel.channel_type in RICH_TEXT_CHANNEL_TYPES:
            content = _escape_notification_rich_text(body.strip())
            send_title = _escape_notification_rich_text(title)
        else:
            content = body.strip()
            send_title = title
        send_recipients = normalized_recipients

    try:
        response = send_msg_with_channel(
            channel.id,
            send_title,
            content,
            send_recipients,
        )
    except Exception:
        logger.exception("Public notification dispatch failed")
        return _notification_failure("provider_unavailable", "通知传输暂不可用。", retryable=True)
    if not isinstance(response, dict):
        return _notification_failure("invalid_provider_response", "通知渠道返回格式无效。", retryable=True)
    if response.get("result") is False:
        return _notification_failure(
            str(response.get("code") or "delivery_failed"),
            str(response.get("message") or "通知渠道投递失败。")[:512],
            retryable=bool(response.get("retryable", True)),
        )
    if capability["delivery_mode"] == "alert_event_copy":
        ingestion = (response.get("data") or {}).get("ingestion") or {}
        if ingestion and (
            int(ingestion.get("errored", 0) or 0) > 0
            or int(ingestion.get("accepted", 0) or 0) + int(ingestion.get("skipped", 0) or 0) < 1
        ):
            return _notification_failure("alert_copy_rejected", "告警中心未接受事件副本。", retryable=True)
    return {"result": True, "code": "delivered", "retryable": False, "message": "success"}


@nats_client.register
def send_msg_with_channel(channel_id, title, content, receivers, attachments=None):
    """
    通过指定通道发送消息
    :param channel_id: 通道ID
    :param title: 邮件主题（企微机器人传空字符串即可）
    :param content: 正文内容
    :param receivers: 用户ID列表 [1, 2, 3, 4] 或用户名列表 ["user1", "user2"]
    :param attachments: 附件列表（仅email通道支持），格式为:
        [{"filename": "文件名.pdf", "content": "base64编码的文件内容"}, ...]
        注意: 附件内容必须是base64编码的字符串，因为NATS使用JSON序列化传输
    """
    channel_obj = Channel.objects.filter(id=channel_id).first()
    if not channel_obj:
        return {"result": False, "message": "Channel not found"}
    # 兼容用户ID列表和用户名列表两种情况
    user_list = _resolve_message_receivers(receivers)
    if channel_obj.channel_type == ChannelChoices.EMAIL:
        # 邮件发送需要校验收件人是否存在
        if not user_list or not user_list.exists():
            return {"result": False, "message": "No valid recipients found"}
        return send_email(channel_obj, title, content, user_list, attachments)
    elif channel_obj.channel_type == ChannelChoices.ENTERPRISE_WECHAT_BOT:
        if user_list is not None:
            display_names = list(user_list.values_list("display_name", flat=True))
        else:
            display_names = receivers if isinstance(receivers, list) else [receivers]
        return send_by_wecom_bot(channel_obj, content, display_names)
    elif channel_obj.channel_type == ChannelChoices.FEISHU_BOT:
        if user_list is not None:
            display_names = list(user_list.values_list("display_name", flat=True))
        else:
            display_names = receivers if isinstance(receivers, list) else [receivers]
        return send_by_feishu_bot(channel_obj, title, content, display_names)
    elif channel_obj.channel_type == ChannelChoices.DINGTALK_BOT:
        if user_list is not None:
            display_names = list(user_list.values_list("display_name", flat=True))
        else:
            display_names = receivers if isinstance(receivers, list) else [receivers]
        return send_by_dingtalk_bot(channel_obj, title, content, display_names)
    elif channel_obj.channel_type == ChannelChoices.CUSTOM_WEBHOOK:
        return send_by_custom_webhook(channel_obj, content, receivers)
    elif channel_obj.channel_type == ChannelChoices.NATS:
        # NATS 通道：content 作为 kwargs 传递给目标服务
        method_name = (channel_obj.config or {}).get("method_name")
        if method_name in RAW_PASSTHROUGH_NATS_METHODS:
            # 内部直推通道（如告警中心）：原样透传 content，跳过 IM 触发的字段规范化。
            return send_nats_message(channel_obj, content)
        normalized, error = _normalize_nats_content(content)
        if error:
            return error
        return send_nats_message(channel_obj, normalized)
    return {"result": False, "message": "Unsupported channel type"}


OPSPILOT_CHANNEL_SOURCE = "opspilot"


OPSPILOT_NATS_NAMESPACE = os.getenv("NATS_NAMESPACE", "bklite")


OPSPILOT_NATS_METHOD = "trigger_workflow_by_nats"


def _list_opspilot_nats_channels(bot_id):
    """返回某个 bot 名下、由 OpsPilot 托管的 NATS 通道（DB 无关，Python 侧过滤 config）。"""
    channels = Channel.objects.filter(channel_type=ChannelChoices.NATS)
    result = []
    for channel in channels:
        config = channel.config or {}
        if config.get("source") == OPSPILOT_CHANNEL_SOURCE and str(config.get("bot_id")) == str(bot_id):
            result.append(channel)
    return result


@nats_client.register
def sync_opspilot_nats_channels(bot_id, bot_name, team, nodes, timeout=60):
    """对账 OpsPilot 某个 bot 的 NATS 触发节点对应的通道（增/改/删）。

    :param bot_id: Bot ID
    :param bot_name: Bot 名称（用于拼通道名）
    :param team: 通道归属组织 ID 列表
    :param nodes: [{"node_id": "xxx", "name": "节点label"}, ...]
    :param timeout: NATS 请求超时（秒）
    """
    try:
        bot_id = int(bot_id)
    except (TypeError, ValueError):
        return {"result": False, "message": "bot_id must be an integer"}

    team = team or []
    nodes = nodes or []
    description = "OpsPilot 工作流自动创建的 NATS 触发通道"

    existing_by_node = {(ch.config or {}).get("node_id"): ch for ch in _list_opspilot_nats_channels(bot_id)}

    incoming_node_ids = set()
    created = updated = 0
    for node in nodes:
        node_id = str((node or {}).get("node_id") or "").strip()
        if not node_id:
            continue
        incoming_node_ids.add(node_id)
        label = str((node or {}).get("name") or node_id).strip()
        # 通道名：BOT名 - 节点名；Channel.name 上限 100
        name = f"{bot_name} - {label}"[:100]
        config = {
            "namespace": OPSPILOT_NATS_NAMESPACE,
            "method_name": OPSPILOT_NATS_METHOD,
            "bot_id": bot_id,
            "node_id": node_id,
            "timeout": timeout,
            "source": OPSPILOT_CHANNEL_SOURCE,
        }
        channel = existing_by_node.get(node_id)
        if channel:
            channel.name = name
            channel.config = config
            channel.team = team
            channel.description = description
            channel.save()
            updated += 1
        else:
            Channel.objects.create(
                name=name,
                channel_type=ChannelChoices.NATS,
                config=config,
                team=team,
                description=description,
            )
            created += 1

    # 对账删除：flow_json 里已不存在的旧节点对应的通道
    deleted = 0
    for node_id, channel in existing_by_node.items():
        if node_id not in incoming_node_ids:
            channel.delete()
            deleted += 1

    return {"result": True, "data": {"created": created, "updated": updated, "deleted": deleted}}


@nats_client.register
def delete_opspilot_nats_channels(bot_id):
    """删除某个 bot 名下所有 OpsPilot 托管的 NATS 通道（bot 删除时清理）。"""
    try:
        bot_id = int(bot_id)
    except (TypeError, ValueError):
        return {"result": False, "message": "bot_id must be an integer"}

    deleted = 0
    for channel in _list_opspilot_nats_channels(bot_id):
        channel.delete()
        deleted += 1
    return {"result": True, "data": {"deleted": deleted}}


@nats_client.register
def search_opspilot_nats_channels(teams=None, bot_id=None, include_children=False):
    """查询 OpsPilot 托管的 NATS 触发通道（config.source == "opspilot"）。

    与通用 search_channel_list 不同：本接口专门按 OpsPilot 托管标识过滤，
    支持跨团队/全局列举，并返回路由字段 bot_id / node_id。

    :param teams: 可选，组织 ID 列表；为空/None 则跨团队全局列举
    :param bot_id: 可选，仅返回该 Bot 的通道
    :param include_children: 当传 teams 时，是否一并包含其子组织
    :return: 标准 NATS 返回结构，data 为 [{id, name, description, team, bot_id, node_id}]
    """
    channels = Channel.objects.filter(channel_type=ChannelChoices.NATS)

    # 传了 teams 才按组织过滤；为空表示全局
    if teams:
        normalized_teams = []
        for team_id in teams:
            try:
                normalized_teams.append(int(team_id))
            except (TypeError, ValueError):
                continue

        if include_children and normalized_teams:
            all_groups = Group.objects.values_list("id", "parent_id")
            children_map = {}
            for gid, pid in all_groups:
                if pid is not None:
                    children_map.setdefault(pid, []).append(gid)

            def _collect_descendants(group_id, acc):
                acc.add(group_id)
                for child_id in children_map.get(group_id, []):
                    _collect_descendants(child_id, acc)

            expanded = set()
            for team_id in normalized_teams:
                _collect_descendants(team_id, expanded)
            normalized_teams = list(expanded)

        if not normalized_teams:
            return {"result": True, "data": []}

        team_filter = Q(team__contains=normalized_teams[0])
        for team_id in normalized_teams[1:]:
            team_filter |= Q(team__contains=team_id)
        channels = channels.filter(team_filter)

    # DB 无关：在 Python 侧按 config.source（及可选 bot_id）过滤
    data = []
    for channel in channels:
        config = channel.config or {}
        if config.get("source") != OPSPILOT_CHANNEL_SOURCE:
            continue
        if bot_id is not None and str(config.get("bot_id")) != str(bot_id):
            continue
        data.append(
            {
                "id": channel.id,
                "name": channel.name,
                "description": channel.description,
                "team": channel.team,
                "bot_id": config.get("bot_id"),
                "node_id": config.get("node_id"),
            }
        )
    return {"result": True, "data": data}


@nats_client.register
def send_email_to_receiver(title, content, receiver):
    channel_obj = Channel.objects.filter(channel_type=ChannelChoices.EMAIL).first()
    channel_config = channel_obj.config
    channel_obj.decrypt_field("smtp_pwd", channel_config)
    return send_email_to_user(channel_config, content, [receiver], title)
