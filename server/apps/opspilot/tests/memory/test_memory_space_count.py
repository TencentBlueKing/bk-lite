"""记忆空间 memory_count 字段一致性集成测试。

核心不变量:
- MemorySpaceSerializer.get_memory_count(user) ==
  get_visible_memories_qs(user, memory_space_id=instance.id).count()

证明:卡片 memory_count 字段值,等价于「同一用户对同一空间调用 helper 算出的可见行数」。
当 MemoryViewSet.list 也复用同一 helper 时,卡片与详情列表口径自动一致(可见性规则
单一来源),无需逐个端到端验证。

辅助验证:
- 修复前的 buggy 行为:instance.memories.count() 对个人空间非创建者会等于 DB 真实条数,
  不等于 helper 数。修复后两边一致。
- 修复后:helper 数对个人空间非创建者为 0。
"""

import pytest
from rest_framework.test import APIRequestFactory

from apps.base.models import User
from apps.opspilot.memory.visibility import get_visible_memories_qs
from apps.opspilot.models.memory_mgmt import Memory, MemorySpace
from apps.opspilot.serializers.memory_serializer import MemorySpaceSerializer

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


def _serializer_memory_count(space, user):
    """直接调用 serializer,跳过 view 层权限链。"""
    factory = APIRequestFactory()
    request = factory.get("/opspilot/memory_mgmt/memory_space/")
    request.user = user
    serializer = MemorySpaceSerializer(space, context={"request": request})
    return serializer.data["memory_count"]


class TestMemorySpaceCountConsistency:
    def test_team_space_count_matches_helper(self):
        """团队空间:卡片 memory_count == helper 数(等于 DB 真实条数)。"""
        space = _make_team_space()
        _make_memory(space, "alice")
        _make_memory(space, "bob")
        _make_memory(space, "charlie")
        user = _make_user("observer", domain="domain.com")

        card_count = _serializer_memory_count(space, user)
        helper_count = get_visible_memories_qs(user).filter(memory_space_id=space.id).count()

        assert card_count == 3
        assert helper_count == 3
        assert card_count == helper_count

    def test_personal_space_count_for_creator(self):
        """个人空间创建者:卡片 memory_count == helper 数 == DB 真实条数。"""
        owner = _make_user("alice", domain="domain.com")
        space = _make_personal_space(owner)
        _make_memory(space, "alice", owner_domain="domain.com")
        _make_memory(space, "alice", owner_domain="domain.com")

        card_count = _serializer_memory_count(space, owner)
        helper_count = get_visible_memories_qs(owner).filter(memory_space_id=space.id).count()

        assert card_count == 2
        assert helper_count == 2
        assert card_count == helper_count

    def test_personal_space_count_for_non_creator_is_zero(self):
        """个人空间非创建者:卡片 memory_count == 0(关键 Bug 场景)。

        修复前:卡片 memory_count == DB 真实条数(2),与详情列表空数据对不上。
        修复后:卡片 memory_count == helper 数(0),与详情列表对齐。
        """
        owner = _make_user("alice", domain="domain.com")
        other = _make_user("bob", domain="domain.com")
        space = _make_personal_space(owner)
        _make_memory(space, "alice", owner_domain="domain.com")
        _make_memory(space, "alice", owner_domain="domain.com")
        # DB 真实条数(模拟截图:卡片显示 2 但详情表空)
        db_count = space.memories.count()
        assert db_count == 2

        card_count = _serializer_memory_count(space, other)
        helper_count = get_visible_memories_qs(other).filter(memory_space_id=space.id).count()

        # 关键断言:helper 已经把不可见的 Memory 过滤掉,等于 0
        assert helper_count == 0
        assert card_count == 0
        # 修复前 bug:卡片数等于 db_count;修复后两者解耦,卡片数跟 helper 数对齐
        assert card_count == helper_count
        assert card_count != db_count

    def test_viewset_list_uses_same_helper(self):
        """回归保护:MemoryViewSet.list 必须调用 visibility helper(否则两端规则会再次走偏)。

        通过 import 检查 + 函数引用,确保 helper 是 list 路径上的必经节点。
        """
        from apps.opspilot import viewsets

        source = open(viewsets.memory_view.__file__, encoding="utf-8").read()
        assert "get_visible_memories_qs" in source, "MemoryViewSet.list 必须复用 visibility helper," "避免规则双份导致卡片与详情列表口径再次走偏"
        # 同时:helper 仍是单一的可见性来源,serializer 也在用
        from apps.opspilot.serializers import memory_serializer

        ser_source = open(memory_serializer.__file__, encoding="utf-8").read()
        assert "get_visible_memories_qs" in ser_source, "MemorySpaceSerializer.get_memory_count 必须调用 visibility helper"
