import json
import logging
import os

from django.http import JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext as _
from rest_framework.decorators import api_view

from apps.core.utils.exempt import api_exempt
from apps.rpc.base import RpcClient
from apps.rpc.system_mgmt import SystemMgmt

logger = logging.getLogger(__name__)


def _create_system_mgmt_client():
    """创建SystemMgmt客户端"""
    return SystemMgmt()


def _parse_request_data(request):
    """解析请求数据"""
    if hasattr(request, "body") and request.body:
        try:
            return json.loads(request.body)
        except json.JSONDecodeError:
            return request.POST.dict()
    return request.POST.dict()


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
        username = data.get("username", "").strip()
        password = data.get("password", "")
        domain = data.get("domain", "")
        c_url = data.get("redirect_url", "").strip()  # 获取回调URL

        if not username or not password:
            return JsonResponse({"result": False, "message": _("Username or password cannot be empty")})
        if domain == "domain.com":
            client = SystemMgmt()
            res = client.login(username, password)
        else:
            res = bk_lite_login(username, password, domain)
        if not res.get("result"):
            logger.warning(f"Login failed for user: {username}")
        else:
            # 登录成功时，如果有c_url参数，添加到响应中
            if c_url:
                if "data" not in res:
                    res["data"] = {}
                res["data"]["redirect_url"] = c_url
                logger.info(f"Login successful for user: {username}, redirect to: {c_url}")
        return JsonResponse(res)
    except Exception as e:
        logger.error(f"Login error: {e}")
        return JsonResponse({"result": False, "message": _("System error occurred")})


@api_exempt
def wechat_user_register(request):
    try:
        data = _parse_request_data(request)
        user_id = data.get("user_id", "").strip()
        nick_name = data.get("nick_name", "").strip()

        if not user_id:
            return JsonResponse({"result": False, "message": _("user_id cannot be empty")})

        client = _create_system_mgmt_client()
        res = client.wechat_user_register(user_id, nick_name)

        if not res.get("result"):
            logger.warning(f"WeChat registration failed for user_id: {user_id}")

        return JsonResponse(res)
    except Exception as e:
        logger.error(f"WeChat registration error: {e}")
        return JsonResponse({"result": False, "message": _("System error occurred")})


@api_exempt
def get_wechat_settings(request):
    try:
        client = _create_system_mgmt_client()
        res = client.get_wechat_settings()
        return JsonResponse(res)
    except Exception as e:
        logger.error(f"Error retrieving WeChat settings: {e}")
        return JsonResponse({"result": False, "message": _("System error occurred")})


@api_exempt
def get_bk_settings(request):
    bk_token = request.COOKIES.get("bk_token", "")
    client = SystemMgmt()
    res = client.verify_bk_token(bk_token)
    return JsonResponse(res)


@api_exempt
def reset_pwd(request):
    try:
        data = _parse_request_data(request)
        username = data.get("username", "").strip()
        password = data.get("password", "")

        if not username or not password:
            return JsonResponse({"result": False, "message": _("Username or password cannot be empty")})

        client = _create_system_mgmt_client()
        res = client.reset_pwd(username, password)

        if not res.get("result"):
            logger.warning(f"Password reset failed for user: {username}")

        return JsonResponse(res)
    except Exception as e:
        logger.error(f"Password reset error: {e}")
        return JsonResponse({"result": False, "message": _("System error occurred")})


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
            },
        }

        return JsonResponse(response_data)
    except Exception as e:
        logger.error(f"Error retrieving login info: {e}")
        return JsonResponse({"result": False, "message": _("System error occurred")})


@api_exempt
def generate_qr_code(request):
    try:
        username = request.GET.get("username", "").strip()

        if not username:
            return JsonResponse({"result": False, "message": _("Username cannot be empty")})

        client = _create_system_mgmt_client()
        res = client.generate_qr_code(username)

        if not res.get("result"):
            logger.warning(f"QR code generation failed for user: {username}")

        return JsonResponse(res)
    except Exception as e:
        logger.error(f"QR code generation error: {e}")
        return JsonResponse({"result": False, "message": _("System error occurred")})


@api_exempt
def verify_otp_code(request):
    try:
        data = _parse_request_data(request)
        username = data.get("username", "").strip()
        otp_code = data.get("otp_code", "").strip()

        if not username or not otp_code:
            return JsonResponse({"result": False, "message": _("Username or OTP code cannot be empty")})

        client = _create_system_mgmt_client()
        res = client.verify_otp_code(username, otp_code)

        if not res.get("result"):
            logger.warning(f"OTP verification failed for user: {username}")

        return JsonResponse(res)
    except Exception as e:
        logger.error(f"OTP verification error: {e}")
        return JsonResponse({"result": False, "message": _("System error occurred")})


def get_client(request):
    try:
        client = _create_system_mgmt_client()
        return_data = client.get_client("", request.user.username, getattr(request.user, "domain", "domain.com"))
        if return_data["result"]:
            for i in return_data["data"]:
                i["description"] = _(i["description"]) if i.get("is_build_in") else i["description"]
        return JsonResponse(return_data)
    except Exception as e:
        logger.error(f"Error retrieving client info: {e}")
        return JsonResponse({"result": False, "message": _("System error occurred")})


def get_my_client(request):
    try:
        client = _create_system_mgmt_client()
        client_id = request.GET.get("client_id", "") or os.getenv("CLIENT_ID", "")
        return_data = client.get_client(client_id, "")
        return JsonResponse(return_data)
    except Exception as e:
        logger.error(f"Error retrieving my client info: {e}")
        return JsonResponse({"result": False, "message": _("System error occurred")})


def get_client_detail(request):
    client_name = request.GET.get("name", "")

    if not client_name:
        return JsonResponse({"result": False, "message": "Client name is required"})

    try:
        client = _create_system_mgmt_client()
        return_data = client.get_client_detail(client_id=client_name)
        return JsonResponse(return_data)
    except Exception as e:
        logger.error(f"Error retrieving client detail for {client_name}: {e}")
        return JsonResponse({"result": False, "message": _("System error occurred")})


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
        return JsonResponse({"result": False, "message": _("System error occurred")})


def get_all_groups(request):
    if not getattr(request.user, "is_superuser", False):
        return JsonResponse({"result": False, "message": _("Not Authorized")})

    try:
        client = _create_system_mgmt_client()
        return_data = client.get_all_groups()
        return JsonResponse(return_data)
    except Exception as e:
        logger.error(f"Error retrieving all groups: {e}")
        return JsonResponse({"result": False, "message": _("System error occurred")})


def bk_lite_login(username, password, domain):
    system_client = SystemMgmt()
    res = system_client.get_namespace_by_domain(domain)
    if not res["result"]:
        return JsonResponse(res)
    namespace = res["data"]
    client = RpcClient(namespace)
    res = client.request("login", username=username, password=password)
    if not res["result"]:
        return JsonResponse(res)
    login_res = system_client.bk_lite_user_login(res["data"]["username"], domain)
    return login_res


@api_exempt
def get_domain_list(request):
    client = SystemMgmt()
    res = client.get_login_module_domain_list()
    return JsonResponse(res)
