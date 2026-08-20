"""记忆条目更新只提交 content 时不必再传 memory_space/title。"""

import pytest

from apps.opspilot.models.memory_mgmt import Memory, MemorySpace
from apps.opspilot.serializers.memory_serializer import MemorySerializer

pytestmark = pytest.mark.django_db


def _memory():
    space = MemorySpace.objects.create(name="s", scope=MemorySpace.SCOPE_TEAM, team=[1])
    return Memory.objects.create(
        memory_space=space,
        title="m-1",
        content="old",
        owner_username="alice",
        owner_domain="d.com",
    )


def test_create_still_requires_memory_space_and_title():
    serializer = MemorySerializer(data={"content": "x"})
    assert serializer.is_valid() is False
    assert "memory_space" in serializer.errors
    assert "title" in serializer.errors


def test_update_accepts_content_only_and_keeps_space_title():
    memory = _memory()
    space_id = memory.memory_space_id
    serializer = MemorySerializer(memory, data={"content": "aaaa"})
    assert serializer.is_valid(), serializer.errors
    serializer.save()
    memory.refresh_from_db()
    assert memory.content == "aaaa"
    assert memory.title == "m-1"
    assert memory.memory_space_id == space_id


def test_partial_update_accepts_content_only():
    memory = _memory()
    serializer = MemorySerializer(memory, data={"content": "bbbb"}, partial=True)
    assert serializer.is_valid(), serializer.errors
    serializer.save()
    memory.refresh_from_db()
    assert memory.content == "bbbb"
    assert memory.title == "m-1"
