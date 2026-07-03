# flake8: noqa
import base64
import io
import json
import os
import time
from datetime import timedelta
from uuid import uuid4

import jwt
import pyotp
import qrcode
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

import nats_client
from apps.core.constants import VERIFY_TOKEN_USER_NOT_FOUND_CODE, VERIFY_TOKEN_USER_NOT_FOUND_MESSAGE
from apps.core.logger import system_mgmt_logger as logger
from apps.core.utils.loader import LanguageLoader
from apps.core.utils.permission_cache import clear_token_info_cache, clear_users_permission_cache, get_cached_token_info, set_cached_token_info
from apps.system_mgmt.guest_menus import CMDB_MENUS, MONITOR_MENUS, OPSPILOT_GUEST_MENUS
from apps.system_mgmt.models import (
    App,
    Channel,
    ChannelChoices,
    ErrorLog,
    Group,
    GroupDataRule,
    LoginModule,
    Menu,
    OperationLog,
    Role,
    User,
    UserRule,
)
from apps.system_mgmt.models.system_settings import SystemSettings
from apps.system_mgmt.otp_challenge import (
    check_rate_limit,
    create_challenge,
    invalidate_challenge,
    record_failed_attempt,
    reset_rate_limit,
    verify_challenge,
)
from apps.system_mgmt.services.role_manage import RoleManage
from apps.system_mgmt.utils.bk_user_utils import get_bk_user_info
from apps.system_mgmt.utils.channel_utils import (
    send_by_custom_webhook,
    send_by_dingtalk_bot,
    send_by_feishu_bot,
    send_by_wecom_bot,
    send_email,
    send_email_to_user,
    send_nats_message,
)
from apps.system_mgmt.utils.group_utils import GroupUtils
from apps.system_mgmt.utils.password_validator import PasswordValidator
from apps.system_mgmt.utils.pwd_policy_cache import get_pwd_policy_settings as _get_pwd_policy_settings
from apps.system_mgmt.utils.token_blacklist import blacklist_token, is_blacklisted




def _collect_ancestor_group_ids(seed_ids):
    """
    从 seed_ids 出发，沿 parent_id 链向上收集所有祖先组 ID（含自身）。

    仅使用轻量级 values_list 查询（不加载角色关联），避免全表 prefetch。
    返回的集合可用于后续有针对性地加载完整 Group 对象。

    :param seed_ids: 起始组 ID 列表（通常为 user.group_list）
    :return: 包含 seed_ids 及其所有祖先的 ID set
    """
    if not seed_ids:
        return set()
    # 一次查询获取全表的 (id, parent_id, allow_inherit_roles)，仅传输轻量列
    all_meta = {
        row[0]: (row[1], row[2])
        for row in Group.objects.values_list("id", "parent_id", "allow_inherit_roles")
    }
    result = set()
    stack = list(seed_ids)
    while stack:
        gid = stack.pop()
        if gid in result:
            continue
        result.add(gid)
        meta = all_meta.get(gid)
        if meta:
            parent_id, allow_inherit = meta
            if parent_id and parent_id not in result:
                stack.append(parent_id)
    return result


def get_user_all_roles(user):
    """
    获取用户的所有角色（个人角色 + 组角色，含完整继承链）

    继承规则：沿 parent_id 链向上追溯，只要父级 allow_inherit_roles=True，
    就收集该父级的角色并继续向上，直到某层 allow_inherit_roles=False 或到达根节点为止。

    :param user: User实例
    :return: 包含所有角色ID的列表
    """
    # 用户直接授权的角色
    personal_role_ids = set(user.role_list)

    group_role_ids = set()
    if user.group_list:
        # 先收集祖先组 ID（轻量查询），再按需加载完整对象（含角色关联）
        ancestor_ids = _collect_ancestor_group_ids(user.group_list)
        all_groups = {
            g.id: g
            for g in Group.objects.prefetch_related("roles").filter(id__in=ancestor_ids)
        }

        visited = set()

        def collect_roles(group_id):
            """收集 group_id 自身角色，并沿 parent_id 链递归收集继承角色"""
            if group_id in visited:
                return
            visited.add(group_id)

            group = all_groups.get(group_id)
            if not group:
                return

            # 收集自身角色
            for role in group.roles.all():
                group_role_ids.add(role.id)

            # 向上追溯：父级 allow_inherit_roles=True 才继续继承
            parent_id = group.parent_id
            if parent_id:
                parent = all_groups.get(parent_id)
                if parent and parent.allow_inherit_roles:
                    collect_roles(parent_id)

        for gid in user.group_list:
            collect_roles(gid)

    # 合并去重
    return list(personal_role_ids | group_role_ids)


def _get_login_expired_seconds():
    """获取 login_expired_time 配置值（秒）。"""
    login_expired_time_set = SystemSettings.objects.filter(key="login_expired_time").first()
    if login_expired_time_set:
        return int(float(login_expired_time_set.value) * 3600)
    return 3600 * 24


def _build_jwt_payload(user_id):
    """构建包含 jti 和 exp 的 JWT payload。"""
    now = int(time.time())
    expired_seconds = _get_login_expired_seconds()
    return {
        "user_id": user_id,
        "login_time": now,
        "jti": uuid4().hex,
        "exp": now + expired_seconds,
    }


def _verify_token(token):
    token = token.split("Basic ")[-1]
    secret_key = os.getenv("SECRET_KEY")
    algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    user_info = jwt.decode(token, key=secret_key, algorithms=[algorithm], options={"verify_exp": False})
    time_now = int(time.time())

    # New-format token (with jti + exp): use PyJWT exp validation + blacklist check
    if "jti" in user_info and "exp" in user_info:
        # Re-decode with exp verification enabled
        jwt.decode(token, key=secret_key, algorithms=[algorithm])
        if is_blacklisted(user_info["jti"]):
            raise Exception("Token has been revoked")
    else:
        # Legacy token: fall back to login_time-based expiry check
        login_expired_time_set = SystemSettings.objects.filter(key="login_expired_time").first()
        login_expired_time = 3600 * 24
        if login_expired_time_set:
            login_expired_time = float(login_expired_time_set.value) * 3600
        if time_now - login_expired_time > user_info["login_time"]:
            raise Exception("Token is invalid")

    user = User.objects.filter(id=user_info["user_id"]).first()
    if not user:
        raise Exception(VERIFY_TOKEN_USER_NOT_FOUND_MESSAGE)
    return user
