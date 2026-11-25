"""
用户登录日志工具函数

提供登录日志记录功能
"""

import re

import httpx
from ipware import get_client_ip

from apps.core.logger import system_mgmt_logger as logger
from apps.system_mgmt.models import UserLoginLog

LOGIN_METHOD_BUILTIN = "bk_lite_builtin"
LOGIN_METHOD_UNRECORDED = "未记录"
CLIENT_UNRECORDED = "未记录"
OTP_DISPLAY_SUFFIX = "(OTP)"
LOGIN_METHOD_LABELS = {
    LOGIN_METHOD_BUILTIN: "本地密码",
    "ad": "AD",
    "feishu": "飞书",
    "wecom": "企业微信",
    "wechat": "微信",
    "blueking": "蓝鲸",
}


def parse_user_agent(user_agent):
    """
    解析 User-Agent 字符串，提取操作系统和浏览器信息

    参数:
        user_agent: User-Agent 字符串

    返回:
        tuple: (os_info, browser_info)
    """
    if not user_agent:
        return "", ""

    os_info = ""
    browser_info = ""

    # 解析操作系统
    if "Windows NT 10.0" in user_agent:
        os_info = "Windows 10/11"
    elif "Windows NT 6.3" in user_agent:
        os_info = "Windows 8.1"
    elif "Windows NT 6.2" in user_agent:
        os_info = "Windows 8"
    elif "Windows NT 6.1" in user_agent:
        os_info = "Windows 7"
    elif "Windows" in user_agent:
        os_info = "Windows"
    elif "Mac OS X" in user_agent:
        # 提取版本号 (例如: Mac OS X 10_15_7)
        mac_match = re.search(r"Mac OS X (\d+[_\.]\d+[_\.]\d+)", user_agent)
        if mac_match:
            version = mac_match.group(1).replace("_", ".")
            os_info = f"macOS {version}"
        else:
            os_info = "macOS"
    elif "Linux" in user_agent and "Android" not in user_agent:
        os_info = "Linux"
    elif "Android" in user_agent:
        # 提取版本号
        android_match = re.search(r"Android (\d+\.?\d*)", user_agent)
        if android_match:
            os_info = f"Android {android_match.group(1)}"
        else:
            os_info = "Android"
    elif "iPhone" in user_agent or "iPad" in user_agent:
        # 提取 iOS 版本
        ios_match = re.search(r"OS (\d+_\d+)", user_agent)
        if ios_match:
            version = ios_match.group(1).replace("_", ".")
            device = "iPad" if "iPad" in user_agent else "iPhone"
            os_info = f"iOS {version} ({device})"
        else:
            os_info = "iOS"

    # 解析浏览器
    if "Edg/" in user_agent or "Edge/" in user_agent:
        edge_match = re.search(r"Edg?e?/(\d+\.\d+)", user_agent)
        if edge_match:
            browser_info = f"Edge {edge_match.group(1)}"
        else:
            browser_info = "Edge"
    elif "Chrome/" in user_agent and "Safari/" in user_agent:
        chrome_match = re.search(r"Chrome/(\d+\.\d+)", user_agent)
        if chrome_match:
            browser_info = f"Chrome {chrome_match.group(1)}"
        else:
            browser_info = "Chrome"
    elif "Firefox/" in user_agent:
        firefox_match = re.search(r"Firefox/(\d+\.\d+)", user_agent)
        if firefox_match:
            browser_info = f"Firefox {firefox_match.group(1)}"
        else:
            browser_info = "Firefox"
    elif "Safari/" in user_agent and "Chrome" not in user_agent:
        safari_match = re.search(r"Version/(\d+\.\d+)", user_agent)
        if safari_match:
            browser_info = f"Safari {safari_match.group(1)}"
        else:
            browser_info = "Safari"
    elif "Opera/" in user_agent or "OPR/" in user_agent:
        browser_info = "Opera"
    elif "MSIE" in user_agent or "Trident/" in user_agent:
        browser_info = "Internet Explorer"

    return os_info, browser_info


def get_ip_location(ip_address):
    """
    查询 IP 地址的地理位置

    使用免费的 IP 地理位置 API 查询

    参数:
        ip_address: IP 地址

    返回:
        str: 地理位置字符串，格式为 "国家 省份 城市" 或空字符串
    """
    # 跳过本地IP
    if ip_address in ["127.0.0.1", "::1", "0.0.0.0", "localhost"]:
        return "本地"

    # 跳过内网IP
    if ip_address.startswith(("10.", "172.", "192.168.", "169.254.")):
        return "内网"

    try:
        # 使用免费的 ip-api.com 服务 (每分钟限制45次请求)
        # 对于生产环境，建议使用付费服务或自建IP库
        url = f"http://ip-api.com/json/{ip_address}?lang=zh-CN&fields=status,country,regionName,city"

        with httpx.Client(timeout=3.0) as client:
            response = client.get(url)

            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    parts = []
                    if data.get("country"):
                        parts.append(data["country"])
                    if data.get("regionName"):
                        parts.append(data["regionName"])
                    if data.get("city"):
                        parts.append(data["city"])
                    return " ".join(parts) if parts else ""

    except Exception as e:
        logger.warning(f"Failed to get IP location for {ip_address}: {e}")

    return ""


def get_user_agent(request):
    """从请求中获取 User-Agent"""
    return request.META.get("HTTP_USER_AGENT", "")[:500]


def log_user_login(
    username,
    source_ip,
    status,
    domain="domain.com",
    failure_reason="",
    user_agent="",
    login_method="",
    used_otp=False,
):
    """
    记录用户登录日志

    参数:
        username: 用户名
        source_ip: 源IP地址
        status: 登录状态 ('success' 或 'failed')
        domain: 域名，默认 'domain.com'
        failure_reason: 失败原因，仅在 status='failed' 时有意义
        user_agent: 用户代理字符串
        login_method: 本次登录来源的稳定键，历史行保持空
        used_otp: 是否经过 OTP 校验后签发凭据

    返回:
        UserLoginLog 实例，如果记录失败则返回 None
    """
    try:
        # 解析 User-Agent
        os_info, browser_info = parse_user_agent(user_agent)

        # 查询 IP 地理位置
        # location = get_ip_location(source_ip)

        log_entry = UserLoginLog.objects.create(
            username=username,
            source_ip=source_ip,
            status=status,
            domain=domain,
            failure_reason=failure_reason if status == UserLoginLog.STATUS_FAILED else "",
            user_agent=user_agent,
            os_info=os_info,
            browser_info=browser_info,
            login_method=login_method or "",
            used_otp=bool(used_otp),
            # location=location,
        )
        # logger.info(
        #     f"Login log recorded: username={username}, status={status}, "
        #     f"ip={source_ip}, location={location}, os={os_info}, browser={browser_info}, domain={domain}"
        # )
        return log_entry
    except Exception as e:
        logger.error(f"Failed to record login log: {e}", exc_info=True)
        return None


def log_user_login_from_request(
    request,
    username,
    status,
    domain="domain.com",
    failure_reason="",
    login_method="",
    used_otp=False,
):
    """
    从请求对象记录用户登录日志

    自动从请求中提取 IP 和 User-Agent

    参数:
        request: Django 请求对象
        username: 用户名
        status: 登录状态 ('success' 或 'failed')
        domain: 域名，默认 'domain.com'
        failure_reason: 失败原因
        login_method: 本次登录来源的稳定键
        used_otp: 是否经过 OTP 校验后签发凭据

    返回:
        UserLoginLog 实例，如果记录失败则返回 None
    """
    source_ip, _ = get_client_ip(request)
    user_agent = get_user_agent(request)

    return log_user_login(
        username=username,
        source_ip=source_ip or "0.0.0.0",
        status=status,
        domain=domain,
        failure_reason=failure_reason,
        user_agent=user_agent,
        login_method=login_method,
        used_otp=used_otp,
    )


def format_login_method_display(login_method, used_otp=False, loader=None):
    method = (login_method or "").strip()
    if not method:
        label = (loader.get("login_method.unrecorded") if loader else None) or LOGIN_METHOD_UNRECORDED
    else:
        mapped = LOGIN_METHOD_LABELS.get(method)
        translated = loader.get(f"login_method.{method}") if loader and mapped else None
        label = translated or mapped or method
    if used_otp:
        suffix = (loader.get("login_method.otp_suffix") if loader else None) or OTP_DISPLAY_SUFFIX
        return f"{label}{suffix}"
    return label


def format_client_display(os_info, browser_info, loader=None):
    parts = [part for part in ((os_info or "").strip(), (browser_info or "").strip()) if part]
    if parts:
        return " ".join(parts)
    return (loader.get("login_method.unrecorded") if loader else None) or CLIENT_UNRECORDED


def login_response_issued_token(result):
    if not isinstance(result, dict) or not result.get("result"):
        return False
    data = result.get("data") or {}
    return bool(data.get("token"))


def login_response_otp_challenge_id(result):
    if not isinstance(result, dict) or not result.get("result"):
        return None
    data = result.get("data") or {}
    challenge_id = data.get("challenge_id")
    if data.get("require_otp") and challenge_id and not data.get("token"):
        return challenge_id
    return None


def login_data_issued_token(data):
    return bool(isinstance(data, dict) and data.get("token"))


def login_data_otp_challenge_id(data):
    if not isinstance(data, dict):
        return None
    challenge_id = data.get("challenge_id")
    if data.get("require_otp") and challenge_id and not data.get("token"):
        return challenge_id
    return None


def resolve_binding_login_method(binding_id):
    try:
        pk = int(binding_id)
    except (TypeError, ValueError):
        return ""
    from apps.system_mgmt.models import LoginAuthBinding

    binding = LoginAuthBinding.objects.select_related("integration_instance").filter(id=pk).first()
    if not binding or binding.integration_instance is None:
        return ""
    return (binding.integration_instance.provider_key or "").strip()


def remember_otp_challenge_login_method(challenge_id, login_method):
    if not challenge_id or not login_method:
        return False
    from apps.system_mgmt.otp_challenge import set_challenge_login_method

    return set_challenge_login_method(challenge_id, login_method)
