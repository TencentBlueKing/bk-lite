import datetime

from wechatpy import WeChatClient as WeChatAccountClient
from wechatpy.enterprise import WeChatClient

from apps.core.backends import cache
from apps.core.logger import opspilot_logger as logger
from apps.opspilot.enum import ChannelChoices
from apps.opspilot.models import BotChannel, ChannelGroup, ChannelUser, SkillRequestLog, UserGroup
from apps.opspilot.services.ding_talk_client import DingTalkClient


def set_time_range(end_time_str, start_time_str):
    today = datetime.datetime.today()
    # 解析时间字符串到 datetime 对象，并处理空值
    if start_time_str:
        start_time = datetime.datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%S.%fZ")
    else:
        start_time = today.replace(hour=0, minute=0, second=0, microsecond=0)
    if end_time_str:
        end_time = datetime.datetime.strptime(end_time_str, "%Y-%m-%dT%H:%M:%S.%fZ")
    else:
        end_time = today.replace(hour=23, minute=59, second=59, microsecond=999999)
    return end_time, start_time


def get_user_info(bot_id, input_channel, sender_id):
    channel_type_map = {
        "web": ChannelChoices.WEB,
        "enterprise_wechat": ChannelChoices.ENTERPRISE_WECHAT,
        "dingtalk": ChannelChoices.DING_TALK,
        "wechat_official_account": ChannelChoices.WECHAT_OFFICIAL_ACCOUNT,
    }
    groups = []
    if input_channel == "enterprise_wechat":
        channel_obj = BotChannel.objects.get(bot_id=bot_id, channel_type=ChannelChoices.ENTERPRISE_WECHAT)
        conf = channel_obj.decrypted_channel_config
        wechat_client = WeChatClient(
            conf["channels.enterprise_wechat_channel.EnterpriseWechatChannel"]["corp_id"],
            conf["channels.enterprise_wechat_channel.EnterpriseWechatChannel"]["secret"],
        )
        try:
            user = wechat_client.user.get(sender_id)
            name = user["name"]
            groups = get_enterprise_wechat_user_groups(wechat_client, user["department"], bot_id)
        except Exception as e:
            logger.error(f"获取企业微信用户信息失败: {e}")
            name = sender_id
    elif input_channel == "dingtalk":
        channel_obj = BotChannel.objects.get(bot_id=bot_id, channel_type=ChannelChoices.DING_TALK)
        conf = channel_obj.decrypted_channel_config
        client = DingTalkClient(
            conf["channels.dingtalk_channel.DingTalkChannel"]["client_id"],
            conf["channels.dingtalk_channel.DingTalkChannel"]["client_secret"],
        )
        try:
            name = client.get_user_info(sender_id)["name"]
            groups = get_ding_talk_user_groups(sender_id, client)
        except Exception as e:
            logger.error(f"获取钉钉用户信息失败: {e}")
            name = sender_id
    elif input_channel == "wechat_official_account":
        channel_obj = BotChannel.objects.get(bot_id=bot_id, channel_type=ChannelChoices.WECHAT_OFFICIAL_ACCOUNT)
        conf = channel_obj.decrypted_channel_config
        client = WeChatAccountClient(
            conf["channels.wechat_official_account_channel.WechatOfficialAccountChannel"]["appid"],
            conf["channels.wechat_official_account_channel.WechatOfficialAccountChannel"]["secret"],
        )
        try:
            user = client.user.get(sender_id)
            name = user["nickname"] or user["remark"] or sender_id
        except Exception as e:
            logger.error(f"获取微信用户信息失败: {e}")
            name = sender_id
    else:
        name = sender_id

    if name == sender_id:
        fun = "get_or_create"
    else:
        fun = "update_or_create"

    user, _ = getattr(ChannelUser.objects, fun)(
        user_id=sender_id,
        channel_type=channel_type_map.get(input_channel, ChannelChoices.WEB),
        defaults={"name": name},
    )
    UserGroup.objects.filter(user_id=user.id).delete()
    user_groups = []
    for group in groups:
        channel_group, _ = ChannelGroup.objects.update_or_create(
            group_id=group["id"],
            channel_type=channel_type_map.get(input_channel, ChannelChoices.WEB),
            defaults={
                "name": group["name"],
            },
        )
        user_groups.append(UserGroup(user_id=user.id, group_id=channel_group.id))
    UserGroup.objects.bulk_create(user_groups, batch_size=100)
    return user, groups


def get_ding_talk_user_groups(sender_id, client):
    dept_list = client.get_user_department(sender_id)
    group_list = []
    for i in dept_list:
        group_list.append({"id": i, "name": client.get_department_name(i)})
    return group_list


def get_enterprise_wechat_user_groups(client, group_ids, bot_id):
    all_groups = cache.get(f"enterprise_wechat_all_groups-{bot_id}")
    if not all_groups:
        all_groups = client.department.get()
    group_list = []
    exist_groups = []
    for group_id in group_ids:
        groups = get_department_hierarchy(group_id, all_groups)
        add_groups = []
        for i in groups:
            if i["id"] in exist_groups:
                continue
            add_groups.append(i)
            exist_groups.append(i["id"])
        group_list.extend(add_groups)
    return group_list


def get_department_hierarchy(department_id, department_list):
    # 构造一个字典索引以便快速查找
    department_dict = {dept["id"]: dept for dept in department_list}

    # 当前的部门信息
    result = []
    current_department = department_dict.get(department_id)

    # 逐级追溯上级部门
    while current_department:
        result.append({"id": current_department["id"], "name": current_department["name"]})
        parent_id = current_department["parentid"]
        current_department = department_dict.get(parent_id)

    # 返回结果，按照从上级到当前的顺序
    return result[::-1]


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[-1].strip()
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip


def insert_skill_log(current_ip, skill_id, response_detail, request_detail, state=True, user_message=""):
    if skill_id is None:
        return
    SkillRequestLog.objects.create(
        skill_id=skill_id,
        response_detail=response_detail,
        request_detail=request_detail,
        state=state,
        current_ip=current_ip,
        user_message=user_message,
    )
