import json
import random

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.http import JsonResponse

from apps.core.utils.loader import LanguageLoader
from apps.rpc.opspilot import OpsPilot
from apps.rpc.system_mgmt import SystemMgmt
from apps.system_mgmt.models import Group, Role, User
from apps.system_mgmt.utils.group_utils import GroupUtils
from apps.system_mgmt.utils.operation_log_utils import log_operation


def get_user_group_paths(user_group_list):
    """
    获取用户所在组的路径信息（包含所有父级组）
    :param user_group_list: 用户所属的组ID列表
    :return: 组路径列表
    """
    if not user_group_list:
        return []

    # 一次性获取所有组数据（包含所有可能的父级组）
    all_groups = Group.objects.all().prefetch_related("roles")

    # 构建组ID到组对象的映射
    group_map = {group.id: group for group in all_groups}

    # 收集用户所在组及其所有父级组ID
    all_group_ids = set(user_group_list)

    # 非递归方式获取所有父级组ID
    current_ids = set(user_group_list)
    while current_ids:
        parent_ids = set()
        for group_id in current_ids:
            group = group_map.get(group_id)
            if group and hasattr(group, "parent_id") and group.parent_id:
                parent_ids.add(group.parent_id)

        # 过滤出尚未处理的父级组ID
        new_parent_ids = parent_ids - all_group_ids
        if not new_parent_ids:
            break

        all_group_ids.update(new_parent_ids)
        current_ids = new_parent_ids

    # 获取所有相关组对象
    related_groups = [group_map[gid] for gid in all_group_ids if gid in group_map]

    return GroupUtils.build_group_paths(related_groups, user_group_list)


def init_user_set(request):
    # 获取用户语言设置
    locale = getattr(request.user, "locale", "en") if hasattr(request, "user") else "en"
    loader = LanguageLoader(app="console_mgmt", default_lang=locale)

    try:
        kwargs = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"result": False, "message": loader.get("error.invalid_json_format", "Invalid JSON format")})
    except Exception:
        return JsonResponse({"result": False, "message": loader.get("error.parse_request_failed", "Failed to parse request body")})

    client = SystemMgmt()
    res = client.init_user_default_attributes(kwargs["user_id"], kwargs["group_name"], request.user.group_list[0]["id"])
    if not res["result"]:
        return JsonResponse(res)
    opspilot_client = OpsPilot()
    res = opspilot_client.init_user_set(res["data"]["group_id"], kwargs["group_name"])
    return JsonResponse(res)


def update_user_base_info(request):
    params = json.loads(request.body)
    username = request.user.username
    domain = request.user.domain

    # 获取用户语言设置
    locale = getattr(request.user, "locale", "en")
    loader = LanguageLoader(app="console_mgmt", default_lang=locale)
    try:
        # 通过username和domain获取用户
        user = User.objects.get(username=username, domain=domain)

        with transaction.atomic():
            user.display_name = params.get("display_name") or user.display_name
            user.email = params.get("email") or user.email
            user.locale = params.get("locale") or user.locale
            user.timezone = params.get("timezone") or user.timezone
            user.save()
            log_operation(request, "update", "console_mgmt", f"编辑用户: {user.username}")
        return JsonResponse({"result": True})
    except User.DoesNotExist:
        return JsonResponse({"result": False, "message": loader.get("error.user_not_found", "User not found")})
    except Exception as e:
        return JsonResponse({"result": False, "message": str(e)})


def validate_pwd(request):
    password = request.GET.get("password")
    username = request.user.username
    domain = request.user.domain

    # 获取用户语言设置
    locale = getattr(request.user, "locale", "en")
    loader = LanguageLoader(app="console_mgmt", default_lang=locale)

    if not password:
        return JsonResponse({"result": False, "message": loader.get("error.password_required", "Password cannot be empty")})
    try:
        # 通过username和domain获取用户
        user = User.objects.get(username=username, domain=domain)
        if check_password(password, user.password):
            return JsonResponse({"result": True})
        return JsonResponse({"result": False})
    except User.DoesNotExist:
        return JsonResponse({"result": False, "message": loader.get("error.user_not_found", "User not found")})
    except Exception as e:
        return JsonResponse({"result": False, "message": str(e)})


def validate_email_code(request):
    """
    验证邮箱验证码
    :param request: {
        "hashed_code": "哈希后的验证码",
        "input_code": "用户输入的验证码"
    }
    """
    try:
        params = json.loads(request.body)
        hashed_code = params.get("hashed_code")
        input_code = params.get("input_code")

        # 获取用户语言设置
        locale = getattr(request.user, "locale", "en") if hasattr(request, "user") else "en"
        loader = LanguageLoader(app="console_mgmt", default_lang=locale)

        if not hashed_code or not input_code:
            return JsonResponse({"result": False, "message": loader.get("error.verification_code_empty", "Verification code cannot be empty")})

        # 使用check_password验证
        if check_password(input_code, hashed_code):
            return JsonResponse({"result": True, "message": loader.get("success.verification_success", "Verification successful")})
        else:
            return JsonResponse({"result": False, "message": loader.get("error.verification_code_incorrect", "Verification code is incorrect")})
    except Exception as e:
        return JsonResponse({"result": False, "message": str(e)})


def send_email_code(request):
    """
    发送邮箱验证码
    :param request: {
        "email": "用户邮箱地址"
    }
    """
    try:
        params = json.loads(request.body)
        email = params.get("email")

        # 获取用户语言设置，默认en
        locale = params.get("locale") or (getattr(request.user, "locale", "en") if hasattr(request, "user") else "en")
        loader = LanguageLoader(app="console_mgmt", default_lang=locale)

        if not email:
            return JsonResponse({"result": False, "message": loader.get("error.email_required", "Email address cannot be empty")})

        # 生成6位随机数字验证码
        verification_code = "".join([str(random.randint(0, 9)) for _ in range(6)])

        # 构造邮件内容（使用翻译）
        title = loader.get("email.verification_code_title", "Email Verification Code")
        title = loader.get("email.verification_code_title", "Email Verification Code")
        body = loader.get("email.verification_code_body", "Your verification code is")
        validity = loader.get("email.verification_code_validity", "The verification code is valid for 10 minutes, please use it in time.")
        ignore = loader.get("email.verification_code_ignore", "If this is not your operation, please ignore this email.")
        content = f"""
        <html>
        <body>
            <h2>{title}</h2>
            <p>{body}: <strong style="font-size: 24px; color: #007bff;">{verification_code}</strong></p>
            <p>{validity}</p>
            <p>{ignore}</p>
        </body>
        </html>
        """

        # 使用RPC调用发送邮件到指定邮箱地址
        client = SystemMgmt()
        result = client.send_email_to_receiver(title=title, content=content, receiver=email)
        if not result.get("result"):
            return JsonResponse(result)

        # 使用make_password哈希验证码返回给前端
        hashed_code = make_password(verification_code)

        return JsonResponse(
            {
                "result": True,
                "message": loader.get("success.verification_code_sent", "Verification code has been sent"),
                "data": {"hashed_code": hashed_code},
            }
        )
    except Exception as e:
        return JsonResponse({"result": False, "message": str(e)})


def get_user_info(request):
    """
    获取用户信息
    :param request: 从 request.user 获取当前用户
    """
    username = request.user.username
    domain = request.user.domain

    # 获取用户语言设置
    locale = getattr(request.user, "locale", "en")
    loader = LanguageLoader(app="console_mgmt", default_lang=locale)
    try:
        # 通过username和domain获取用户
        user = User.objects.get(username=username, domain=domain)

        # 构建组织路径格式（获取用户所在组及其所有父级组）
        group_paths = get_user_group_paths(user.group_list)

        # 将role_list中的ID转换为角色信息（包含app名称）
        role_info = []
        if user.role_list:
            roles = Role.objects.filter(id__in=user.role_list)
            role_info = [{"id": role.id, "name": role.name, "app": role.app or ""} for role in roles]

        user_info = {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "email": user.email,
            "disabled": user.disabled,
            "locale": user.locale,
            "timezone": user.timezone,
            "domain": user.domain,
            "group_list": group_paths,
            "role_list": role_info,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "password_last_modified": user.password_last_modified.isoformat() if user.password_last_modified else None,
            "temporary_pwd": user.temporary_pwd,
        }

        # 记录操作日志
        log_operation(request, "execute", "console_mgmt", f"查询用户信息: {user.username}")

        return JsonResponse({"result": True, "data": user_info})
    except User.DoesNotExist:
        return JsonResponse({"result": False, "message": loader.get("error.user_not_found", "User not found")})
    except Exception as e:
        return JsonResponse({"result": False, "message": str(e)})


def reset_pwd(request):
    try:
        data = json.loads(request.body)
        username = request.user.username
        domain = request.user.domain
        password = data.get("password", "")

        # 获取用户语言设置
        locale = getattr(request.user, "locale", "en")
        loader = LanguageLoader(app="console_mgmt", default_lang=locale)

        if not username or not password:
            return JsonResponse({"result": False, "message": loader.get("error.password_required", "Username or password cannot be empty")})

        client = SystemMgmt()
        res = client.reset_pwd(username, domain, password)

        # 如果密码重置成功，记录操作日志
        if res.get("result"):
            log_operation(request, "update", "console_mgmt", f"重置用户密码: {username}")

        return JsonResponse(res)
    except Exception as e:
        return JsonResponse({"result": False, "message": str(e)})
