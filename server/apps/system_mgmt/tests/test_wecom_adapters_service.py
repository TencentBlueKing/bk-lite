from unittest.mock import MagicMock, patch

import pytest

from apps.system_mgmt.providers.adapters.wecom import (
    WeComIMNotificationAdapter,
    WeComLoginAuthAdapter,
    WeComUserSyncAdapter,
)

CONFIG = {
    "corp_id": "ww",
    "corp_secret": "secret",
    "agent_id": "100",
    "access_token_url": "https://wecom.internal/cgi-bin/gettoken",
    "user_sync_departments_url": "https://wecom.internal/cgi-bin/department/list",
    "user_sync_users_url": "https://wecom.internal/cgi-bin/user/list",
    "im_notification_users_url": "https://wecom.internal/cgi-bin/user/list",
    "im_notification_send_message_url": "https://wecom.internal/cgi-bin/message/send",
}


def response(payload):
    item = MagicMock()
    item.status_code = 200
    item.json.return_value = payload
    return item


def test_user_sync_returns_normalized_departments_and_users():
    source = MagicMock()
    source.business_config = {"root_department_id": "1"}
    source.name = "wecom"
    side_effects = [
        response({"errcode": 0, "access_token": "token"}),
        response({"errcode": 0, "department": [{"id": 1, "parentid": 0, "name": "Root"}]}),
        response({"errcode": 0, "userlist": [{"userid": "alice", "name": "Alice", "department": [1]}]}),
    ]
    with patch("apps.system_mgmt.providers.adapters.wecom.requests.get", side_effect=side_effects):
        result = WeComUserSyncAdapter.sync_users(CONFIG, "wecom", "user_sync", source=source)
    assert result.success is True
    assert result.payload["user_list"][0]["userid"] == "alice"


def test_user_sync_deduplicates_users_and_keeps_all_departments():
    source = MagicMock()
    source.business_config = {"root_department_id": "1"}
    source.name = "wecom"
    responses = [
        response({"errcode": 0, "access_token": "token"}),
        response({"errcode": 0, "department": [{"id": 1, "parentid": 0, "name": "Root"}]}),
        response({"errcode": 0, "userlist": [
            {"userid": "alice", "name": "Alice", "department": [1]},
            {"userid": "alice", "name": "Alice", "department": [2]},
        ]}),
    ]
    with patch("apps.system_mgmt.providers.adapters.wecom.requests.get", side_effect=responses):
        result = WeComUserSyncAdapter.sync_users(CONFIG, "wecom", "user_sync", source=source)

    assert result.success is True
    expected = [{
        "userid": "alice",
        "name": "Alice",
        "email": "",
        "mobile": "",
        "department_ids": ["1", "2"],
    }]
    assert result.payload["user_list"] == expected


def test_user_sync_passes_saved_real_department_id_unchanged():
    source = MagicMock()
    source.business_config = {"root_department_id": "42"}
    source.name = "wecom"
    with patch("apps.system_mgmt.providers.adapters.wecom.requests.get", side_effect=[
        response({"errcode": 0, "access_token": "token"}),
        response({"errcode": 0, "department": []}),
        response({"errcode": 0, "userlist": []}),
    ]) as get:
        result = WeComUserSyncAdapter.sync_users(CONFIG, "wecom", "user_sync", source=source)

    assert result.success is True
    department_request = get.call_args_list[1]
    user_request = get.call_args_list[2]
    assert department_request.kwargs["params"]["id"] == "42"
    assert user_request.kwargs["params"]["department_id"] == "42"


@pytest.mark.parametrize("root_department_id", ["", "0", "__all__", "**all**"])
def test_user_sync_rejects_virtual_or_enterprise_root_department_id_before_requests(root_department_id):
    source = MagicMock()
    source.business_config = {"root_department_id": root_department_id}
    source.name = "wecom"

    with patch("apps.system_mgmt.providers.adapters.wecom.requests.get") as get:
        result = WeComUserSyncAdapter.sync_users(CONFIG, "wecom", "user_sync", source=source)

    assert result.success is False
    assert result.errors[0].code == "provider.invalid_config"
    assert result.errors[0].field == "root_department_id"
    get.assert_not_called()


def test_list_departments_returns_real_department_forest_without_virtual_root():
    with patch("apps.system_mgmt.providers.adapters.wecom.requests.get", side_effect=[
        response({"errcode": 0, "access_token": "token"}),
        response({"errcode": 0, "department": [
            {"id": 1, "parentid": 0, "name": "Root"},
            {"id": 2, "parentid": 1, "name": "Child"},
        ]}),
    ]):
        result = WeComUserSyncAdapter.list_departments(
            CONFIG,
            "wecom",
            "user_sync",
            business_config={"root_department_id": "1"},
        )

    assert result.success is True
    assert result.payload["items"][0]["id"] == "1"
    assert result.payload["items"][0]["parent_id"] is None
    assert result.payload["items"][0].get("is_all") is None
    assert set(result.payload) == {"items"}


def test_list_departments_does_not_calculate_current_selection_state():
    with patch("apps.system_mgmt.providers.adapters.wecom.requests.get", side_effect=[
        response({"errcode": 0, "access_token": "token"}),
        response({"errcode": 0, "department": [{"id": 1, "parentid": 0, "name": "Root"}]}),
    ]):
        result = WeComUserSyncAdapter.list_departments(
            CONFIG,
            "wecom",
            "user_sync",
            business_config={"root_department_id": "999"},
        )

    assert result.success is True
    assert set(result.payload) == {"items"}


def test_im_send_posts_text_message_to_each_userid():
    get_patch = patch(
        "apps.system_mgmt.providers.adapters.wecom.requests.get",
        return_value=response({"errcode": 0, "access_token": "token"}),
    )
    post_patch = patch(
        "apps.system_mgmt.providers.adapters.wecom.requests.post",
        return_value=response({"errcode": 0}),
    )
    with get_patch, post_patch as post:
        result = WeComIMNotificationAdapter.send_message(
            CONFIG,
            "wecom",
            "im_notification",
            receive_ids=["alice"],
            title="T",
            content="C",
        )
    assert result.success is True
    assert post.call_args.args[0] == "https://wecom.internal/cgi-bin/message/send"


def test_im_send_reports_partial_failures_without_falling_back_to_other_identifiers():
    get_patch = patch(
        "apps.system_mgmt.providers.adapters.wecom.requests.get",
        return_value=response({"errcode": 0, "access_token": "token"}),
    )
    post_patch = patch(
        "apps.system_mgmt.providers.adapters.wecom.requests.post",
        side_effect=[response({"errcode": 0}), response({"errcode": 81013, "errmsg": "invalid userid"})],
    )
    with get_patch, post_patch:
        result = WeComIMNotificationAdapter.send_message(
            CONFIG,
            "wecom",
            "im_notification",
            receive_ids=["alice", "missing"],
            title="T",
            content="C",
        )

    assert result.success is True
    assert result.partial_success is True
    assert result.payload == {
        "sent_count": 1,
        "failures": [{"receive_id": "missing", "message": "invalid userid"}],
    }


def test_user_sync_collects_all_pages_of_members_via_cursor():
    source = MagicMock()
    source.business_config = {"root_department_id": "1"}
    source.name = "wecom"
    responses = [
        response({"errcode": 0, "access_token": "token"}),
        response({"errcode": 0, "department": [{"id": 1, "parentid": 0, "name": "Root"}]}),
        response({"errcode": 0, "userlist": [{"userid": "alice", "name": "Alice"}], "next_cursor": "next"}),
        response({"errcode": 0, "userlist": [{"userid": "bob", "name": "Bob"}], "next_cursor": ""}),
    ]
    with patch("apps.system_mgmt.providers.adapters.wecom.requests.get", side_effect=responses) as get:
        result = WeComUserSyncAdapter.sync_users(CONFIG, "wecom", "user_sync", source=source)

    assert result.success is True
    assert sorted(user["userid"] for user in result.payload["user_list"]) == ["alice", "bob"]
    user_call_args = [call.args[0] for call in get.call_args_list[2:]]
    assert all(url.endswith("/cgi-bin/user/list") for url in user_call_args)
    cursor_params = [call.kwargs["params"].get("cursor", "") for call in get.call_args_list[2:]]
    assert cursor_params == ["", "next"]


def test_im_notification_collects_all_pages_of_users_via_cursor():
    with patch("apps.system_mgmt.providers.adapters.wecom.requests.get", side_effect=[
        response({"errcode": 0, "access_token": "token"}),
        response({"errcode": 0, "userlist": [{"userid": "alice"}], "next_cursor": "next"}),
        response({"errcode": 0, "userlist": [{"userid": "bob"}], "next_cursor": ""}),
    ]):
        result = WeComIMNotificationAdapter.list_external_users(CONFIG, "wecom", "im_notification")

    assert result.success is True
    assert sorted(user["userid"] for user in result.payload["external_users"]) == ["alice", "bob"]


def test_user_sync_default_fetch_child_is_one():
    source = MagicMock()
    source.business_config = {"root_department_id": "1"}
    source.name = "wecom"
    with patch("apps.system_mgmt.providers.adapters.wecom.requests.get", side_effect=[
        response({"errcode": 0, "access_token": "token"}),
        response({"errcode": 0, "department": [{"id": 1, "parentid": 0, "name": "Root"}]}),
        response({"errcode": 0, "userlist": []}),
    ]) as get:
        WeComUserSyncAdapter.sync_users(CONFIG, "wecom", "user_sync", source=source)
    assert get.call_args_list[2].kwargs["params"]["fetch_child"] == 1


def test_user_sync_respects_include_child_departments_false():
    source = MagicMock()
    source.business_config = {"root_department_id": "1", "include_child_departments": False}
    source.name = "wecom"
    with patch("apps.system_mgmt.providers.adapters.wecom.requests.get", side_effect=[
        response({"errcode": 0, "access_token": "token"}),
        response({"errcode": 0, "department": [{"id": 1, "parentid": 0, "name": "Root"}]}),
        response({"errcode": 0, "userlist": []}),
    ]) as get:
        WeComUserSyncAdapter.sync_users(CONFIG, "wecom", "user_sync", source=source)
    assert get.call_args_list[2].kwargs["params"]["fetch_child"] == 0


def test_user_sync_drops_child_departments_when_recursion_disabled():
    source = MagicMock()
    source.business_config = {"root_department_id": "1", "include_child_departments": False}
    source.name = "wecom"
    with patch("apps.system_mgmt.providers.adapters.wecom.requests.get", side_effect=[
        response({"errcode": 0, "access_token": "token"}),
        response({"errcode": 0, "department": [
            {"id": 1, "parentid": 0, "name": "Root"},
            {"id": 2, "parentid": 1, "name": "Child"},
        ]}),
        response({"errcode": 0, "userlist": []}),
    ]):
        result = WeComUserSyncAdapter.sync_users(CONFIG, "wecom", "user_sync", source=source)

    assert result.success is True
    assert [item["id"] for item in result.payload["group_list"]] == ["1"]


def test_user_sync_keeps_child_departments_when_recursion_enabled():
    source = MagicMock()
    source.business_config = {"root_department_id": "1", "include_child_departments": True}
    source.name = "wecom"
    with patch("apps.system_mgmt.providers.adapters.wecom.requests.get", side_effect=[
        response({"errcode": 0, "access_token": "token"}),
        response({"errcode": 0, "department": [
            {"id": 1, "parentid": 0, "name": "Root"},
            {"id": 2, "parentid": 1, "name": "Child"},
        ]}),
        response({"errcode": 0, "userlist": []}),
    ]):
        result = WeComUserSyncAdapter.sync_users(CONFIG, "wecom", "user_sync", source=source)

    assert result.success is True
    assert [item["id"] for item in result.payload["group_list"]] == ["1", "2"]


def test_user_sync_caps_pagination_when_next_cursor_repeats():
    source = MagicMock()
    source.business_config = {"root_department_id": "1"}
    source.name = "wecom"
    responses = [
        response({"errcode": 0, "access_token": "token"}),
        response({"errcode": 0, "department": [{"id": 1, "parentid": 0, "name": "Root"}]}),
        response({"errcode": 0, "userlist": [{"userid": "alice"}], "next_cursor": "loop"}),
        response({"errcode": 0, "userlist": [{"userid": "alice"}], "next_cursor": "loop"}),
        response({"errcode": 0, "userlist": [{"userid": "alice"}], "next_cursor": "loop"}),
    ]
    with patch("apps.system_mgmt.providers.adapters.wecom.requests.get", side_effect=responses) as get:
        result = WeComUserSyncAdapter.sync_users(CONFIG, "wecom", "user_sync", source=source)

    assert result.success is False
    assert result.errors[0].code == "provider.invalid_response"
    assert result.errors[0].field == "next_cursor"
    user_list_calls = [call for call in get.call_args_list[2:] if "/cgi-bin/user/list" in call.args[0]]
    assert len(user_list_calls) <= 5


def test_im_notification_caps_pagination_when_next_cursor_repeats():
    with patch("apps.system_mgmt.providers.adapters.wecom.requests.get", side_effect=[
        response({"errcode": 0, "access_token": "token"}),
        response({"errcode": 0, "userlist": [{"userid": "alice"}], "next_cursor": "loop"}),
        response({"errcode": 0, "userlist": [{"userid": "alice"}], "next_cursor": "loop"}),
    ]) as get:
        result = WeComIMNotificationAdapter.list_external_users(CONFIG, "wecom", "im_notification")

    assert result.success is False
    assert result.errors[0].code == "provider.invalid_response"
    assert len(get.call_args_list) <= 4


def test_user_sync_handles_non_object_json_response():
    source = MagicMock()
    source.business_config = {"root_department_id": "1"}
    source.name = "wecom"
    array_response = MagicMock()
    array_response.status_code = 200
    array_response.json.return_value = ["not", "a", "dict"]

    with patch("apps.system_mgmt.providers.adapters.wecom.requests.get", side_effect=[
        response({"errcode": 0, "access_token": "token"}),
        array_response,
    ]):
        result = WeComUserSyncAdapter.sync_users(CONFIG, "wecom", "user_sync", source=source)

    assert result.success is False
    assert result.errors[0].code == "provider.invalid_response"


def test_user_sync_uses_private_endpoint_overrides():
    config = {
        **CONFIG,
        "access_token_url": "https://internal.example/cgi-bin/gettoken",
        "user_sync_departments_url": "https://internal.example/cgi-bin/department/list",
        "user_sync_users_url": "https://internal.example/cgi-bin/user/list",
    }
    source = MagicMock()
    source.business_config = {"root_department_id": "1"}
    source.name = "wecom"
    responses = [
        response({"errcode": 0, "access_token": "token"}),
        response({"errcode": 0, "department": [{"id": 1, "parentid": 0, "name": "Root"}]}),
        response({"errcode": 0, "userlist": [{"userid": "alice"}]}),
    ]
    with patch("apps.system_mgmt.providers.adapters.wecom.requests.get", side_effect=responses) as get:
        WeComUserSyncAdapter.sync_users(config, "wecom", "user_sync", source=source)

    called_urls = [call.args[0] for call in get.call_args_list]
    assert "https://internal.example/cgi-bin/gettoken" in called_urls
    assert "https://internal.example/cgi-bin/department/list" in called_urls
    assert "https://internal.example/cgi-bin/user/list" in called_urls
    assert not any(url.startswith("https://wecom.internal") for url in called_urls)


def test_im_notification_users_endpoint_override_is_honored():
    config = {
        **CONFIG,
        "access_token_url": "https://internal.example/cgi-bin/gettoken",
        "im_notification_users_url": "https://internal.example/cgi-bin/user/list",
        "im_notification_send_message_url": "https://internal.example/cgi-bin/message/send",
    }
    with patch("apps.system_mgmt.providers.adapters.wecom.requests.get", side_effect=[
        response({"errcode": 0, "access_token": "token"}),
        response({"errcode": 0, "userlist": [{"userid": "alice"}]}),
    ]) as get:
        result = WeComIMNotificationAdapter.list_external_users(
            config, "wecom", "im_notification"
        )

    assert result.success is True
    called_urls = [call.args[0] for call in get.call_args_list]
    assert "https://internal.example/cgi-bin/user/list" in called_urls
    assert not any(url.startswith("https://wecom.internal/cgi-bin/user/list") for url in called_urls)


def test_im_notification_uses_private_endpoint_overrides():
    config = {
        **CONFIG,
        "access_token_url": "https://internal.example/cgi-bin/gettoken",
        "im_notification_users_url": "https://internal.example/cgi-bin/user/list",
        "im_notification_send_message_url": "https://internal.example/cgi-bin/message/send",
    }
    get_patch = patch(
        "apps.system_mgmt.providers.adapters.wecom.requests.get",
        side_effect=[response({"errcode": 0, "access_token": "token"})],
    )
    post_patch = patch(
        "apps.system_mgmt.providers.adapters.wecom.requests.post",
        return_value=response({"errcode": 0}),
    )
    with get_patch, post_patch as post:
        WeComIMNotificationAdapter.send_message(
            config,
            "wecom",
            "im_notification",
            receive_ids=["alice"],
            title="T",
            content="C",
        )

    post_called_urls = [call.args[0] for call in post.call_args_list]
    assert post_called_urls == ["https://internal.example/cgi-bin/message/send"]


def test_im_send_rejects_non_http_endpoint_override():
    config = {**CONFIG, "im_notification_send_message_url": "ftp://wecom.internal/message/send"}

    result = WeComIMNotificationAdapter.send_message(
        config,
        "wecom",
        "im_notification",
        receive_ids=["alice"],
        title="T",
        content="C",
    )

    assert result.success is False
    assert result.errors[0].code == "provider.invalid_config"
    assert result.errors[0].field == "im_notification_send_message_url"


def test_proxy_url_invalid_scheme_rejects_with_provider_invalid_config():
    config = {**CONFIG, "proxy_url": "socks5h://127.0.0.1:1080"}

    result = WeComIMNotificationAdapter.send_message(
        config,
        "wecom",
        "im_notification",
        receive_ids=["alice"],
        title="T",
        content="C",
    )

    assert result.success is False
    assert result.errors[0].code == "provider.invalid_config"
    assert result.errors[0].field == "proxy_url"


def test_proxy_url_passes_requests_proxies_to_all_server_side_requests():
    config = {
        **CONFIG,
        "proxy_url": "http://127.0.0.1:8080",
    }
    get_responses = [
        response({"errcode": 0, "access_token": "token"}),  # sync_users token
        response({"errcode": 0, "department": [{"id": 1, "parentid": 0, "name": "Root"}]}),
        response({"errcode": 0, "userlist": [{"userid": "alice"}]}),
    ]
    with patch(
        "apps.system_mgmt.providers.adapters.wecom.requests.get",
        side_effect=get_responses,
    ) as get, patch(
        "apps.system_mgmt.providers.adapters.wecom.requests.post",
        return_value=response({"errcode": 0}),
    ) as post:
        WeComUserSyncAdapter.sync_users(
            config,
            "wecom",
            "user_sync",
            source=MagicMock(business_config={"root_department_id": "1"}, name="wecom"),
        )

    for call in list(get.call_args_list) + list(post.call_args_list):
        assert call.kwargs.get("proxies") == {
            "http": "http://127.0.0.1:8080",
            "https": "http://127.0.0.1:8080",
        }, call.kwargs


def test_proxy_url_passes_requests_proxies_to_im_notification_endpoints():
    config = {
        **CONFIG,
        "proxy_url": "http://127.0.0.1:8080",
    }
    get_responses = [
        response({"errcode": 0, "access_token": "token"}),  # list_external_users token
        response({"errcode": 0, "userlist": [{"userid": "bob"}], "next_cursor": ""}),
        response({"errcode": 0, "access_token": "token"}),  # send_message token
    ]
    with patch(
        "apps.system_mgmt.providers.adapters.wecom.requests.get",
        side_effect=get_responses,
    ) as get, patch(
        "apps.system_mgmt.providers.adapters.wecom.requests.post",
        return_value=response({"errcode": 0}),
    ) as post:
        WeComIMNotificationAdapter.list_external_users(config, "wecom", "im_notification")
        WeComIMNotificationAdapter.send_message(
            config,
            "wecom",
            "im_notification",
            receive_ids=["alice"],
            title="T",
            content="C",
        )

    for call in list(get.call_args_list) + list(post.call_args_list):
        assert call.kwargs.get("proxies") == {
            "http": "http://127.0.0.1:8080",
            "https": "http://127.0.0.1:8080",
        }, call.kwargs


def test_proxy_url_is_omitted_when_unset():
    with patch(
        "apps.system_mgmt.providers.adapters.wecom.requests.get",
        return_value=response({"errcode": 0, "access_token": "token"}),
    ) as get, patch(
        "apps.system_mgmt.providers.adapters.wecom.requests.post",
        return_value=response({"errcode": 0}),
    ) as post:
        WeComIMNotificationAdapter.send_message(
            CONFIG,
            "wecom",
            "im_notification",
            receive_ids=["alice"],
            title="T",
            content="C",
        )

    for call in list(get.call_args_list) + list(post.call_args_list):
        assert "proxies" not in call.kwargs, call.kwargs


def test_build_login_url_does_not_emit_http_request():
    with patch(
        "apps.system_mgmt.providers.adapters.wecom.requests.get",
        side_effect=AssertionError("build_login_url must not perform HTTP requests"),
    ) as get, patch(
        "apps.system_mgmt.providers.adapters.wecom.requests.post",
        side_effect=AssertionError("build_login_url must not perform HTTP requests"),
    ) as post:
        WeComLoginAuthAdapter.build_login_url(
            CONFIG,
            "wecom",
            "login_auth",
            redirect_uri="https://bk/callback",
            state="signed",
        )

    assert get.call_count == 0
    assert post.call_count == 0


def test_user_sync_does_not_concatenate_base_url_with_path():
    config = {
        **CONFIG,
        "user_sync_departments_url": "https://dept.internal.example/v1/list",
        "user_sync_users_url": "https://users.internal.example/v1/list",
    }
    responses = [
        response({"errcode": 0, "access_token": "token"}),
        response({"errcode": 0, "department": [{"id": 1, "parentid": 0, "name": "Root"}]}),
        response({"errcode": 0, "userlist": []}),
    ]
    with patch(
        "apps.system_mgmt.providers.adapters.wecom.requests.get",
        side_effect=responses,
    ) as get:
        WeComUserSyncAdapter.sync_users(
            config,
            "wecom",
            "user_sync",
            source=MagicMock(business_config={"root_department_id": "1"}, name="wecom"),
        )

    department_call = next(call for call in get.call_args_list if "dept.internal" in call.args[0])
    user_call = next(call for call in get.call_args_list if "users.internal" in call.args[0])
    assert department_call.args[0] == "https://dept.internal.example/v1/list"
    assert user_call.args[0] == "https://users.internal.example/v1/list"
    # 私有化端点不应再使用官方 cgi-bin 路径拼接。
    business_urls = [
        call for call in get.call_args_list
        if "dept.internal" in call.args[0] or "users.internal" in call.args[0]
    ]
    for call in business_urls:
        assert "/cgi-bin/" not in call.args[0], call.args[0]


def test_user_sync_falls_back_to_official_urls_when_addresses_missing():
    config = {
        "corp_id": "ww",
        "corp_secret": "secret",
        "agent_id": "100",
    }
    responses = [
        response({"errcode": 0, "access_token": "token"}),
        response({"errcode": 0, "department": [{"id": 1, "parentid": 0, "name": "Root"}]}),
        response({"errcode": 0, "userlist": []}),
    ]
    with patch(
        "apps.system_mgmt.providers.adapters.wecom.requests.get",
        side_effect=responses,
    ) as get:
        result = WeComUserSyncAdapter.sync_users(
            config,
            "wecom",
            "user_sync",
            source=MagicMock(business_config={"root_department_id": "1"}, name="wecom"),
        )

    assert result.success is True
    assert [call.args[0] for call in get.call_args_list] == [
        "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
        "https://qyapi.weixin.qq.com/cgi-bin/department/list",
        "https://qyapi.weixin.qq.com/cgi-bin/user/list",
    ]


def test_im_notification_falls_back_to_official_urls_when_addresses_missing():
    config = {
        "corp_id": "ww",
        "corp_secret": "secret",
        "agent_id": "100",
    }
    get_responses = [
        response({"errcode": 0, "access_token": "token"}),
        response({"errcode": 0, "userlist": []}),
        response({"errcode": 0, "access_token": "token"}),
    ]
    post_response = response({"errcode": 0})
    with patch(
        "apps.system_mgmt.providers.adapters.wecom.requests.get",
        side_effect=get_responses,
    ) as get, patch(
        "apps.system_mgmt.providers.adapters.wecom.requests.post",
        return_value=post_response,
    ) as post:
        list_result = WeComIMNotificationAdapter.list_external_users(
            config, "wecom", "im_notification"
        )
        send_result = WeComIMNotificationAdapter.send_message(
            config,
            "wecom",
            "im_notification",
            receive_ids=["alice"],
            title="T",
            content="C",
        )

    assert list_result.success is True
    assert send_result.success is True
    assert [call.args[0] for call in get.call_args_list] == [
        "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
        "https://qyapi.weixin.qq.com/cgi-bin/user/list",
        "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
    ]
    assert [call.args[0] for call in post.call_args_list] == [
        "https://qyapi.weixin.qq.com/cgi-bin/message/send"
    ]
