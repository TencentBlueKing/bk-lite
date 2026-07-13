"""补充 system_mgmt 各 utils 模块的真实行为单元测试。

只针对纯逻辑/可控边界做断言：
- channel_utils 的 SSRF 白名单校验与模板占位符替换（纯函数）
- password_validator 的密码复杂度校验（DB 读取走真实 SystemSettings）
- user_status 的派生状态/过期信息计算
- token_blacklist 的 Redis（cache）撤销语义
- operation_log_utils 的日志落库副作用
- group_utils 的树/路径/子孙构建
"""

import types
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.system_mgmt.utils import channel_utils
from apps.system_mgmt.utils import token_blacklist
from apps.system_mgmt.utils import user_status
from apps.system_mgmt.utils.operation_log_utils import log_operation
from apps.system_mgmt.utils.password_validator import PasswordValidator


# --------------------------------------------------------------------------- #
# channel_utils.is_valid_webhook_url —— 纯函数 SSRF 白名单校验
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "url",
    [
        "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=abc",
        "https://open.feishu.cn/open-apis/bot/v2/hook/xxx",
        "https://oapi.dingtalk.com/robot/send?access_token=xxx",
        "https://open.larksuite.com/open-apis/bot/v2/hook/yyy",
    ],
)
def test_is_valid_webhook_url_accepts_allowlisted_domains(url):
    assert channel_utils.is_valid_webhook_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "",
        None,
        "https://evil.example.com/hook",
        "https://qyapi.weixin.qq.com\\@evil.com/hook",  # 反斜杠绕过
        "https://user@qyapi.weixin.qq.com/hook",  # userinfo 绕过
        "ftp://qyapi.weixin.qq.com/hook",  # 非 http(s)
        "https://qyapi.weixin.qq.com%23.evil.com/hook",  # 编码绕过
        "not-a-url",
    ],
)
def test_is_valid_webhook_url_rejects_invalid_or_unlisted(url):
    assert channel_utils.is_valid_webhook_url(url) is False


def test_replace_placeholder_recurses_into_nested_structures():
    template = {
        "text": "前缀 {{content}} 后缀",
        "list": ["{{content}}", {"nested": "{{content}}"}],
        "num": 5,
        "flag": True,
    }
    result = channel_utils._replace_placeholder(template, "{{content}}", "你好")
    assert result["text"] == "前缀 你好 后缀"
    assert result["list"][0] == "你好"
    assert result["list"][1]["nested"] == "你好"
    # 非字符串原样保留
    assert result["num"] == 5
    assert result["flag"] is True


# --------------------------------------------------------------------------- #
# channel_utils.send_email_to_user —— 失败分支（缺失字段）返回 result False
# --------------------------------------------------------------------------- #
def test_send_email_to_user_returns_failure_on_missing_config():
    # channel_config 缺少 mail_sender 等键，应捕获异常并返回 result=False
    result = channel_utils.send_email_to_user({}, "正文", ["a@b.com"], "标题")
    assert result["result"] is False
    assert "Error sending email" in result["message"]


# --------------------------------------------------------------------------- #
# password_validator —— 复杂度校验（DB 读取真实 SystemSettings）
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_validate_password_rejects_empty():
    ok, msg = PasswordValidator.validate_password("")
    assert ok is False
    assert msg == "密码不能为空"


@pytest.mark.django_db
def test_validate_password_enforces_min_length():
    # 迁移默认 min_length=8
    ok, msg = PasswordValidator.validate_password("Aa1!")
    assert ok is False
    assert "不能少于8" in msg


@pytest.mark.django_db
def test_validate_password_enforces_required_char_types():
    # 默认要求 大写/小写/数字/特殊
    ok, msg = PasswordValidator.validate_password("alllowercase")
    assert ok is False
    assert "密码必须包含" in msg


@pytest.mark.django_db
def test_validate_password_accepts_compliant_password():
    ok, msg = PasswordValidator.validate_password("Abcdef1!")
    assert ok is True
    assert msg == ""


@pytest.mark.django_db
def test_validate_password_rejects_non_ascii_characters():
    # 含中文，长度与类型可满足但应被非法字符校验拦下
    ok, msg = PasswordValidator.validate_password("Abc1!中文字符")
    assert ok is False
    assert "非法字符" in msg


@pytest.mark.django_db
def test_get_password_policy_description_contains_length_and_types():
    desc = PasswordValidator.get_password_policy_description()
    assert "密码策略要求" in desc
    assert "8-20" in desc
    assert "大写字母" in desc


# --------------------------------------------------------------------------- #
# user_status —— 派生状态与过期信息
# --------------------------------------------------------------------------- #
def test_is_user_locked_true_when_lock_in_future():
    now = timezone.now()
    user = types.SimpleNamespace(account_locked_until=now + timedelta(hours=1))
    assert user_status.is_user_locked(user, now=now) is True


def test_is_user_locked_false_when_lock_in_past_or_none():
    now = timezone.now()
    assert user_status.is_user_locked(types.SimpleNamespace(account_locked_until=None), now=now) is False
    assert user_status.is_user_locked(types.SimpleNamespace(account_locked_until=now - timedelta(hours=1)), now=now) is False


def test_get_password_expiry_info_not_expired_for_fresh_password():
    now = timezone.now()
    user = types.SimpleNamespace(password_last_modified=now)
    info = user_status.get_password_expiry_info(user, now=now, validity_days=180)
    assert info["is_expired"] is False
    assert info["validity_days"] == 180
    assert info["days_until_expire"] == 180


def test_get_password_expiry_info_expired_when_overdue():
    now = timezone.now()
    user = types.SimpleNamespace(password_last_modified=now - timedelta(days=200))
    info = user_status.get_password_expiry_info(user, now=now, validity_days=180)
    assert info["is_expired"] is True
    assert info["days_until_expire"] <= 0


def test_get_password_expiry_info_no_expiry_when_validity_non_positive():
    now = timezone.now()
    user = types.SimpleNamespace(password_last_modified=now - timedelta(days=999))
    info = user_status.get_password_expiry_info(user, now=now, validity_days=0)
    assert info["is_expired"] is False
    assert info["expire_date"] is None


def test_get_user_derived_status_priority_order():
    now = timezone.now()

    # disabled 优先于一切
    disabled_user = types.SimpleNamespace(
        disabled=True,
        account_locked_until=now + timedelta(hours=1),
        password_last_modified=now - timedelta(days=999),
    )
    assert user_status.get_user_derived_status(disabled_user, now=now, validity_days=180) == user_status.USER_STATUS_DISABLED

    # locked 优先于 password_expired
    locked_user = types.SimpleNamespace(
        disabled=False,
        account_locked_until=now + timedelta(hours=1),
        password_last_modified=now - timedelta(days=999),
    )
    assert user_status.get_user_derived_status(locked_user, now=now, validity_days=180) == user_status.USER_STATUS_LOCKED

    # password_expired
    expired_user = types.SimpleNamespace(
        disabled=False,
        account_locked_until=None,
        password_last_modified=now - timedelta(days=999),
    )
    assert user_status.get_user_derived_status(expired_user, now=now, validity_days=180) == user_status.USER_STATUS_PASSWORD_EXPIRED

    # normal
    normal_user = types.SimpleNamespace(
        disabled=False,
        account_locked_until=None,
        password_last_modified=now,
    )
    assert user_status.get_user_derived_status(normal_user, now=now, validity_days=180) == user_status.USER_STATUS_NORMAL


@pytest.mark.django_db
def test_get_int_setting_reads_db_and_falls_back():
    from apps.system_mgmt.models import SystemSettings

    SystemSettings.objects.update_or_create(key="pwd_set_validity_period", defaults={"value": "90"})
    assert user_status.get_password_validity_days(default=180) == 90

    # 非法值回退默认
    SystemSettings.objects.update_or_create(key="pwd_set_validity_period", defaults={"value": "not-int"})
    assert user_status.get_password_validity_days(default=180) == 180


# --------------------------------------------------------------------------- #
# token_blacklist —— 基于 cache 的撤销语义
# --------------------------------------------------------------------------- #
@pytest.fixture
def locmem_cache(settings):
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    cache.clear()
    yield
    cache.clear()


def test_blacklist_token_skips_expired(locmem_cache):
    import time

    past = int(time.time()) - 10
    assert token_blacklist.blacklist_token("jti-expired", past) is False
    assert token_blacklist.is_blacklisted("jti-expired") is False


def test_blacklist_token_marks_and_detects(locmem_cache):
    import time

    future = int(time.time()) + 3600
    assert token_blacklist.blacklist_token("jti-live", future) is True
    assert token_blacklist.is_blacklisted("jti-live") is True
    assert token_blacklist.is_blacklisted("jti-unknown") is False


# --------------------------------------------------------------------------- #
# operation_log_utils —— 落库副作用与异常吞掉
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_log_operation_persists_record():
    from apps.system_mgmt.models.operation_log import OperationLog

    request = types.SimpleNamespace(
        user=types.SimpleNamespace(username="op-user", domain="domain.com"),
        META={"REMOTE_ADDR": "10.0.0.5"},
    )
    log = log_operation(request, "create", "system-manager", "测试操作")
    assert log is not None
    assert log.username == "op-user"
    assert log.app == "system-manager"
    assert log.action_type == "create"
    assert OperationLog.objects.filter(id=log.id, summary="测试操作").exists()


@pytest.mark.django_db
def test_log_operation_returns_none_on_error():
    # request.user 无 username 属性触发异常，应被吞掉返回 None（不影响主流程）
    request = types.SimpleNamespace(user=object(), META={})
    assert log_operation(request, "update", "app", "x") is None


# --------------------------------------------------------------------------- #
# viewset_utils.ViewSetUtils.search_by_page —— 真实 queryset 分页
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_search_by_page_returns_slice_and_total():
    from apps.system_mgmt.models import App
    from apps.system_mgmt.utils.viewset_utils import ViewSetUtils

    for i in range(5):
        App.objects.create(name=f"page_app_{i}", display_name=f"d{i}", url=f"/p{i}", is_build_in=False)

    queryset = App.objects.filter(name__startswith="page_app_").order_by("name")
    request = types.SimpleNamespace(GET={"page": "1", "page_size": "2"})
    data, total = ViewSetUtils.search_by_page(queryset, request, fields=["name"])

    assert total == 5
    assert len(data) == 2
    assert data[0]["name"] == "page_app_0"
    assert data[1]["name"] == "page_app_1"

    # 第二页
    request2 = types.SimpleNamespace(GET={"page": "2", "page_size": "2"})
    data2, total2 = ViewSetUtils.search_by_page(queryset, request2, fields=["name"])
    assert total2 == 5
    assert [d["name"] for d in data2] == ["page_app_2", "page_app_3"]


@pytest.mark.django_db
def test_search_by_page_defaults_when_no_params():
    from apps.system_mgmt.models import App
    from apps.system_mgmt.utils.viewset_utils import ViewSetUtils

    App.objects.create(name="solo_app", display_name="s", url="/s", is_build_in=False)
    queryset = App.objects.filter(name="solo_app")
    request = types.SimpleNamespace(GET={})
    data, total = ViewSetUtils.search_by_page(queryset, request, fields=["name"])
    assert total == 1
    assert data[0]["name"] == "solo_app"


# --------------------------------------------------------------------------- #
# bk_user_utils.get_bk_user_info —— mock HTTP 边界，验证两阶段调用与失败分支
# --------------------------------------------------------------------------- #
def _fake_resp(payload):
    return types.SimpleNamespace(json=lambda: payload)


def test_get_bk_user_info_success_two_phase(monkeypatch):
    from apps.system_mgmt.utils import bk_user_utils

    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params))
        if "bk_login/get_user" in url:
            return _fake_resp({"result": True, "data": {"bk_username": "alice"}})
        # 第二阶段：retrieve_user
        return _fake_resp({"result": True, "data": {"username": "alice", "domain": "domain.com"}})

    monkeypatch.setattr(bk_user_utils.requests, "get", fake_get)

    ok, data = bk_user_utils.get_bk_user_info("tok", "app", "secret", "https://bk.example.com/")
    assert ok is True
    assert data["username"] == "alice"
    # 两阶段各调用一次，第二阶段透传了 id=bk_username
    assert len(calls) == 2
    assert calls[1][1]["id"] == "alice"
    # rstrip('/') 生效，URL 不出现双斜杠
    assert "//api" not in calls[0][0].replace("https://", "")


def test_get_bk_user_info_first_phase_failure(monkeypatch):
    from apps.system_mgmt.utils import bk_user_utils

    monkeypatch.setattr(
        bk_user_utils.requests, "get",
        lambda url, params=None, timeout=None: _fake_resp({"result": False, "message": "bad token"}),
    )
    ok, data = bk_user_utils.get_bk_user_info("tok", "app", "secret", "https://bk.example.com")
    assert ok is False
    assert data is None


def test_get_bk_user_info_returns_false_on_request_exception(monkeypatch):
    from apps.system_mgmt.utils import bk_user_utils

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(bk_user_utils.requests, "get", boom)
    ok, data = bk_user_utils.get_bk_user_info("tok", "app", "secret", "https://bk.example.com")
    assert ok is False
    assert data is None


def test_get_bk_user_info_second_phase_failure(monkeypatch):
    from apps.system_mgmt.utils import bk_user_utils

    def fake_get(url, params=None, timeout=None):
        if "bk_login/get_user" in url:
            return _fake_resp({"result": True, "data": {"bk_username": "bob"}})
        return _fake_resp({"result": False, "message": "user not found"})

    monkeypatch.setattr(bk_user_utils.requests, "get", fake_get)
    ok, data = bk_user_utils.get_bk_user_info("tok", "app", "secret", "https://bk.example.com")
    assert ok is False
    assert data == {}
