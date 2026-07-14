"""MemorySpace / Memory 可见性 helper 单测。

覆盖 get_visible_memories_qs(user) 的核心规则:
- 团队空间对任意用户可见
- 个人空间仅 owner_username/domain 匹配的用户可见
- 个人空间非创建者不可见
- None user / 无 username user 返回空 queryset 且不抛异常
- SimpleNamespace 模拟 user(回归测试常用模式)也能正常过滤

注:helper 不限定 memory_space_id,返回 user 可见全集;
单空间/全空间的口径由调用方通过 ``qs.filter(memory_space_id=...)`` 限定。
"""

import pytest

from apps.base.models import User
from apps.opspilot.memory.visibility import get_visible_memories_qs
from apps.opspilot.models.memory_mgmt import Memory, MemorySpace

pytestmark = pytest.mark.django_db


def _make_user(username, domain="domain.com"):
    return User.objects.create_user(
        username=username,
        password="x",
        domain=domain,
        locale="zh-CN",
    )


def _make_team_space():
    return MemorySpace.objects.create(
        name="team-space",
        scope=MemorySpace.SCOPE_TEAM,
        team=[1],
    )


def _make_personal_space(owner_user):
    return MemorySpace.objects.create(
        name=f"personal-{owner_user.username}",
        scope=MemorySpace.SCOPE_PERSONAL,
        team=[1],
    )


def _make_memory(space, owner_username, owner_domain="domain.com"):
    return Memory.objects.create(
        memory_space=space,
        title=f"m-{owner_username}",
        content="body",
        owner_username=owner_username,
        owner_domain=owner_domain,
    )


class TestGetVisibleMemoriesQs:
    def test_team_space_visible_to_any_user(self):
        """团队空间对任意用户可见,不被可见性规则过滤。"""
        team_space = _make_team_space()
        _make_memory(team_space, "alice")
        _make_memory(team_space, "bob")
        user = _make_user("charlie")

        visible = get_visible_memories_qs(user)

        assert visible.count() == 2

    def test_personal_space_visible_to_creator(self):
        """个人空间对创建者本人可见。"""
        owner = _make_user("alice", domain="domain.com")
        personal = _make_personal_space(owner)
        _make_memory(personal, "alice", owner_domain="domain.com")
        _make_memory(personal, "alice", owner_domain="domain.com")

        visible = get_visible_memories_qs(owner)

        assert visible.count() == 2

    def test_personal_space_invisible_to_non_creator(self):
        """个人空间对非创建者不可见,即使同域不同用户。"""
        owner = _make_user("alice", domain="domain.com")
        other = _make_user("bob", domain="domain.com")
        personal = _make_personal_space(owner)
        _make_memory(personal, "alice", owner_domain="domain.com")
        team_space = _make_team_space()
        _make_memory(team_space, "alice")

        visible = get_visible_memories_qs(other)

        # 团队空间可见,个人空间不可见
        assert visible.count() == 1
        assert not visible.filter(memory_space=personal).exists()

    def test_none_user_returns_empty(self):
        """None user 返回空 queryset,不抛异常。"""
        owner = _make_user("alice", domain="domain.com")
        personal = _make_personal_space(owner)
        _make_memory(personal, "alice", owner_domain="domain.com")

        visible = get_visible_memories_qs(None)

        assert visible.count() == 0

    def test_user_without_username_returns_empty(self):
        """没有 username 的 user 对象返回空 queryset。"""
        from types import SimpleNamespace

        visible = get_visible_memories_qs(SimpleNamespace(domain="d.com", is_superuser=True))

        assert visible.count() == 0

    def test_simple_namespace_user_works(self):
        """SimpleNamespace 模拟 user(无 is_authenticated)也能正常过滤。

        这与 view 层常见测试模式兼容;helper 不强制要求 is_authenticated。
        """
        from types import SimpleNamespace

        team_space = _make_team_space()
        personal = _make_personal_space(_make_user("alice", domain="d.com"))
        _make_memory(team_space, "alice")
        _make_memory(personal, "alice", owner_domain="d.com")
        _make_memory(personal, "bob", owner_domain="d.com")

        user = SimpleNamespace(username="alice", domain="d.com", is_superuser=True)
        visible = get_visible_memories_qs(user)

        # 团队记忆 + alice 自己的个人记忆
        assert visible.count() == 2
        assert visible.filter(memory_space=personal).count() == 1

    def test_personal_space_matches_owner_username_and_domain(self):
        """个人空间可见性必须 username+domain 双匹配;username 相同但 domain 不同不可见。"""
        owner = _make_user("alice", domain="domain.com")
        impostor = _make_user("alice", domain="other.com")
        personal = _make_personal_space(owner)
        _make_memory(personal, "alice", owner_domain="domain.com")
        team_space = _make_team_space()
        _make_memory(team_space, "alice")

        visible = get_visible_memories_qs(impostor)

        # 团队空间可见,他人个人空间不可见
        assert visible.count() == 1
        assert not visible.filter(memory_space=personal).exists()

    def test_combined_with_memory_space_filter(self):
        """helper 与外部 memory_space_id 过滤组合:单空间计数。"""
        owner = _make_user("alice", domain="domain.com")
        other = _make_user("bob", domain="domain.com")
        personal = _make_personal_space(owner)
        _make_memory(personal, "alice", owner_domain="domain.com")
        _make_memory(personal, "alice", owner_domain="domain.com")

        # 对创建者:helper & personal = 2
        owner_count = get_visible_memories_qs(owner).filter(memory_space_id=personal.id).count()
        assert owner_count == 2

        # 对非创建者:helper & personal = 0(关键 Bug 场景)
        other_count = get_visible_memories_qs(other).filter(memory_space_id=personal.id).count()
        assert other_count == 0
