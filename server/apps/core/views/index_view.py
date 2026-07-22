import json
import os
from urllib.parse import urlencode, urlparse

import requests
from django.conf import settings as django_settings
from django.core.cache import cache
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from rest_framework.decorators import api_view

from apps.core.logger import logger
from apps.core.services.login_auth_request_service import (
    build_auth_request_state,
    create_auth_request,
    get_auth_request,
    get_login_auth_callback_uri,
    parse_auth_request_state,
    update_auth_request_status,
    validate_poll_token,
    validate_redirect_origin,
)
from apps.core.utils.exempt import api_exempt
from apps.core.utils.loader import LanguageLoader
from apps.rpc.base import RpcClient
from apps.rpc.system_mgmt import SystemMgmt
from apps.system_mgmt.models import UserLoginLog
from apps.system_mgmt.models.login_module import LoginModule
from apps.system_mgmt.services.login_auth_binding_service import build_login_auth_redirect, get_active_login_auth_bindings
from apps.system_mgmt.models.system_settings import SystemSettings
from apps.system_mgmt.utils.login_log_utils import log_user_login_from_request

PORTAL_BRANDING_KEYS = ("portal_name", "portal_logo_url", "portal_favicon_url", "watermark_enabled", "watermark_text")
LOGIN_AUTH_BINDINGS_RATE_LIMIT = 60
LOGIN_AUTH_BINDINGS_RATE_WINDOW_SECONDS = 60
LOGIN_AUTH_BINDINGS_CACHE_SECONDS = 30


def _get_loader(request=None) -> LanguageLoader:
    """获取基于用户locale的LanguageLoader"""
    locale = "en"
    if request and hasattr(request, "user") and hasattr(request.user, "locale"):
        locale = request.user.locale or "en"
    return LanguageLoader(app="core", default_lang=locale)


def _create_system_mgmt_client():
    """创建SystemMgmt客户端"""
    return SystemMgmt()


def _get_portal_branding_settings():
    return dict(SystemSettings.objects.filter(key__in=PORTAL_BRANDING_KEYS).values_list("key", "value"))


def _parse_request_data(request):
    """解析请求数据"""
    if hasattr(request, "body") and request.body:
        try:
            return json.loads(request.body)
        except json.JSONDecodeError:
            return request.POST.dict()
    return request.POST.dict()


def _set_auth_cookie_on_response(response, token):
    """
    统一设置认证 cookie。

    在所有登录入口成功后调用此函数，确保 cookie 设置的一致性。
    """
    login_expired_time = 3600 * 24  # default 24h
    try:
        setting = SystemSettings.objects.filter(key="login_expired_time").first()
        if setting:
            login_expired_time = int(float(setting.value) * 3600)
    except Exception:
        pass

    response.set_cookie(
        "bklite_token",
        token,
        max_age=login_expired_time,
        path="/",
        secure=not django_settings.DEBUG,
        httponly=True,
        samesite="Lax",
    )


def _get_client_ip(request):
    """
    Get client IP address from request.

    Handles X-Forwarded-For header for proxied requests.
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        # Take the first IP in the chain (original client)
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR", "")
    return ip


def _is_safe_relative_callback_url(callback_url: str) -> bool:
    if not callback_url or not callback_url.startswith("/"):
        return False

    parsed = urlparse(callback_url)
    return not parsed.scheme and not parsed.netloc


def _is_safe_legacy_external_callback_url(callback_url: str) -> bool:
    try:
        parsed = urlparse(callback_url)
    except (TypeError, ValueError):
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _build_login_auth_result_redirect(
    request,
    status_key: str,
    message: str,
    redirect_origin: str | None = None,
):
    """生成 OAuth callback 完成后的前端结果页重定向。

    安全前提:redirect_origin 在 start_login_auth 阶段已通过
    validate_redirect_origin 校验并落 cache(校验失败时已被置 None,
    不会入 cache)。callback 阶段无需再校验:
      - callback 是 top-level navigation,无 HTTP_ORIGIN
      - 容器化部署下 X-Forwarded-Host / request.get_host() 不可靠
      - 唯一可信源是 cache 里 T1 阶段验证过的值(server-side,不可篡改)
    """
    query_string = urlencode(
        {
            "status": status_key,
            "message": message,
        }
    )
    path = f"/auth/signin/login-auth-result?{query_string}"
    if redirect_origin:
        return HttpResponseRedirect(f"{redirect_origin.rstrip('/')}{path}")
    return HttpResponseRedirect(path)


def _get_login_auth_binding_by_id(binding_id: int):
    for binding in get_active_login_auth_bindings():
        if binding.id == binding_id:
            return binding
    return None


def verify_wechat_code(code: str) -> dict:
    """
    真实微信 API 验证 code。

    Returns:
        {
            "success": bool,
            "openid": str,       # 成功时
            "nickname": str,     # 成功时
            "unionid": str,      # 成功时（可选）
            "error": str,        # 失败时
            "errcode": int       # 失败时（可选）
        }
    """
    try:
        # 直接从数据库获取微信配置，避免通过 NATS 接口暴露 app_secret
        login_module = LoginModule.objects.filter(source_type="wechat", enabled=True).first()
        if not login_module:
            return {"success": False, "error": "WeChat login is not enabled"}

        app_id = login_module.app_id
        app_secret = login_module.decrypted_app_secret

        # Step 1: code 换 access_token
        token_url = (
            f"https://api.weixin.qq.com/sns/oauth2/access_token"
            f"?appid={app_id}"
            f"&secret={app_secret}"
            f"&code={code}"
            f"&grant_type=authorization_code"
        )

        token_resp = requests.get(token_url, timeout=10)
        token_data = token_resp.json()

        if "errcode" in token_data:
            logger.warning(f"WeChat token exchange failed: {token_data}")
            return {
                "success": False,
                "error": token_data.get("errmsg", "Unknown error"),
                "errcode": token_data.get("errcode"),
            }

        # Step 2: 获取用户信息
        userinfo_url = (
            f"https://api.weixin.qq.com/sns/userinfo" f"?access_token={token_data['access_token']}" f"&openid={token_data['openid']}" f"&lang=zh_CN"
        )

        userinfo_resp = requests.get(userinfo_url, timeout=10)
        userinfo_data = userinfo_resp.json()

        if "errcode" in userinfo_data:
            logger.warning(f"WeChat userinfo fetch failed: {userinfo_data}")
            return {
                "success": False,
                "error": userinfo_data.get("errmsg", "Unknown error"),
                "errcode": userinfo_data.get("errcode"),
            }

        return {
            "success": True,
            "openid": userinfo_data["openid"],
            "nickname": userinfo_data.get("nickname", ""),
            "unionid": userinfo_data.get("unionid"),
            "headimgurl": userinfo_data.get("headimgurl"),
        }

    except requests.Timeout:
        logger.error("WeChat API timeout")
        return {"success": False, "error": "WeChat API timeout"}
    except Exception as e:
        logger.exception(f"WeChat verification error: {e}")
        return {"success": False, "error": str(e)}


def _safe_get_user_id_by_username(client, username):
    """安全获取用户ID"""
    try:
        res = client.search_users({"search": username})
        users_list = res.get("data", {}).get("users", [])

        if not users_list:
            return None

        for user in users_list:
            if user.get("username") == username:
                return user.get("id")

        return None
    except Exception as e:
        logger.error(f"Error searching for user {username}: {e}")
        return None


def _check_first_login(user, default_group):
    """检查是否为首次登录"""
    group_list = getattr(user, "group_list", [])

    if not group_list:
        return True

    if len(group_list) == 1:
        first_group = group_list[0]
        group_name = first_group.get("name") if isinstance(first_group, dict) else str(first_group)
        return group_name == default_group

    return False


def index(request):
    data = {"STATIC_URL": "static/", "RUN_MODE": "PROD"}
    return render(request, "index.prod.html", data)


@api_exempt
def login(request):
    try:
        data = _parse_request_data(request)
        login_auth_binding_id = data.get("binding_id") or data.get("login_auth_binding_id")
        auth_code = data.get("auth_code", "").strip()
        username = data.get("username", "").strip()
        password = data.get("password", "")
        domain = data.get("domain", "")
        c_url = data.get("redirect_url", "").strip()  # 获取回调URL

        if login_auth_binding_id:
            client = SystemMgmt()
            res = client.login_with_binding(login_auth_binding_id, auth_code, username=username, password=password)
            log_username = res.get("data", {}).get("username") or username or "unknown"
            if not res.get("result"):
                logger.warning(f"Binding login failed for binding: {login_auth_binding_id}")
                failure_reason = res.get("message", "Login failed")
                log_user_login_from_request(
                    request,
                    log_username,
                    UserLoginLog.STATUS_FAILED,
                    "domain.com",
                    failure_reason=str(failure_reason),
                )
            else:
                logger.info(f"Binding login successful for binding: {login_auth_binding_id}")
                log_user_login_from_request(request, log_username, UserLoginLog.STATUS_SUCCESS, "domain.com")
                if c_url:
                    if "data" not in res:
                        res["data"] = {}
                    res["data"]["redirect_url"] = c_url
            response = JsonResponse(res)
            if res.get("result") and res.get("data", {}).get("token"):
                _set_auth_cookie_on_response(response, res["data"]["token"])
            return response

        if not username or not password:
            # 记录登录失败日志 - 用户名或密码为空
            loader = _get_loader(request)
            msg = loader.get("error.username_password_empty", "Username or password cannot be empty")
            log_user_login_from_request(request, username or "unknown", UserLoginLog.STATUS_FAILED, domain or "domain.com", failure_reason=msg)
            return JsonResponse({"result": False, "message": msg})

        if domain == "domain.com":
            client = SystemMgmt()
            res = client.login(username, password)
        else:
            res = bk_lite_login(username, password, domain)

        if not res.get("result"):
            # 记录登录失败日志
            logger.warning(f"Login failed for user: {username}")
            failure_reason = res.get("message", "Login failed")
            log_user_login_from_request(
                request,
                username,
                UserLoginLog.STATUS_FAILED,
                domain or "domain.com",
                failure_reason=str(failure_reason),
            )
        else:
            # 记录登录成功日志
            logger.info(f"Login successful for user: {username}")
            log_user_login_from_request(request, username, UserLoginLog.STATUS_SUCCESS, domain or "domain.com")

            # 登录成功时，如果有c_url参数，添加到响应中
            if c_url:
                if "data" not in res:
                    res["data"] = {}
                res["data"]["redirect_url"] = c_url
                logger.info(f"Login successful for user: {username}, redirect to: {c_url}")
        response = JsonResponse(res)

        # Set bklite_token cookie with secure attributes on successful login
        if res.get("result") and res.get("data", {}).get("token"):
            _set_auth_cookie_on_response(response, res["data"]["token"])

        return response
    except Exception as e:
        logger.error(f"Login error: {e}")
        # 记录系统错误导致的登录失败
        log_user_login_from_request(
            request,
            username if "username" in locals() else "unknown",
            UserLoginLog.STATUS_FAILED,
            domain if "domain" in locals() else "domain.com",
            failure_reason=f"System error: {str(e)}",
        )
        return JsonResponse(
            {
                "result": False,
                "message": _get_loader(request).get("error.system_error", "System error occurred"),
            }
        )


@api_exempt
def logout(request):
    """撤销 token 并清除 bklite_token cookie。"""
    if request.method != "POST":
        return JsonResponse({"result": False, "message": "Method not allowed"}, status=405)
    try:
        # Read token from both cookie (HttpOnly) and body (API call from Next.js server-side)
        token = request.COOKIES.get("bklite_token", "")
        if not token:
            data = _parse_request_data(request)
            token = data.get("token", "")
        if token:
            client = SystemMgmt()
            client.revoke_token(token)

        response = JsonResponse({"result": True, "message": "Logout successful"})
        response.delete_cookie("bklite_token", path="/", samesite="Lax")
        return response
    except Exception as e:
        logger.error(f"Logout error: {e}")
        response = JsonResponse({"result": True, "message": "Logout completed with errors"})
        response.delete_cookie("bklite_token", path="/", samesite="Lax")
        return response


@api_exempt
def wechat_login(request):
    """
    [LEGACY] 旧扫码登录入口,与 LoginAuthBinding 通用链路并行。

    接收微信授权 code,后端验证后签发 token。

    新链路走 WechatLoginAuthAdapter → _resolve_platform_user,
    详情见 openspec/changes/wechat-login-auth-field-mapping/design.md。
    新链路稳定后移除本入口及 wechat_user_register NATS handler。

    Request:
        POST { "code": "微信授权码" }

    Response:
        成功: { "result": true, "data": { "id", "username", "token", ... } }
        失败: { "result": false, "message": "错误信息" }
    """
    if request.method != "POST":
        return JsonResponse({"result": False, "message": "Method not allowed"}, status=405)

    try:
        data = _parse_request_data(request)
        code = data.get("code", "").strip()

        if not code:
            loader = _get_loader(request)
            msg = loader.get("error.code_empty", "code is required")
            log_user_login_from_request(
                request,
                "unknown",
                UserLoginLog.STATUS_FAILED,
                "wechat",
                failure_reason=msg,
            )
            return JsonResponse({"result": False, "message": msg})

        # 验证微信 code
        verify_result = verify_wechat_code(code)

        if not verify_result["success"]:
            error_msg = verify_result.get("error", "WeChat verification failed")
            logger.warning(f"WeChat login failed: {error_msg}")
            log_user_login_from_request(
                request,
                "unknown",
                UserLoginLog.STATUS_FAILED,
                "wechat",
                failure_reason=error_msg,
            )
            return JsonResponse({"result": False, "message": error_msg})

        # 用 openid 创建/获取用户
        openid = verify_result["openid"]
        nickname = verify_result.get("nickname", openid)

        client = _create_system_mgmt_client()
        res = client.wechat_user_register(openid, nickname)

        if not res.get("result"):
            logger.warning(f"WeChat user registration failed for openid: {openid}")
            failure_reason = res.get("message", "User registration failed")
            log_user_login_from_request(
                request,
                openid,
                UserLoginLog.STATUS_FAILED,
                "wechat",
                failure_reason=str(failure_reason),
            )
            return JsonResponse(res)

        # 记录登录成功
        logger.info(f"WeChat login successful for openid: {openid}")
        log_user_login_from_request(request, openid, UserLoginLog.STATUS_SUCCESS, "wechat")

        # 添加微信 profile 数据到响应
        if res.get("data"):
            res["data"]["openid"] = openid
            res["data"]["unionid"] = verify_result.get("unionid")
            res["data"]["display_name"] = nickname

        response = JsonResponse(res)

        # 设置 cookie
        if res.get("data", {}).get("token"):
            _set_auth_cookie_on_response(response, res["data"]["token"])

        return response

    except Exception as e:
        logger.error(f"WeChat login error: {e}")
        log_user_login_from_request(
            request,
            "unknown",
            UserLoginLog.STATUS_FAILED,
            "wechat",
            failure_reason=f"System error: {str(e)}",
        )
        return JsonResponse(
            {
                "result": False,
                "message": _get_loader(request).get("error.system_error", "System error occurred"),
            }
        )


@api_exempt
def get_wechat_settings(request):
    try:
        client = _create_system_mgmt_client()
        res = client.get_wechat_settings()
        return JsonResponse(res)
    except Exception as e:
        logger.error(f"Error retrieving WeChat settings: {e}")
        return JsonResponse(
            {
                "result": False,
                "message": _get_loader(request).get("error.system_error", "System error occurred"),
            }
        )


@api_exempt
def get_bk_settings(request):
    bk_token = request.COOKIES.get("bk_token", "")
    client = SystemMgmt()
    res = client.verify_bk_token(bk_token)
    if isinstance(res, dict):
        res.setdefault("data", {})
        res["data"].update(_get_portal_branding_settings())
    return JsonResponse(res)


def reset_pwd(request):
    try:
        data = _parse_request_data(request)
        username = request.user.username
        domain = getattr(request.user, "domain", "")
        password = data.get("password", "")

        if not password:
            return JsonResponse(
                {
                    "result": False,
                    "message": _get_loader(request).get(
                        "error.username_password_empty",
                        "Password cannot be empty",
                    ),
                }
            )

        # 从 cookie 中读取调用方 token，转发给 NATS handler 进行身份校验
        caller_token = request.COOKIES.get("bklite_token", "")
        if not caller_token:
            return JsonResponse(
                {
                    "result": False,
                    "message": _get_loader(request).get("error.please_provide_token", "Please provide Token"),
                }
            )

        client = _create_system_mgmt_client()
        res = client.reset_pwd(username, domain, password, caller_token=caller_token)

        if not res.get("result"):
            logger.warning(f"Password reset failed for user: {username}")

        return JsonResponse(res)
    except Exception as e:
        logger.error(f"Password reset error: {e}")
        return JsonResponse(
            {
                "result": False,
                "message": _get_loader(request).get("error.system_error", "System error occurred"),
            }
        )


@api_view(["GET"])
def login_info(request):
    try:
        # default_group = os.environ.get("TOP_GROUP", "Default")
        is_first_login = _check_first_login(request.user, "OpsPilotGuest")

        client = _create_system_mgmt_client()
        user_id = _safe_get_user_id_by_username(client, request.user.username)

        if user_id is None:
            logger.error(f"User not found: {request.user.username}")
            return JsonResponse({"result": False, "message": "User not found"})

        response_data = {
            "result": True,
            "data": {
                "user_id": user_id,
                "username": request.user.username,
                "display_name": getattr(request.user, "display_name", request.user.username),
                "is_superuser": getattr(request.user, "is_superuser", False),
                "group_list": getattr(request.user, "group_list", []),
                "roles": getattr(request.user, "roles", []),
                "is_first_login": is_first_login,
                "group_tree": getattr(request.user, "group_tree", []),
                "locale": getattr(request.user, "locale", "zh-CN"),
                "timezone": getattr(request.user, "timezone", "Asia/Shanghai"),
            },
        }

        return JsonResponse(response_data)
    except Exception as e:
        logger.error(f"Error retrieving login info: {e}")
        return JsonResponse(
            {
                "result": False,
                "message": _get_loader(request).get("error.system_error", "System error occurred"),
            }
        )


def generate_qr_code(request):
    """
    Generate OTP QR code for the current authenticated user.

    Requires authentication - only generates QR code for request.user.
    """
    try:
        # Use authenticated user instead of username parameter
        if not hasattr(request, "user") or not request.user or not request.user.id:
            return JsonResponse(
                {
                    "result": False,
                    "message": _get_loader(request).get("error.unauthorized", "Authentication required"),
                },
                status=401,
            )

        user_id = request.user.id

        client = _create_system_mgmt_client()
        res = client.generate_qr_code_by_user_id(user_id)

        if not res.get("result"):
            logger.warning(f"QR code generation failed for user_id: {user_id}")

        return JsonResponse(res)
    except Exception as e:
        logger.error(f"QR code generation error: {e}")
        return JsonResponse(
            {
                "result": False,
                "message": _get_loader(request).get("error.system_error", "System error occurred"),
            }
        )


def verify_otp_code(request):
    """
    Verify OTP code for the current authenticated user (for OTP binding).

    Requires authentication - only verifies OTP for request.user.
    """
    try:
        # Use authenticated user instead of username parameter
        if not hasattr(request, "user") or not request.user or not request.user.id:
            return JsonResponse(
                {
                    "result": False,
                    "message": _get_loader(request).get("error.unauthorized", "Authentication required"),
                },
                status=401,
            )

        data = _parse_request_data(request)
        otp_code = data.get("otp_code", "").strip()

        if not otp_code:
            return JsonResponse(
                {
                    "result": False,
                    "message": _get_loader(request).get("error.otp_empty", "OTP code cannot be empty"),
                }
            )

        user_id = request.user.id

        client = _create_system_mgmt_client()
        res = client.verify_otp_code_by_user_id(user_id, otp_code)

        if not res.get("result"):
            logger.warning(f"OTP verification failed for user_id: {user_id}")

        return JsonResponse(res)
    except Exception as e:
        logger.error(f"OTP verification error: {e}")
        return JsonResponse(
            {
                "result": False,
                "message": _get_loader(request).get("error.system_error", "System error occurred"),
            }
        )


@api_exempt
def verify_otp_login(request):
    """
    Verify OTP code with challenge_id and complete two-factor authentication.

    This is the second phase of login for OTP-enabled users.
    On success, issues JWT token and sets bklite_token cookie.
    """
    try:
        data = _parse_request_data(request)
        challenge_id = data.get("challenge_id", "").strip()
        otp_code = data.get("otp_code", "").strip()

        if not challenge_id or not otp_code:
            return JsonResponse(
                {
                    "result": False,
                    "message": _get_loader(request).get("error.otp_challenge_empty", "Challenge ID and OTP code are required"),
                }
            )

        # Get client IP for rate limiting
        client_ip = _get_client_ip(request)

        client = _create_system_mgmt_client()
        res = client.verify_otp_login(challenge_id, otp_code, client_ip)

        response = JsonResponse(res)

        # Set bklite_token cookie on successful OTP verification
        if res.get("result") and res.get("data", {}).get("token"):
            _set_auth_cookie_on_response(response, res["data"]["token"])
            logger.info(f"OTP login successful for user: {res['data'].get('username')}")
        else:
            logger.warning(f"OTP login failed: {res.get('message')}")

        return response
    except Exception as e:
        logger.error(f"OTP login error: {e}")
        return JsonResponse(
            {
                "result": False,
                "message": _get_loader(request).get("error.system_error", "System error occurred"),
            }
        )


def get_client(request):
    try:
        client = _create_system_mgmt_client()
        return_data = client.get_client("", request.user.username, getattr(request.user, "domain", "domain.com"))
        # 翻译内置应用的描述和标签
        if return_data.get("result") and return_data.get("data"):
            loader = _get_loader(request)
            for i in return_data["data"]:
                if i.get("is_build_in"):
                    # 翻译 description（格式为 "app.xxx"）
                    if i.get("description"):
                        i["description"] = loader.get(i["description"], i["description"])
                    # 翻译 tags 列表（格式为 "tag.xxx"）
                    if i.get("tags"):
                        translated_tags = []
                        for tag in i["tags"]:
                            translated_tags.append(loader.get(tag, tag))
                        i["tags"] = translated_tags
            # EE: 根据 license 过滤未授权的模块
            try:
                mod = __import__("apps.core.enterprise.license_filter", fromlist=["filter_clients_by_license"])
                return_data["data"] = mod.filter_clients_by_license(return_data["data"])
            except (ImportError, ModuleNotFoundError):
                pass
        return JsonResponse(return_data)
    except Exception as e:
        logger.error(f"Error retrieving client info: {e}")
        return JsonResponse(
            {
                "result": False,
                "message": _get_loader(request).get("error.system_error", "System error occurred"),
            }
        )


def get_my_client(request):
    try:
        client = _create_system_mgmt_client()
        client_id = request.GET.get("client_id", "") or os.getenv("CLIENT_ID", "")
        return_data = client.get_client(client_id, "")
        return JsonResponse(return_data)
    except Exception as e:
        logger.error(f"Error retrieving my client info: {e}")
        return JsonResponse(
            {
                "result": False,
                "message": _get_loader(request).get("error.system_error", "System error occurred"),
            }
        )


def get_client_detail(request):
    client_name = request.GET.get("name", "")

    if not client_name:
        return JsonResponse({"result": False, "message": "Client name is required"})

    try:
        client = _create_system_mgmt_client()
        return_data = client.get_client_detail(client_id=client_name)
        if return_data.get("result") and return_data.get("data"):
            data = return_data["data"]
            locale = getattr(getattr(request, "user", None), "locale", None) or "en"
            loader = LanguageLoader(app="system_mgmt", default_lang=locale)
            desc_key = data.get("description", "")
            translated = loader.get(desc_key) if desc_key else ""
            data["description"] = translated or desc_key
        return JsonResponse(return_data)
    except Exception as e:
        logger.error(f"Error retrieving client detail for {client_name}: {e}")
        return JsonResponse(
            {
                "result": False,
                "message": _get_loader(request).get("error.system_error", "System error occurred"),
            }
        )


def get_user_menus(request):
    client_name = request.GET.get("name", "")

    if not client_name:
        return JsonResponse({"result": False, "message": "Client name is required"})
    app_admin = f"{client_name}--admin"
    is_superuser = request.user.is_superuser or app_admin in request.user.roles
    try:
        client = _create_system_mgmt_client()
        return_data = client.get_user_menus(
            client_id=client_name,
            roles=request.user.role_ids,
            username=request.user.username,
            is_superuser=is_superuser,
        )
        return JsonResponse(return_data)
    except Exception as e:
        logger.error(f"Error retrieving user menus for {client_name}: {e}")
        return JsonResponse(
            {
                "result": False,
                "message": _get_loader(request).get("error.system_error", "System error occurred"),
            }
        )


def get_all_groups(request):
    if not getattr(request.user, "is_superuser", False):
        return JsonResponse(
            {
                "result": False,
                "message": _get_loader(request).get("error.not_authorized", "Not Authorized"),
            }
        )

    try:
        client = _create_system_mgmt_client()
        return_data = client.get_all_groups()
        return JsonResponse(return_data)
    except Exception as e:
        logger.error(f"Error retrieving all groups: {e}")
        return JsonResponse(
            {
                "result": False,
                "message": _get_loader(request).get("error.system_error", "System error occurred"),
            }
        )


def bk_lite_login(username, password, domain):
    system_client = SystemMgmt()
    res = system_client.get_namespace_by_domain(domain)
    if not res["result"]:
        return res
    namespace = res["data"]
    client = RpcClient(namespace)
    res = client.request("login", username=username, password=password)
    if not res["result"]:
        return res
    login_res = system_client.bk_lite_user_login(res["data"]["username"], domain)
    return login_res


@api_exempt
def get_domain_list(request):
    client = SystemMgmt()
    res = client.get_login_module_domain_list()
    return JsonResponse(res)


@api_exempt
def get_login_auth_bindings(request):
    if _is_login_auth_bindings_rate_limited(request):
        response = JsonResponse({"result": False, "message": "Too many requests"}, status=429)
        response["Cache-Control"] = "no-store"
        return response

    client = SystemMgmt()
    response = JsonResponse(client.get_login_auth_bindings())
    response["Cache-Control"] = f"public, max-age={LOGIN_AUTH_BINDINGS_CACHE_SECONDS}"
    return response


def _is_login_auth_bindings_rate_limited(request) -> bool:
    client_ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",", 1)[0].strip()
    if not client_ip:
        client_ip = request.META.get("REMOTE_ADDR", "unknown")
    cache_key = f"login_auth_bindings_rate:{client_ip}"
    if cache.add(cache_key, 1, timeout=LOGIN_AUTH_BINDINGS_RATE_WINDOW_SECONDS):
        return False
    try:
        request_count = cache.incr(cache_key)
    except ValueError:
        cache.set(cache_key, 1, timeout=LOGIN_AUTH_BINDINGS_RATE_WINDOW_SECONDS)
        return False
    return request_count > LOGIN_AUTH_BINDINGS_RATE_LIMIT


@api_exempt
def start_login_auth(request):
    if request.method != "POST":
        return JsonResponse({"result": False, "message": "Method not allowed"}, status=405)

    try:
        data = _parse_request_data(request)
        callback_url = (data.get("callback_url") or "/").strip() or "/"
        redirect_origin = (data.get("redirect_origin") or "").strip() or None
        legacy_external_callback_url = (data.get("legacy_external_callback_url") or "").strip() or None
        legacy_third_login_code = (data.get("legacy_third_login_code") or "").strip() or None
        binding_id = data.get("binding_id")

        if not _is_safe_relative_callback_url(callback_url):
            return JsonResponse({"result": False, "message": "callback_url must be an in-site relative path"}, status=400)
        if legacy_external_callback_url and not legacy_third_login_code:
            return JsonResponse(
                {"result": False, "message": "legacy_external_callback_url requires third_login_code"}, status=400
            )
        if legacy_external_callback_url and not _is_safe_legacy_external_callback_url(legacy_external_callback_url):
            return JsonResponse({"result": False, "message": "legacy_external_callback_url must be an absolute HTTP(S) URL"}, status=400)
        if redirect_origin and not validate_redirect_origin(request, redirect_origin):
            redirect_origin = None

        try:
            binding_id = int(binding_id)
        except (TypeError, ValueError):
            return JsonResponse({"result": False, "message": "binding_id is required"}, status=400)

        binding = _get_login_auth_binding_by_id(binding_id)
        if not binding:
            return JsonResponse({"result": False, "message": "Login auth binding not found"}, status=404)

        auth_request = create_auth_request(
            binding_id=binding.id,
            provider_key=binding.integration_instance.provider_key,
            callback_url=callback_url,
            redirect_origin=redirect_origin,
            legacy_external_callback_url=legacy_external_callback_url,
            legacy_third_login_code=legacy_third_login_code,
        )
        state = build_auth_request_state(
            auth_request_id=auth_request["auth_request_id"],
            binding_id=binding.id,
            callback_url=callback_url,
        )
        redirect_result = build_login_auth_redirect(
            binding,
            redirect_uri=get_login_auth_callback_uri(request=request, redirect_origin=redirect_origin),
            state=state,
        )
        redirect_payload = getattr(redirect_result, "payload", {}) or {}
        redirect_dict = redirect_result.to_dict() if hasattr(redirect_result, "to_dict") else {}
        login_url = (
            redirect_payload.get("login_url")
            or redirect_payload.get("authorize_url")
            or redirect_payload.get("url")
            or redirect_dict.get("login_url")
            or redirect_dict.get("authorize_url")
            or redirect_dict.get("url")
        )
        if not redirect_result.success or not login_url:
            logger.warning("Failed to build login auth redirect for binding: %s", binding.id)
            return JsonResponse(
                {"result": False, "message": redirect_result.summary or "Failed to build login url"},
                status=400,
            )

        return JsonResponse(
            {
                "result": True,
                "data": {
                    "auth_request_id": auth_request["auth_request_id"],
                    "poll_token": auth_request["poll_token"],
                    "login_url": login_url,
                    "expires_at": auth_request["expires_at"],
                },
                "message": "",
            }
        )
    except Exception as e:
        logger.error(f"Start login auth error: {e}")
        return JsonResponse(
            {
                "result": False,
                "message": _get_loader(request).get("error.system_error", "System error occurred"),
            },
            status=500,
        )


@api_exempt
def get_login_auth_request_status(request, auth_request_id):
    poll_token = request.GET.get("poll_token", "").strip()
    if not poll_token:
        return JsonResponse({"result": False, "message": "poll_token is required"}, status=400)

    auth_request = get_auth_request(auth_request_id)
    if not auth_request:
        return JsonResponse(
            {
                "result": True,
                "data": {
                    "status": "expired",
                    "error_message": "Login auth request has expired",
                },
                "message": "",
            }
        )

    if not validate_poll_token(auth_request, poll_token):
        return JsonResponse({"result": False, "message": "Invalid poll token"}, status=403)

    payload = {
        "status": auth_request.get("status", "pending"),
        "error_message": auth_request.get("error_message", ""),
        "expires_at": auth_request.get("expires_at"),
        "completed_at": auth_request.get("completed_at"),
    }
    if auth_request.get("status") == "success" and auth_request.get("login_result"):
        payload["login_result"] = auth_request["login_result"]

    return JsonResponse({"result": True, "data": payload, "message": ""})


@api_exempt
def login_auth_callback(request):
    state = request.GET.get("state", "").strip()
    code = request.GET.get("code", "").strip()
    provider_error = request.GET.get("error", "").strip()
    error_description = request.GET.get("error_description", "").strip()

    state_payload = parse_auth_request_state(state)
    if not state_payload:
        return _build_login_auth_result_redirect(request, "failed", "认证状态无效或已过期，请返回原页面重试。")

    auth_request_id = state_payload["auth_request_id"]
    auth_request = get_auth_request(auth_request_id)
    if not auth_request:
        return _build_login_auth_result_redirect(request, "expired", "认证请求已过期，请返回原页面重新发起认证。")

    # 集中读一次(后续 6 处 status 分支共用);state 解析失败/auth_request 缺失分支
    # 走相对路径,这里 redirect_origin 自然为 None
    redirect_origin = (auth_request or {}).get("redirect_origin") or None

    current_status = auth_request.get("status", "pending")
    if current_status != "pending":
        terminal_messages = {
            "success": "认证已完成，可返回原页面继续。",
            "cancelled": "认证已取消，可返回原页面重试。",
            "expired": "认证请求已过期，请返回原页面重新发起认证。",
            "failed": "认证失败，请返回原页面重试。",
        }
        return _build_login_auth_result_redirect(
            request,
            current_status,
            terminal_messages.get(current_status, "认证状态已完成，可返回原页面查看结果。"),
            redirect_origin=redirect_origin,
        )

    if provider_error:
        message = error_description or provider_error
        update_auth_request_status(auth_request_id, status="cancelled", error_message=message)
        return _build_login_auth_result_redirect(request, "cancelled", "认证已取消，可返回原页面重试。", redirect_origin=redirect_origin)

    if not code:
        update_auth_request_status(auth_request_id, status="failed", error_message="Missing provider code")
        return _build_login_auth_result_redirect(request, "failed", "认证失败，请返回原页面重试。", redirect_origin=redirect_origin)

    try:
        client = SystemMgmt()
        result = client.login_with_binding(state_payload["binding_id"], code)
    except Exception as e:
        logger.error(f"Login auth callback error: {e}")
        update_auth_request_status(auth_request_id, status="failed", error_message=str(e))
        return _build_login_auth_result_redirect(request, "failed", "认证失败，请返回原页面重试。", redirect_origin=redirect_origin)

    if not result.get("result"):
        error_message = result.get("message", "Login auth callback failed")
        update_auth_request_status(auth_request_id, status="failed", error_message=error_message)
        return _build_login_auth_result_redirect(request, "failed", "认证失败，请返回原页面重试。", redirect_origin=redirect_origin)

    login_result = result.get("data", {}) or {}
    login_result.setdefault("redirect_url", state_payload["callback_url"])
    if auth_request.get("legacy_external_callback_url") and auth_request.get("legacy_third_login_code"):
        login_result["legacy_external_callback_url"] = auth_request["legacy_external_callback_url"]
        login_result["legacy_third_login_code"] = auth_request["legacy_third_login_code"]
    update_auth_request_status(
        auth_request_id,
        status="success",
        login_result=login_result,
    )

    response = _build_login_auth_result_redirect(request, "success", "认证已完成，可返回原页面继续。", redirect_origin=redirect_origin)
    if login_result.get("token"):
        _set_auth_cookie_on_response(response, login_result["token"])
    return response
