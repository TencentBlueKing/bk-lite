"""rpc.system_mgmt.SystemMgmt 转发契约补充测试。

规格：每个方法把固定的 method_name 与参数原样转发给底层传输（self.client.run）。
替换传输 seam（self.client）为记录器，断言方法名 + 参数（位置/具名）契约。
能抓到方法名拼写、参数名/顺序回归。不触达真实 NATS。
"""
import pydantic.root_model  # noqa

import pytest

from apps.rpc.system_mgmt import SystemMgmt

pytestmark = pytest.mark.unit


class _Recorder:
    def __init__(self):
        self.calls = []

    def run(self, method_name, *args, **kwargs):
        self.calls.append((method_name, args, kwargs))
        return {"result": True, "data": {"sentinel": method_name}}


@pytest.fixture
def client():
    c = SystemMgmt()
    c.client = _Recorder()
    return c


def _last(client):
    return client.client.calls[-1]


def test_bk_lite_user_login_转发具名参数(client):
    out = client.bk_lite_user_login("alice", "domain.com")
    assert out["data"]["sentinel"] == "bk_lite_user_login"
    assert _last(client) == ("bk_lite_user_login", (), {"username": "alice", "domain": "domain.com"})


def test_create_default_rule_转发四模型参数(client):
    client.create_default_rule("llm", "ocr", "embed", "rerank")
    assert _last(client) == (
        "create_default_rule",
        (),
        {"llm_model": "llm", "ocr_model": "ocr", "embed_model": "embed", "rerank_model": "rerank"},
    )


def test_create_guest_role_无参转发(client):
    client.create_guest_role()
    assert _last(client) == ("create_guest_role", (), {})


def test_delete_opspilot_nats_channels_转发bot_id(client):
    client.delete_opspilot_nats_channels(bot_id=7)
    assert _last(client) == ("delete_opspilot_nats_channels", (), {"bot_id": 7})


def test_delete_rules_位置参数顺序与默认child_module(client):
    client.delete_rules([1, 2], "inst", "monitor", "mod")
    assert _last(client) == ("delete_rules", ([1, 2], "inst", "monitor", "mod", ""), {})


def test_generate_qr_code_by_user_id_转发(client):
    client.generate_qr_code_by_user_id(42)
    assert _last(client) == ("generate_qr_code_by_user_id", (), {"user_id": 42})


def test_get_all_groups_无参(client):
    client.get_all_groups()
    assert _last(client) == ("get_all_groups", (), {})


def test_get_all_users_无参(client):
    client.get_all_users()
    assert _last(client) == ("get_all_users", (), {})


def test_get_authorized_groups_scoped_默认include_children为False(client):
    ctx = {"user": "alice"}
    client.get_authorized_groups_scoped(ctx)
    assert _last(client) == (
        "get_authorized_groups_scoped",
        (),
        {"actor_context": ctx, "include_children": False},
    )


def test_get_client_转发默认domain(client):
    client.get_client("cid")
    assert _last(client) == ("get_client", (), {"client_id": "cid", "username": "", "domain": "domain.com"})


def test_get_group_id_转发(client):
    client.get_group_id("OpsPilotGuest")
    assert _last(client) == ("get_group_id", (), {"group_name": "OpsPilotGuest"})


def test_get_group_users_默认include_children(client):
    client.get_group_users(5)
    assert _last(client) == ("get_group_users", (), {"group": 5, "include_children": False})


def test_get_group_users_scoped_转发(client):
    ctx = {"user": "bob"}
    client.get_group_users_scoped(ctx, group=3, include_children=True)
    assert _last(client) == (
        "get_group_users_scoped",
        (),
        {"actor_context": ctx, "group": 3, "include_children": True},
    )


def test_get_login_module_domain_list_无参(client):
    client.get_login_module_domain_list()
    assert _last(client) == ("get_login_module_domain_list", (), {})


def test_get_namespace_by_domain_转发(client):
    client.get_namespace_by_domain("example.com")
    assert _last(client) == ("get_namespace_by_domain", (), {"domain": "example.com"})


def test_get_pilot_permission_by_token_位置参数(client):
    client.get_pilot_permission_by_token("tok", 9, [1, 2])
    assert _last(client) == ("get_pilot_permission_by_token", ("tok", 9, [1, 2]), {})


def test_get_user_rules_转发(client):
    client.get_user_rules(1, "alice")
    assert _last(client) == ("get_user_rules", (), {"group_id": 1, "username": "alice"})


def test_get_user_rules_by_app_位置参数顺序(client):
    # 注意：方法签名是 (group_id, username, app, module, child_module, domain, include_children)
    # 但转发顺序是 (group_id, username, domain, app, module, child_module, include_children)
    client.get_user_rules_by_app(1, "alice", "monitor", "mod", child_module="cm", domain="d.com", include_children=True)
    assert _last(client) == (
        "get_user_rules_by_app",
        (1, "alice", "d.com", "monitor", "mod", "cm", True),
        {},
    )


def test_get_user_rules_by_module_位置参数顺序(client):
    client.get_user_rules_by_module(2, "bob", "log", "m2")
    assert _last(client) == (
        "get_user_rules_by_module",
        (2, "bob", "domain.com", "log", "m2", False),
        {},
    )


def test_get_wechat_settings_无参(client):
    client.get_wechat_settings()
    assert _last(client) == ("get_wechat_settings", (), {})


def test_init_user_default_attributes_转发(client):
    client.init_user_default_attributes(99, "DevTeam", 1)
    assert _last(client) == (
        "init_user_default_attributes",
        (),
        {"user_id": 99, "group_name": "DevTeam", "default_group_id": 1},
    )


def test_revoke_token_转发(client):
    client.revoke_token("tk")
    assert _last(client) == ("revoke_token", (), {"token": "tk"})


def test_save_error_log_默认domain(client):
    client.save_error_log("alice", "monitor", "mod", "boom")
    assert _last(client) == (
        "save_error_log",
        (),
        {"username": "alice", "app": "monitor", "module": "mod", "error_message": "boom", "domain": "domain.com"},
    )


def test_save_operation_log_默认detail为None(client):
    client.save_operation_log("alice", "1.2.3.4", "cmdb", "create")
    assert _last(client) == (
        "save_operation_log",
        (),
        {
            "username": "alice", "source_ip": "1.2.3.4", "app": "cmdb", "action_type": "create",
            "summary": "", "domain": "domain.com", "target_type": "", "target_id": "", "detail": None,
        },
    )


def test_search_channel_list_转发(client):
    client.search_channel_list("email", [1, 2], True)
    assert _last(client) == (
        "search_channel_list",
        (),
        {"channel_type": "email", "teams": [1, 2], "include_children": True},
    )


def test_search_channel_list_scoped_默认值(client):
    ctx = {"user": "a"}
    client.search_channel_list_scoped(ctx)
    assert _last(client) == (
        "search_channel_list_scoped",
        (),
        {"actor_context": ctx, "channel_type": "", "teams": None, "include_children": False},
    )


def test_search_groups_转发query_params(client):
    client.search_groups({"search": "x"})
    assert _last(client) == ("search_groups", (), {"query_params": {"search": "x"}})


def test_search_opspilot_nats_channels_默认值(client):
    client.search_opspilot_nats_channels()
    assert _last(client) == (
        "search_opspilot_nats_channels",
        (),
        {"teams": None, "bot_id": None, "include_children": False},
    )


def test_search_users_转发(client):
    client.search_users({"page": 1, "page_size": 10})
    assert _last(client) == ("search_users", (), {"query_params": {"page": 1, "page_size": 10}})


def test_send_email_to_receiver_转发(client):
    client.send_email_to_receiver("标题", "正文", "a@b.com")
    assert _last(client) == (
        "send_email_to_receiver",
        (),
        {"title": "标题", "content": "正文", "receiver": "a@b.com"},
    )


def test_send_msg_with_channel_默认attachments为None(client):
    client.send_msg_with_channel(1, "t", "c", [1, 2])
    assert _last(client) == (
        "send_msg_with_channel",
        (),
        {"channel_id": 1, "title": "t", "content": "c", "receivers": [1, 2], "attachments": None},
    )


def test_sync_opspilot_nats_channels_默认timeout(client):
    nodes = [{"node_id": "n1", "name": "节点"}]
    client.sync_opspilot_nats_channels(7, "bot", [1], nodes)
    assert _last(client) == (
        "sync_opspilot_nats_channels",
        (),
        {"bot_id": 7, "bot_name": "bot", "team": [1], "nodes": nodes, "timeout": 60},
    )


def test_verify_bk_token_转发(client):
    client.verify_bk_token("bktok")
    assert _last(client) == ("verify_bk_token", (), {"bk_token": "bktok"})


def test_verify_otp_code_默认client_ip(client):
    client.verify_otp_code("alice", "123456")
    assert _last(client) == ("verify_otp_code", (), {"username": "alice", "otp_code": "123456", "client_ip": ""})


def test_verify_otp_code_by_user_id_转发(client):
    client.verify_otp_code_by_user_id(42, "654321")
    assert _last(client) == ("verify_otp_code_by_user_id", (), {"user_id": 42, "otp_code": "654321"})


def test_wechat_user_register_转发(client):
    client.wechat_user_register(5, "昵称")
    assert _last(client) == ("wechat_user_register", (), {"user_id": 5, "nick_name": "昵称"})


def test_appclient_path_指向nats_api():
    """构造时绑定的 AppClient 路径必须是 system_mgmt.nats_api。"""
    c = SystemMgmt()
    assert c.client.path == "apps.system_mgmt.nats_api"
