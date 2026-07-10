"""Telegraf haproxy plugin 模板密码契约测试。

修复背景:`server/apps/monitor/support-files/plugins/Telegraf/middleware/haproxy/haproxy.child.toml.j2`
历史版本把 `${PASSWORD__<config_id>}` 字面占位符塞进 URL 的 userinfo 段,采集端 envsubst
还原真实密码后,含 `@ / # / % / 空格` 等特殊字符时 Go `net/url.Parse` 解析失败 → 401。

修复策略:把 username/password 拆出 URL,改用 telegraf 1.21+ `inputs.haproxy` 的独立字段,
密码完全脱离 URL 拼装,特殊字符天然可用。本测试覆盖该契约。
"""
import tomllib
from pathlib import Path
from urllib.parse import urlparse

import pytest

from apps.monitor.utils.plugin_controller import Controller

SERVER_ROOT = Path(__file__).resolve().parents[3]
HAPROXY_TEMPLATE = (
    SERVER_ROOT
    / "apps" / "monitor" / "support-files" / "plugins"
    / "Telegraf" / "middleware" / "haproxy" / "haproxy.child.toml.j2"
)


@pytest.fixture(scope="module")
def template_text():
    """读 j2 原文,断言测试与生产同步。"""
    return HAPROXY_TEMPLATE.read_text(encoding="utf-8")


@pytest.fixture
def ctrl():
    return Controller({})


def _render(ctrl, template_text, context):
    """渲染模板并把 toml 顶层第一个 [[inputs.haproxy]] 表取出,方便断言。"""
    rendered = ctrl.render_template(template_text, context)
    parsed = tomllib.loads(rendered)
    # `[[inputs.haproxy]]` 在 TOML 里是 array of tables,取首个元素
    return rendered, parsed["inputs"]["haproxy"][0]


def _base_context(**overrides):
    """生成一份合法的最小 context,unittest 测例按需覆盖。

    必须包含 j2 文件里所有被引用的变量(即使是空值),否则
    `validate_template_variables` 会把 {{ ENV_PASSWORD }} 等视为未授权。
    """
    ctx = {
        "url": "http://10.0.0.5:1024/haproxy?stats",
        "instance_id": "h1",
        "instance_type": "haproxy",
        "interval": "60",
        "username": "",
        "ENV_PASSWORD": "",
    }
    ctx.update(overrides)
    return ctx


@pytest.mark.unit
def test_template_uses_independent_username_password_fields(template_text):
    """回归:j2 文件必须把 username/password 拆到独立字段,不能再嵌进 URL。"""
    # 关键反例:不能出现「占位符嵌进 URL 的 userinfo」这种旧写法
    assert "${PASSWORD__" not in template_text.split("servers", 1)[1].split("]", 1)[0], (
        "${PASSWORD__<config_id>} 字面占位符不能再嵌进 servers URL 的 userinfo 段。"
        "应改用独立的 password = \"${PASSWORD__<config_id>}\" 字段。"
    )
    # 正向:独立字段必须存在
    assert 'username = "{{ username }}"' in template_text
    assert 'password = "${PASSWORD__{{ config_id }}}"' in template_text


@pytest.mark.unit
def test_no_credentials_emits_pure_url(ctrl, template_text):
    """case 1:无凭据场景 → servers 是纯 URL,不含 userinfo;无 username/password 字段。"""
    context = _base_context()  # username / ENV_PASSWORD 默认未提供
    rendered, cfg = _render(ctrl, template_text, context)

    # TOML 结构断言
    assert "servers" in cfg, f"渲染后缺 servers 字段:\n{rendered}"
    assert cfg["servers"] == ["http://10.0.0.5:1024/haproxy?stats"]

    # 关键契约:URL 不含 userinfo(没有 @ 没有 ://...)
    for server_url in cfg["servers"]:
        parsed = urlparse(server_url)
        assert parsed.scheme == "http"
        assert parsed.hostname == "10.0.0.5"
        assert parsed.port == 1024
        assert parsed.path == "/haproxy"
        assert parsed.query == "stats"
        assert parsed.username is None, f"URL 不应含 userinfo.username: {server_url}"
        assert parsed.password is None, f"URL 不应含 userinfo.password: {server_url}"

    # 无凭据场景不应出现 username / password 字段
    assert "username" not in cfg
    assert "password" not in cfg


@pytest.mark.unit
def test_with_credentials_emits_independent_fields(ctrl, template_text):
    """case 2:有凭据场景 → servers 是纯 URL;username/password 是独立字段;占位符字面留存。"""
    context = _base_context(
        username="statsuser",
        ENV_PASSWORD="p@ss:1%2#",
        config_id="ABC",
    )
    rendered, cfg = _render(ctrl, template_text, context)

    # servers 必须是纯 URL,userinfo 段被拆走
    assert cfg["servers"] == ["http://10.0.0.5:1024/haproxy?stats"]
    parsed = urlparse(cfg["servers"][0])
    assert parsed.username is None
    assert parsed.password is None

    # username 独立字段,值原样保留(包含可能的特殊字符,交给 telegraf SetBasicAuth)
    assert cfg["username"] == "statsuser"

    # password 必须以**字面**形式持有 ${PASSWORD__<config_id>}
    assert cfg["password"] == "${PASSWORD__ABC}"
    # 断言占位符没有被任何 filter 误编码成不可识别串
    assert "%24" not in cfg["password"]
    assert "%7B" not in cfg["password"]


@pytest.mark.unit
def test_password_placeholder_is_never_percent_encoded(ctrl, template_text):
    """case 3:反向契约 —— 任何密码占位符都不能被 percent-encode 改写。

    模拟 attempt 1 错版(`{{ '${PASSWORD__<config_id>}' | urlencode }}`),
    这里的密码字段若被错误 encode,采集端 envsubst 会拿不到占位符。
    """
    context = _base_context(
        username="u",
        ENV_PASSWORD="无关紧要,占位符才是重点",
        config_id="XYZ_123",
    )
    _, cfg = _render(ctrl, template_text, context)
    placeholder = cfg["password"]

    # 1. 字面占位符必须原样留存
    assert placeholder == "${PASSWORD__XYZ_123}"
    # 2. 反例特征不能出现:${} 被替换成 %24 %7B 之类
    for forbidden in ("%24%7BPASSWORD", "%24", "%7B%7D", "%7D"):
        assert forbidden not in placeholder, (
            f"password 字段含被错误 encode 的占位符片段 {forbidden!r} → 采集端 envsubst 会失效。"
            f"actual={placeholder!r}"
        )


@pytest.mark.unit
def test_username_with_special_chars_does_not_leak_into_url(ctrl, template_text):
    """case 4:username 含特殊字符(如 @)也不能塞回 URL。

    旧代码:即使 username 编码,某些字符组合仍可能让 URL parser 错位。
    新 schema:username 在独立字段里,telegraf SetBasicAuth 原样使用,无 URL 解析风险。
    """
    context = _base_context(
        username="user@org",
        ENV_PASSWORD="pw",
        config_id="SPEC",
    )
    rendered, cfg = _render(ctrl, template_text, context)

    # servers 仍必须是纯 URL
    assert cfg["servers"] == ["http://10.0.0.5:1024/haproxy?stats"]
    parsed = urlparse(cfg["servers"][0])
    assert parsed.username is None, (
        f"含 @ 的 username 不应污染 URL.userinfo: {cfg['servers'][0]}"
    )

    # username 字段保留 @,交给 telegraf haproxy.go 处理
    assert cfg["username"] == "user@org"
    assert cfg["password"] == "${PASSWORD__SPEC}"


@pytest.mark.unit
def test_unrelated_fields_intact(ctrl, template_text):
    """case 5:回归契约 —— 修复不能破坏 keep_field_names / interval / tags。"""
    context = _base_context(
        username="statsuser",
        ENV_PASSWORD="p@ss",
        config_id="REG1",
        interval="30",
    )
    _, cfg = _render(ctrl, template_text, context)

    # [[inputs.haproxy]] 顶层字段保留
    assert cfg["startup_error_behavior"] == "retry"
    assert cfg["keep_field_names"] is True
    assert cfg["interval"] == "30s"

    # tags 子表保留
    assert cfg["tags"]["instance_id"] == "h1"
    assert cfg["tags"]["instance_type"] == "haproxy"
    assert cfg["tags"]["collect_type"] == "middleware"
    assert cfg["tags"]["config_type"] == "haproxy"
