import json
import os
import secrets
from zoneinfo import ZoneInfo

from django.contrib.auth.hashers import check_password
from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone as django_timezone

from apps.core.utils.loader import LanguageLoader
from apps.rpc.system_mgmt import SystemMgmt
from apps.system_mgmt.models import Group, Role, User
from apps.system_mgmt.models.app import App
from apps.system_mgmt.utils.group_utils import GroupUtils
from apps.system_mgmt.utils.operation_log_utils import log_operation

# 每用户每邮箱发送验证码的速率限制：60 秒内最多 1 次
EMAIL_CODE_RATE_LIMIT_SECONDS = 60

# 验证码在 cache 中的有效期（秒），可通过环境变量覆盖，默认 600s（10 分钟）
_EMAIL_CODE_TTL = int(os.getenv("EMAIL_CODE_TTL", "600"))


def _email_code_cache_key(username: str, email: str) -> str:
    """生成验证码 cache key，按用户+邮箱隔离。"""
    return f"vc:{username}:{email}"


def _format_datetime_for_user(value, timezone_name=None):
    if not value:
        return None

    try:
        if timezone_name:
            return django_timezone.localtime(value, ZoneInfo(timezone_name)).isoformat()
    except Exception:
        pass

    return django_timezone.localtime(value).isoformat()


def get_user_group_paths(user_group_list):
    """
    获取用户所在组的路径信息（包含所有父级组）
    :param user_group_list: 用户所属的组ID列表
    :return: 组路径列表

    实现采用两阶段按需加载，避免全表扫描：
    - Phase 1：仅查询 id/parent_id 轻量字段，BFS 收集从用户组到根的所有祖先 ID。
    - Phase 2：按 ID 集合查询完整对象（含 prefetch_related("roles")），集合大小
              与路径深度成正比（O(depth × fan-out)），而非系统组织总数 O(N)。
    """
    if not user_group_list:
        return []

    # Phase 1：轻量查询，仅取 id + parent_id，BFS 向上收集祖先 ID
    # 从用户直属组出发，每轮查询当前层节点的 parent_id，直到到达根（parent_id=0 或 None）
    all_group_ids: set = set(user_group_list)
    current_ids: set = set(user_group_list)

    while current_ids:
        # 仅查询当前层节点的 parent_id，不加载其余字段
        parent_rows = Group.objects.filter(id__in=current_ids).values_list("id", "parent_id")
        new_parent_ids = set()
        for _gid, parent_id in parent_rows:
            if parent_id and parent_id not in all_group_ids:
                new_parent_ids.add(parent_id)

        if not new_parent_ids:
            break

        all_group_ids.update(new_parent_ids)
        current_ids = new_parent_ids

    # Phase 2：仅加载路径所需的组对象（含 roles prefetch）
    related_groups = list(Group.objects.filter(id__in=all_group_ids).prefetch_related("roles"))

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

    # 校验当前用户是否处于首次登录状态（仅属于默认组 OpsPilotGuest）
    group_list = getattr(request.user, "group_list", [])
    if not group_list or len(group_list) != 1:
        return JsonResponse({"result": False, "message": loader.get("error.not_first_login", "User has already been initialized")})

    first_group = group_list[0]
    group_name = first_group.get("name") if isinstance(first_group, dict) else str(first_group)
    if group_name != "OpsPilotGuest":
        return JsonResponse({"result": False, "message": loader.get("error.not_first_login", "User has already been initialized")})

    # 使用当前登录用户的身份，不信任前端传入的 user_id
    try:
        user = User.objects.get(username=request.user.username, domain=request.user.domain)
    except User.DoesNotExist:
        return JsonResponse({"result": False, "message": loader.get("error.user_not_found", "User not found")})

    client = SystemMgmt()
    res = client.init_user_default_attributes(user.id, kwargs["group_name"], group_list[0]["id"])
    if not res["result"]:
        return JsonResponse(res)
    log_operation(request, "create", "console_mgmt", f"初始化用户设置: {request.user.username}")
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
    body = json.loads(request.body)
    password = body.get("password")
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
    验证邮箱验证码（服务端持有验证码状态，一次性使用）
    :param request: {
        "email": "待验证邮箱地址",
        "input_code": "用户输入的验证码"
    }
    """
    try:
        params = json.loads(request.body)
        email = params.get("email")
        input_code = params.get("input_code")

        # 获取用户语言设置
        locale = getattr(request.user, "locale", "en") if hasattr(request, "user") else "en"
        loader = LanguageLoader(app="console_mgmt", default_lang=locale)

        if not email or not input_code:
            return JsonResponse({"result": False, "message": loader.get("error.verification_code_empty", "Verification code cannot be empty")})

        username = request.user.username if hasattr(request, "user") and request.user else ""
        cache_key = _email_code_cache_key(username, email)
        stored_code = cache.get(cache_key)

        if stored_code is None:
            # 验证码不存在：已过期或从未发送
            return JsonResponse({"result": False, "message": loader.get("error.verification_code_expired", "Verification code has expired or does not exist")})

        if secrets.compare_digest(str(stored_code), str(input_code)):
            # 验证通过：立即删除（一次性使用）
            cache.delete(cache_key)
            return JsonResponse({"result": True, "message": loader.get("success.verification_success", "Verification successful")})

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

        # 速率限制：每个已登录用户每个目标邮箱 60 秒内最多发送 1 次，防止平台邮件服务被滥用为骚扰工具
        # 使用 cache.add() 原子操作（set-if-not-exists），避免 get+set 的 TOCTOU 竞争条件
        username = getattr(request.user, "username", None)
        if username:
            rate_key = f"send_email_code_rate:{username}:{email}"
            if not cache.add(rate_key, 1, timeout=EMAIL_CODE_RATE_LIMIT_SECONDS):
                return JsonResponse(
                    {
                        "result": False,
                        "message": loader.get(
                            "error.email_code_rate_limit",
                            "Please wait before requesting another verification code",
                        ),
                    }
                )

        # 使用密码学安全 PRNG 生成 6 位数字验证码
        verification_code = "".join([str(secrets.randbelow(10)) for _ in range(6)])

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

        # 验证码存入服务端 cache，TTL 到期自动失效；不向客户端返回任何哈希
        username = request.user.username if hasattr(request, "user") and request.user else ""
        cache_key = _email_code_cache_key(username, email)
        cache.set(cache_key, verification_code, timeout=_EMAIL_CODE_TTL)

        return JsonResponse(
            {
                "result": True,
                "message": loader.get("success.verification_code_sent", "Verification code has been sent"),
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

        # 一次性获取所有app数据并构建映射
        all_apps = App.objects.all()
        app_map = {app.name: app.display_name for app in all_apps}

        # 收集用户角色ID：包含用户直接角色和所属组的角色（去重）
        role_ids = set(user.role_list) if user.role_list else set()
        if user.group_list:
            groups = Group.objects.filter(id__in=user.group_list).prefetch_related("roles")
            for group in groups:
                role_ids.update(group.roles.values_list("id", flat=True))

        # 将role_list中的ID转换为角色信息（包含app显示名称）
        role_info = []
        if role_ids:
            roles = Role.objects.filter(id__in=list(role_ids))
            role_info = [
                {"id": role.id, "name": role.name, "app": role.app or "", "app_display_name": app_map.get(role.app, "") if role.app else ""}
                for role in roles
            ]

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
            "last_login": _format_datetime_for_user(user.last_login, getattr(request.user, "timezone", None)),
            "password_last_modified": _format_datetime_for_user(
                user.password_last_modified,
                getattr(request.user, "timezone", None),
            ),
            "temporary_pwd": user.temporary_pwd,
        }
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

        # 从 cookie 中读取调用方 token，转发给 NATS handler 进行身份校验
        caller_token = request.COOKIES.get("bklite_token", "")
        if not caller_token:
            return JsonResponse({"result": False, "message": loader.get("error.please_provide_token", "Please provide Token")})

        client = SystemMgmt()
        res = client.reset_pwd(username, domain, password, caller_token=caller_token)

        # 如果密码重置成功，记录操作日志
        if res.get("result"):
            log_operation(request, "update", "console_mgmt", f"重置用户密码: {username}")

        return JsonResponse(res)
    except Exception as e:
        return JsonResponse({"result": False, "message": str(e)})
