# flake8: noqa
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
def search_channel_list(channel_type="", teams=None, include_children=False):
    """
    :param channel_type: str， 目前只有email、enterprise_wechat_bot
    :param teams: list, [1,2,3]
    :param include_children: bool , True、False
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
def search_channel_list_scoped(actor_context, channel_type="", teams=None, include_children=False):
    """
    在调用方授权范围内查询通知通道列表。

    :param actor_context: 调用方上下文，包含 username、domain、current_team、is_superuser 等字段
    :param channel_type: 可选，通道类型过滤条件
    :param teams: 可选，待查询的组织 ID 列表；最终会与调用方授权范围取交集
    :param include_children: 是否包含当前组织下的已授权子组织
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
