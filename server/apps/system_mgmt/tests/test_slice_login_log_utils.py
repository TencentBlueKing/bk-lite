import pydantic.root_model  # noqa

import pytest

from apps.system_mgmt.models import UserLoginLog
from apps.system_mgmt.utils import login_log_utils

pytestmark = pytest.mark.django_db


# ----------------------- parse_user_agent (纯函数) -----------------------


@pytest.mark.parametrize(
    "ua,exp_os,exp_browser",
    [
        ("", "", ""),
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64) Chrome/120.0 Safari/537.36",
            "Windows 10/11",
            "Chrome 120.0",
        ),
        ("Mozilla/5.0 (Windows NT 6.1) Gecko Firefox/115.0", "Windows 7", "Firefox 115.0"),
        ("Mozilla/5.0 (Windows NT 6.3)", "Windows 8.1", ""),
        ("Mozilla/5.0 (Windows NT 6.2)", "Windows 8", ""),
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Version/16.1 Safari/605.1",
            "macOS 10.15.7",
            "Safari 16.1",
        ),
        ("Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit", "macOS", ""),
        ("Mozilla/5.0 (X11; Linux x86_64)", "Linux", ""),
        ("Mozilla/5.0 (Linux; Android 13; Pixel) Chrome/110.0 Safari/537", "Android 13", "Chrome 110.0"),
        # 注:当前解析器把 iPhone UA(含 "Mac OS X")误判为 macOS,锁定现状(疑似缺陷,待确认)
        ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X)", "macOS", ""),
        (
            "Mozilla/5.0 (Windows NT 10.0) Chrome/120.0 Safari/537 Edg/120.0",
            "Windows 10/11",
            "Edge 120.0",
        ),
        ("Opera/9.80 (Windows NT 6.1)", "Windows 7", "Opera"),
        ("Mozilla/5.0 (Windows NT 10.0; Trident/7.0; rv:11.0) like Gecko", "Windows 10/11", "Internet Explorer"),
    ],
)
def test_parse_user_agent(ua, exp_os, exp_browser):
    os_info, browser_info = login_log_utils.parse_user_agent(ua)
    assert os_info == exp_os
    assert browser_info == exp_browser


# ----------------------- get_ip_location -----------------------


@pytest.mark.parametrize("ip,exp", [("127.0.0.1", "本地"), ("::1", "本地"), ("localhost", "本地")])
def test_get_ip_location_本地(ip, exp):
    assert login_log_utils.get_ip_location(ip) == exp


@pytest.mark.parametrize("ip", ["10.0.0.5", "172.16.1.1", "192.168.1.1", "169.254.0.1"])
def test_get_ip_location_内网(ip):
    assert login_log_utils.get_ip_location(ip) == "内网"


def test_get_ip_location_公网成功(mocker):
    fake_resp = mocker.Mock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "status": "success",
        "country": "中国",
        "regionName": "广东",
        "city": "深圳",
    }
    fake_client = mocker.MagicMock()
    fake_client.get.return_value = fake_resp
    fake_client.__enter__.return_value = fake_client
    mocker.patch("apps.system_mgmt.utils.login_log_utils.httpx.Client", return_value=fake_client)

    assert login_log_utils.get_ip_location("8.8.8.8") == "中国 广东 深圳"


def test_get_ip_location_api失败状态(mocker):
    fake_resp = mocker.Mock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"status": "fail"}
    fake_client = mocker.MagicMock()
    fake_client.get.return_value = fake_resp
    fake_client.__enter__.return_value = fake_client
    mocker.patch("apps.system_mgmt.utils.login_log_utils.httpx.Client", return_value=fake_client)

    assert login_log_utils.get_ip_location("8.8.8.8") == ""


def test_get_ip_location_异常返回空(mocker):
    mocker.patch(
        "apps.system_mgmt.utils.login_log_utils.httpx.Client",
        side_effect=RuntimeError("timeout"),
    )
    assert login_log_utils.get_ip_location("8.8.8.8") == ""


# ----------------------- get_user_agent -----------------------


def test_get_user_agent_截断500(rf):
    long_ua = "A" * 600
    request = rf.get("/", HTTP_USER_AGENT=long_ua)
    ua = login_log_utils.get_user_agent(request)
    assert len(ua) == 500


def test_get_user_agent_缺失():
    class Req:
        META = {}

    assert login_log_utils.get_user_agent(Req()) == ""


# ----------------------- log_user_login (写库) -----------------------


def test_log_user_login_成功写库():
    entry = login_log_utils.log_user_login(
        username="alice",
        source_ip="1.2.3.4",
        status=UserLoginLog.STATUS_SUCCESS,
        user_agent="Mozilla/5.0 (Windows NT 10.0) Chrome/120.0 Safari/537",
    )
    assert entry is not None
    assert entry.pk is not None
    assert entry.os_info == "Windows 10/11"
    assert entry.browser_info == "Chrome 120.0"
    # 成功状态下 failure_reason 被清空
    assert entry.failure_reason == ""


def test_log_user_login_失败保留原因():
    entry = login_log_utils.log_user_login(
        username="bob",
        source_ip="1.2.3.4",
        status=UserLoginLog.STATUS_FAILED,
        failure_reason="密码错误",
    )
    assert entry.failure_reason == "密码错误"
    assert entry.status == UserLoginLog.STATUS_FAILED


def test_log_user_login_异常返回None(mocker):
    mocker.patch.object(
        UserLoginLog.objects,
        "create",
        side_effect=RuntimeError("db error"),
    )
    result = login_log_utils.log_user_login("x", "1.2.3.4", UserLoginLog.STATUS_SUCCESS)
    assert result is None


# ----------------------- log_user_login_from_request -----------------------


def test_log_user_login_from_request(rf, mocker):
    request = rf.get("/", HTTP_USER_AGENT="Mozilla/5.0 (X11; Linux x86_64)")
    mocker.patch(
        "apps.system_mgmt.utils.login_log_utils.get_client_ip",
        return_value=("9.9.9.9", True),
    )
    entry = login_log_utils.log_user_login_from_request(request, "carol", UserLoginLog.STATUS_SUCCESS)
    assert entry.source_ip == "9.9.9.9"
    assert entry.os_info == "Linux"
    assert entry.username == "carol"


def test_log_user_login_from_request_无ip回退(rf, mocker):
    request = rf.get("/")
    mocker.patch(
        "apps.system_mgmt.utils.login_log_utils.get_client_ip",
        return_value=(None, False),
    )
    entry = login_log_utils.log_user_login_from_request(request, "dan", UserLoginLog.STATUS_SUCCESS)
    assert entry.source_ip == "0.0.0.0"
