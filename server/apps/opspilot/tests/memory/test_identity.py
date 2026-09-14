"""记忆个人归属对接系统用户 UUID。"""

from types import SimpleNamespace

import pytest

from apps.base.models import User
from apps.opspilot.memory.engines.base import MemoryEntity
from apps.opspilot.memory.engines.local_engine import LocalMemoryEngine
from apps.opspilot.memory.identity import is_system_user_uuid, resolve_owner_identity, resolve_system_user_uuid, split_external_user_id
from apps.opspilot.memory.visibility import get_visible_memories_qs
from apps.opspilot.models.memory_mgmt import Memory, MemorySpace
from apps.opspilot.services.skill_channel_chat_service import saas_external_user_id
from apps.opspilot.tasks.memory import _commit_memory_write_with_retry
from apps.system_mgmt.models import User as SystemUser

pytestmark = pytest.mark.django_db

ALICE_UUID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def _system_user(username="alice", domain="domain.com", user_id=ALICE_UUID):
    return SystemUser.objects.create(
        username=username,
        domain=domain,
        display_name=username,
        email=f"{username}@{domain or 'example.com'}",
        password="x",
        user_id=user_id,
    )


def _base_user(username="alice", domain="domain.com"):
    return User.objects.create_user(username=username, password="x", domain=domain, locale="zh-CN")


def _personal_space():
    return MemorySpace.objects.create(name="personal", scope=MemorySpace.SCOPE_PERSONAL, team=[1])


class TestIdentityHelpers:
    def test_split_and_uuid_detection(self):
        assert split_external_user_id("alice@domain.com") == ("alice", "domain.com")
        assert split_external_user_id("wecom-user") == ("wecom-user", "")
        assert is_system_user_uuid(ALICE_UUID) is True
        assert is_system_user_uuid("alice@domain.com") is False
        assert is_system_user_uuid("not-a-uuid") is False

    def test_resolve_uuid_from_request_user(self):
        _system_user()
        user = _base_user()
        assert resolve_system_user_uuid(user) == ALICE_UUID
        assert saas_external_user_id(user) == ALICE_UUID

    def test_im_sender_has_no_uuid(self):
        owner = resolve_owner_identity(external_user_id="wecom-zhangsan")
        assert owner.user_id is None
        assert owner.username == "wecom-zhangsan"
        assert owner.domain == ""

    def test_username_change_still_resolves_same_uuid(self):
        sys_user = _system_user()
        user = _base_user()
        assert resolve_system_user_uuid(user) == ALICE_UUID
        sys_user.username = "alice-renamed"
        sys_user.save(update_fields=["username"])
        user.username = "alice-renamed"
        user.save(update_fields=["username"])
        assert resolve_system_user_uuid(user) == ALICE_UUID
        assert saas_external_user_id(user) == ALICE_UUID


class TestMemoryOwnerUuid:
    def test_write_and_read_survive_username_change(self):
        _system_user()
        space = _personal_space()
        _commit_memory_write_with_retry(
            memory_space_id=space.id,
            title="对话记忆",
            content="喜欢浓缩咖啡",
            owner_username="alice",
            owner_domain="domain.com",
            skip_write_rule=True,
        )
        mem = Memory.objects.get(memory_space=space)
        assert mem.owner_user_id == ALICE_UUID
        assert mem.owner_username == "alice"

        sys_user = SystemUser.objects.get(user_id=ALICE_UUID)
        sys_user.username = "alice-new"
        sys_user.save(update_fields=["username"])
        user = _base_user(username="alice-new")

        engine = LocalMemoryEngine(space.id)
        result = engine.read(MemoryEntity(user_id=ALICE_UUID), top_k=5)
        assert "浓缩咖啡" in result.context

        visible = get_visible_memories_qs(user)
        assert visible.filter(id=mem.id).exists()

    def test_visibility_fallback_without_system_user(self):
        owner = _base_user()
        space = _personal_space()
        Memory.objects.create(
            memory_space=space,
            title="t",
            content="c",
            owner_username="alice",
            owner_domain="domain.com",
        )
        assert get_visible_memories_qs(owner).count() == 1
        other = SimpleNamespace(username="alice", domain="other.com")
        assert get_visible_memories_qs(other).count() == 0
