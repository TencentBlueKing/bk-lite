from unittest import mock

import pytest
from wechatpy.exceptions import WeChatClientException

from apps.system_mgmt.providers.builtin.wecom.adapters.im_group import WeComIMGroupAdapter
from apps.system_mgmt.providers.loader import load_builtin_providers
from apps.system_mgmt.providers.registry import get_provider_registry


CONFIG = {
    "corp_id": "ww-corp",
    "corp_secret": "secret",
    "agent_id": "1000002",
}


def test_wecom_create_group_uses_deterministic_chat_id_and_internal_userids():
    client = mock.Mock()
    client.appchat.get.side_effect = WeChatClientException(86003, "not found")
    client.appchat.create.return_value = {"chatid": "chat-returned"}

    with mock.patch(
        "apps.system_mgmt.providers.builtin.wecom.adapters.im_group.WeChatClient",
        return_value=client,
    ):
        result = WeComIMGroupAdapter.create_group(
            config=CONFIG,
            provider_key="wecom",
            capability_key="im_group",
            group_name="INC-1001",
            owner_id="alice",
            member_ids=["alice", "bob", "alice"],
            member_id_type="userid",
            idempotency_key="incident-binding-stable-key",
        )

    assert result.success
    assert result.payload["chat_id"] == "acb26d1c6f5ff8a6b26db99bcda826ce"
    client.appchat.create.assert_called_once_with(
        chat_id=result.payload["chat_id"],
        name="INC-1001",
        owner="alice",
        user_list=["alice", "bob"],
    )


def test_wecom_create_group_treats_86001_preflight_as_absent_for_real_failed_binding_key():
    client = mock.Mock()
    client.appchat.get.side_effect = WeChatClientException(86001, "invalid chatid")
    client.appchat.create.return_value = {"chatid": "created"}

    with mock.patch(
        "apps.system_mgmt.providers.builtin.wecom.adapters.im_group.WeChatClient",
        return_value=client,
    ):
        result = WeComIMGroupAdapter.create_group(
            config=CONFIG,
            provider_key="wecom",
            capability_key="im_group",
            group_name="INCIDENT-2",
            owner_id="alice",
            member_ids=["alice", "bob"],
            member_id_type="userid",
            idempotency_key="bklite-d1eb260b25ee420484292ac01f32b524",
        )

    assert result.success
    assert result.payload["chat_id"] == "8c9d9273107a506dd0046320f19550f7"
    client.appchat.create.assert_called_once_with(
        chat_id="8c9d9273107a506dd0046320f19550f7",
        name="INCIDENT-2",
        owner="alice",
        user_list=["alice", "bob"],
    )


def test_wecom_create_group_skips_invalid_candidates_and_creates_with_first_valid_pair():
    client = mock.Mock()
    client.appchat.get.side_effect = WeChatClientException(86003, "not found")
    client.appchat.create.side_effect = [
        WeChatClientException(86007, "invalid member"),
        {"chatid": "created"},
    ]

    with mock.patch(
        "apps.system_mgmt.providers.builtin.wecom.adapters.im_group.WeChatClient",
        return_value=client,
    ):
        result = WeComIMGroupAdapter.create_group(
            config=CONFIG,
            provider_key="wecom",
            capability_key="im_group",
            group_name="INC-1001",
            owner_id="alice",
            member_ids=["alice", "invalid-bob", "carol", "dave"],
            member_id_type="userid",
            idempotency_key="incident-binding-stable-key",
        )

    assert result.success
    assert result.partial_success
    assert result.payload["joined_member_ids"] == ["alice", "carol"]
    assert result.payload["invalid_member_ids"] == ["invalid-bob"]
    assert client.appchat.create.call_args_list == [
        mock.call(
            chat_id=result.payload["chat_id"],
            name="INC-1001",
            owner="alice",
            user_list=["alice", "invalid-bob"],
        ),
        mock.call(
            chat_id=result.payload["chat_id"],
            name="INC-1001",
            owner="alice",
            user_list=["alice", "carol"],
        ),
    ]


def test_wecom_create_group_does_not_hide_an_invalid_owner_as_member_partial_success():
    client = mock.Mock()
    client.appchat.get.side_effect = WeChatClientException(86003, "not found")
    client.appchat.create.side_effect = WeChatClientException(86005, "invalid owner")

    with mock.patch(
        "apps.system_mgmt.providers.builtin.wecom.adapters.im_group.WeChatClient",
        return_value=client,
    ):
        result = WeComIMGroupAdapter.create_group(
            config=CONFIG,
            provider_key="wecom",
            capability_key="im_group",
            group_name="INC-1001",
            owner_id="alice",
            member_ids=["alice", "bob", "carol"],
            member_id_type="userid",
            idempotency_key="incident-binding-stable-key",
        )

    assert not result.success
    assert result.errors[0].code == "provider.owner_invalid"
    assert client.appchat.create.call_count == 1


def test_wecom_create_group_bounds_invalid_candidate_probes():
    client = mock.Mock()
    client.appchat.get.side_effect = WeChatClientException(86003, "not found")
    client.appchat.create.side_effect = WeChatClientException(86007, "invalid member")

    with mock.patch(
        "apps.system_mgmt.providers.builtin.wecom.adapters.im_group.WeChatClient",
        return_value=client,
    ):
        result = WeComIMGroupAdapter.create_group(
            config=CONFIG,
            provider_key="wecom",
            capability_key="im_group",
            group_name="INC-1001",
            owner_id="alice",
            member_ids=["alice", *[f"invalid-{index}" for index in range(40)]],
            member_id_type="userid",
            idempotency_key="incident-binding-stable-key",
        )

    assert not result.success
    assert result.errors[0].code == "provider.member_invalid"
    assert client.appchat.create.call_count == 20


def test_wecom_create_group_reuses_existing_deterministic_group_before_create():
    client = mock.Mock()
    client.appchat.get.return_value = {"chat_info": {"chatid": "existing"}}

    with mock.patch(
        "apps.system_mgmt.providers.builtin.wecom.adapters.im_group.WeChatClient",
        return_value=client,
    ):
        result = WeComIMGroupAdapter.create_group(
            config=CONFIG,
            provider_key="wecom",
            capability_key="im_group",
            group_name="INC-1001",
            owner_id="alice",
            member_ids=["alice", "bob"],
            member_id_type="userid",
            idempotency_key="incident-binding-stable-key",
        )

    assert result.success
    assert result.payload["reused"] is True
    client.appchat.get.assert_called_once_with(result.payload["chat_id"])
    client.appchat.create.assert_not_called()


def test_wecom_create_group_does_not_create_when_preflight_is_inconclusive():
    client = mock.Mock()
    client.appchat.get.side_effect = WeChatClientException(60011, "permission denied")

    with mock.patch(
        "apps.system_mgmt.providers.builtin.wecom.adapters.im_group.WeChatClient",
        return_value=client,
    ):
        result = WeComIMGroupAdapter.create_group(
            config=CONFIG,
            provider_key="wecom",
            capability_key="im_group",
            group_name="INC-1001",
            owner_id="alice",
            member_ids=["alice", "bob"],
            member_id_type="userid",
            idempotency_key="incident-binding-stable-key",
        )

    assert result.success is False
    assert result.errors[0].code == "provider.permission_denied"


def test_wecom_add_members_preserves_retryable_failure_after_partial_success():
    client = mock.Mock()
    client.appchat.update.side_effect = [
        WeChatClientException(86007, "invalid member"),
        {},
        WeChatClientException(45009, "rate limited"),
    ]

    with mock.patch(
        "apps.system_mgmt.providers.builtin.wecom.adapters.im_group.WeChatClient",
        return_value=client,
    ):
        result = WeComIMGroupAdapter.add_members(
            config=CONFIG,
            provider_key="wecom",
            capability_key="im_group",
            chat_id="chat-1",
            member_ids=["alice", "bob", "carol"],
            member_id_type="userid",
        )

    assert not result.success
    assert result.partial_success
    assert result.retryable
    assert result.payload == {
        "joined_member_ids": ["alice"],
        "invalid_member_ids": [],
        "failed_member_ids": ["bob", "carol"],
    }
    assert result.errors[0].code == "provider.rate_limited"
    client.appchat.create.assert_not_called()


@pytest.mark.parametrize(
    ("external_code", "expected_code"),
    [
        (86001, "provider.chat_id_invalid"),
        (86004, "provider.group_name_invalid"),
        (86005, "provider.owner_invalid"),
        (86006, "provider.member_count_invalid"),
        (86007, "provider.member_invalid"),
        (86207, "provider.owner_not_member"),
    ],
)
def test_wecom_create_group_preserves_safe_parameter_failure_kind(
    external_code,
    expected_code,
):
    client = mock.Mock()
    client.appchat.get.side_effect = WeChatClientException(86003, "not found")
    client.appchat.create.side_effect = WeChatClientException(
        external_code,
        "untrusted provider response",
    )

    with mock.patch(
        "apps.system_mgmt.providers.builtin.wecom.adapters.im_group.WeChatClient",
        return_value=client,
    ):
        result = WeComIMGroupAdapter.create_group(
            config=CONFIG,
            provider_key="wecom",
            capability_key="im_group",
            group_name="INC-1001",
            owner_id="alice",
            member_ids=["alice", "bob"],
            member_id_type="userid",
            idempotency_key="incident-binding-stable-key",
        )

    assert result.success is False
    assert result.errors[0].code == expected_code
    assert result.errors[0].external_code == str(external_code)
    assert "untrusted provider response" not in result.summary


def test_wecom_create_group_rejects_non_userid_and_fewer_than_two_members():
    wrong_type = WeComIMGroupAdapter.create_group(
        config=CONFIG,
        provider_key="wecom",
        capability_key="im_group",
        group_name="INC",
        owner_id="alice",
        member_ids=["alice", "bob"],
        member_id_type="open_id",
        idempotency_key="key",
    )
    too_few = WeComIMGroupAdapter.create_group(
        config=CONFIG,
        provider_key="wecom",
        capability_key="im_group",
        group_name="INC",
        owner_id="alice",
        member_ids=["alice"],
        member_id_type="userid",
        idempotency_key="key",
    )

    assert not wrong_type.success
    assert wrong_type.errors[0].code == "provider.invalid_config"
    assert not too_few.success
    assert too_few.errors[0].code == "provider.invalid_config"


def test_wecom_group_constraints_are_enforced_by_create_and_add():
    too_many_create = WeComIMGroupAdapter.validate_create(
        config=CONFIG,
        provider_key="wecom",
        capability_key="im_group",
        owner_id="user-0",
        member_ids=[f"user-{index}" for index in range(501)],
        member_id_type="userid",
    )
    too_many_add = WeComIMGroupAdapter.add_members(
        config=CONFIG,
        provider_key="wecom",
        capability_key="im_group",
        chat_id="chat-1",
        member_ids=[f"user-{index}" for index in range(51)],
        member_id_type="userid",
    )

    assert not too_many_create.success
    assert too_many_create.errors[0].field == "member_ids"
    assert not too_many_add.success
    assert too_many_add.errors[0].field == "member_ids"


def test_wecom_validate_create_exposes_member_constraint_without_sdk_call():
    result = WeComIMGroupAdapter.validate_create(
        config=CONFIG,
        provider_key="wecom",
        capability_key="im_group",
        owner_id="alice",
        member_ids=["alice"],
        member_id_type="userid",
    )

    assert not result.success
    assert result.errors[0].field == "member_ids"
    assert "至少需要两名成员" in result.summary


def test_wecom_group_connection_verifies_root_department_visibility():
    client = mock.Mock()
    client.agent.get.return_value = {"allow_partys": {"partyid": [2, 3]}}

    with mock.patch(
        "apps.system_mgmt.providers.builtin.wecom.adapters.im_group.WeChatClient",
        return_value=client,
    ):
        result = WeComIMGroupAdapter.test_connection(
            config=CONFIG,
            provider_key="wecom",
            capability_key="im_group",
        )

    assert result.success is False
    assert result.errors[0].code == "provider.permission_unverified"
    assert result.payload["missing_requirements"] == ["root_department_visibility"]
    client.agent.get.assert_called_once_with(CONFIG["agent_id"])


def test_wecom_group_connection_is_ready_when_root_department_is_visible():
    client = mock.Mock()
    client.agent.get.return_value = {"allow_partys": {"partyid": [1]}}

    with mock.patch(
        "apps.system_mgmt.providers.builtin.wecom.adapters.im_group.WeChatClient",
        return_value=client,
    ):
        result = WeComIMGroupAdapter.test_connection(
            config=CONFIG,
            provider_key="wecom",
            capability_key="im_group",
        )

    assert result.success


def test_wecom_group_connection_explains_trusted_ip_failure():
    client = mock.Mock()
    client.fetch_access_token.side_effect = WeChatClientException(
        60020,
        "not allow to access from your ip",
    )

    with mock.patch(
        "apps.system_mgmt.providers.builtin.wecom.adapters.im_group.WeChatClient",
        return_value=client,
    ):
        result = WeComIMGroupAdapter.test_connection(
            config=CONFIG,
            provider_key="wecom",
            capability_key="im_group",
        )

    assert result.success is False
    assert result.errors[0].code == "provider.permission_denied"
    assert result.errors[0].external_code == "60020"
    assert result.summary == ("当前 BK-Lite 服务出口 IP 未加入企业微信自建应用的企业可信 IP，" "请在企业微信管理后台配置后重试")


def test_wecom_group_get_add_and_send_share_the_sdk_contract():
    client = mock.Mock()
    client.appchat.get.return_value = {"chat_info": {"chatid": "chat-1"}}

    with mock.patch(
        "apps.system_mgmt.providers.builtin.wecom.adapters.im_group.WeChatClient",
        return_value=client,
    ):
        fetched = WeComIMGroupAdapter.get_group(
            config=CONFIG,
            provider_key="wecom",
            capability_key="im_group",
            chat_id="chat-1",
        )
        added = WeComIMGroupAdapter.add_members(
            config=CONFIG,
            provider_key="wecom",
            capability_key="im_group",
            chat_id="chat-1",
            member_ids=["bob", "carol", "bob"],
            member_id_type="userid",
        )
        sent = WeComIMGroupAdapter.send_group_message(
            config=CONFIG,
            provider_key="wecom",
            capability_key="im_group",
            chat_id="chat-1",
            content="Incident 摘要",
            idempotency_key="message-key",
        )

    assert fetched.success and fetched.payload["chat_id"] == "chat-1"
    assert added.success and added.payload["invalid_member_ids"] == []
    assert sent.success
    assert client.appchat.get.call_args_list == [
        mock.call("chat-1"),
        mock.call("chat-1"),
    ]
    client.appchat.update.assert_called_once_with(
        "chat-1",
        add_user_list=["bob", "carol"],
    )
    client.appchat.send_text.assert_called_once_with("chat-1", "Incident 摘要")


@pytest.mark.parametrize("operation", ["get_group", "add_members"])
def test_wecom_unknown_group_86001_is_normalized_as_group_not_found(operation):
    client = mock.Mock()
    client.appchat.get.side_effect = WeChatClientException(86001, "invalid chatid")

    kwargs = {"chat_id": "known-generated-chat-id"}
    if operation == "add_members":
        kwargs.update(member_ids=["alice"], member_id_type="userid")

    with mock.patch(
        "apps.system_mgmt.providers.builtin.wecom.adapters.im_group.WeChatClient",
        return_value=client,
    ):
        result = getattr(WeComIMGroupAdapter, operation)(
            config=CONFIG,
            provider_key="wecom",
            capability_key="im_group",
            **kwargs,
        )

    assert not result.success
    assert result.errors[0].code == "provider.group_not_found"
    client.appchat.update.assert_not_called()


def test_wecom_add_members_recovers_after_ack_loss_by_skipping_existing_users():
    client = mock.Mock()
    client.appchat.get.return_value = {"chat_info": {"chatid": "chat-1", "userlist": ["alice"]}}

    with mock.patch(
        "apps.system_mgmt.providers.builtin.wecom.adapters.im_group.WeChatClient",
        return_value=client,
    ):
        result = WeComIMGroupAdapter.add_members(
            config=CONFIG,
            provider_key="wecom",
            capability_key="im_group",
            chat_id="chat-1",
            member_ids=["alice", "bob"],
            member_id_type="userid",
        )

    assert result.success
    assert result.payload["joined_member_ids"] == ["alice", "bob"]
    client.appchat.update.assert_called_once_with(
        "chat-1",
        add_user_list=["bob"],
    )


def test_wecom_add_members_isolates_invalid_userids_without_blocking_valid_members():
    client = mock.Mock()

    def update(_chat_id, *, add_user_list):
        if "invalid-bob" in add_user_list:
            raise WeChatClientException(86007, "invalid member")
        return {}

    client.appchat.update.side_effect = update
    with mock.patch(
        "apps.system_mgmt.providers.builtin.wecom.adapters.im_group.WeChatClient",
        return_value=client,
    ):
        result = WeComIMGroupAdapter.add_members(
            config=CONFIG,
            provider_key="wecom",
            capability_key="im_group",
            chat_id="chat-1",
            member_ids=["alice", "invalid-bob", "carol"],
            member_id_type="userid",
        )

    assert result.success
    assert result.partial_success
    assert result.payload["joined_member_ids"] == ["alice", "carol"]
    assert result.payload["invalid_member_ids"] == ["invalid-bob"]
    assert client.appchat.update.call_args_list == [
        mock.call("chat-1", add_user_list=["alice", "invalid-bob", "carol"]),
        mock.call("chat-1", add_user_list=["alice"]),
        mock.call("chat-1", add_user_list=["invalid-bob", "carol"]),
        mock.call("chat-1", add_user_list=["invalid-bob"]),
        mock.call("chat-1", add_user_list=["carol"]),
    ]


def test_wecom_add_members_separates_platform_failure_from_invalid_userids_after_partial_success():
    client = mock.Mock()
    client.appchat.update.side_effect = [
        WeChatClientException(86007, "invalid member"),
        {},
        WeChatClientException(60011, "permission denied"),
    ]

    with mock.patch(
        "apps.system_mgmt.providers.builtin.wecom.adapters.im_group.WeChatClient",
        return_value=client,
    ):
        result = WeComIMGroupAdapter.add_members(
            config=CONFIG,
            provider_key="wecom",
            capability_key="im_group",
            chat_id="chat-1",
            member_ids=["alice", "bob", "carol"],
            member_id_type="userid",
        )

    assert result.success
    assert result.partial_success
    assert result.payload == {
        "joined_member_ids": ["alice"],
        "invalid_member_ids": [],
        "failed_member_ids": ["bob", "carol"],
    }
    assert result.errors[0].code == "provider.permission_denied"
    assert result.summary == "WeCom group members partially added"


def test_wecom_add_members_bounds_invalid_member_isolation_calls():
    client = mock.Mock()
    client.appchat.update.side_effect = WeChatClientException(86007, "invalid member")
    member_ids = [f"invalid-{index}" for index in range(50)]

    with mock.patch(
        "apps.system_mgmt.providers.builtin.wecom.adapters.im_group.WeChatClient",
        return_value=client,
    ):
        result = WeComIMGroupAdapter.add_members(
            config=CONFIG,
            provider_key="wecom",
            capability_key="im_group",
            chat_id="chat-1",
            member_ids=member_ids,
            member_id_type="userid",
        )

    assert result.success
    assert result.partial_success
    assert set(result.payload["invalid_member_ids"]) | set(result.payload["failed_member_ids"]) == set(member_ids)
    assert client.appchat.get.call_count + client.appchat.update.call_count == 32


def test_wecom_manifest_registers_im_group_capability():
    load_builtin_providers(force=True)

    manifest = get_provider_registry().get("wecom")
    capability = manifest.get_capability("im_group")

    assert capability.adapter_key == "wecom.im_group"
    assert capability.adapter_path == "adapters.im_group.WeComIMGroupAdapter"
