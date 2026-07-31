from unittest import mock

from wechatpy.exceptions import WeChatClientException

from apps.system_mgmt.providers.adapters.wecom import WeComIMGroupAdapter
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
        "apps.system_mgmt.providers.adapters.wecom.WeChatClient",
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
    assert len(result.payload["chat_id"]) == 32
    client.appchat.create.assert_called_once_with(
        chat_id=result.payload["chat_id"],
        name="INC-1001",
        owner="alice",
        user_list=["alice", "bob"],
    )


def test_wecom_create_group_reuses_existing_deterministic_group_before_create():
    client = mock.Mock()
    client.appchat.get.return_value = {"chat_info": {"chatid": "existing"}}

    with mock.patch(
        "apps.system_mgmt.providers.adapters.wecom.WeChatClient",
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
        "apps.system_mgmt.providers.adapters.wecom.WeChatClient",
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
    client.appchat.create.assert_not_called()


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
        "apps.system_mgmt.providers.adapters.wecom.WeChatClient",
        return_value=client,
    ):
        result = WeComIMGroupAdapter.test_connection(
            config=CONFIG,
            provider_key="wecom",
            capability_key="im_group",
        )

    assert result.success is False
    assert result.errors[0].code == "provider.permission_unverified"
    assert result.payload["missing_requirements"] == [
        "root_department_visibility"
    ]
    client.agent.get.assert_called_once_with(CONFIG["agent_id"])


def test_wecom_group_connection_is_ready_when_root_department_is_visible():
    client = mock.Mock()
    client.agent.get.return_value = {"allow_partys": {"partyid": [1]}}

    with mock.patch(
        "apps.system_mgmt.providers.adapters.wecom.WeChatClient",
        return_value=client,
    ):
        result = WeComIMGroupAdapter.test_connection(
            config=CONFIG,
            provider_key="wecom",
            capability_key="im_group",
        )

    assert result.success


def test_wecom_group_get_add_and_send_share_the_sdk_contract():
    client = mock.Mock()
    client.appchat.get.return_value = {"chat_info": {"chatid": "chat-1"}}

    with mock.patch(
        "apps.system_mgmt.providers.adapters.wecom.WeChatClient",
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
    client.appchat.get.assert_called_once_with("chat-1")
    client.appchat.update.assert_called_once_with(
        "chat-1",
        add_user_list=["bob", "carol"],
    )
    client.appchat.send_text.assert_called_once_with("chat-1", "Incident 摘要")


def test_wecom_manifest_registers_im_group_capability():
    load_builtin_providers(force=True)

    manifest = get_provider_registry().get("wecom")
    capability = manifest.get_capability("im_group")

    assert capability.adapter_key == "wecom.im_group"
    assert (
        capability.adapter_path
        == "apps.system_mgmt.providers.adapters.wecom.WeComIMGroupAdapter"
    )
