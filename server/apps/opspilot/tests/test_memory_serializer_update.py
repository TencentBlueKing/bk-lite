"""记忆条目更新只提交 content 时不必再传 memory_space/title。"""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.exceptions import APIException

from apps.opspilot.models.memory_mgmt import Memory, MemorySpace
from apps.opspilot.serializers.memory_serializer import (
    MEMORY_RETRIEVE_CONTENT_LIMIT_MAX,
    MemoryContentConflict,
    MemorySerializer,
    apply_memory_content_splice,
    parse_memory_content_limit,
    parse_memory_content_offset,
)

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


def test_parse_memory_content_limit_none_invalid_and_cap():
    assert parse_memory_content_limit(None) is None
    assert parse_memory_content_limit("80") == 80
    assert parse_memory_content_limit(str(MEMORY_RETRIEVE_CONTENT_LIMIT_MAX + 9)) == MEMORY_RETRIEVE_CONTENT_LIMIT_MAX
    with pytest.raises(ValueError):
        parse_memory_content_limit("")
    with pytest.raises(ValueError):
        parse_memory_content_limit("0")
    with pytest.raises(ValueError):
        parse_memory_content_limit("-1")


def test_parse_memory_content_offset_defaults_and_rejects_invalid():
    assert parse_memory_content_offset(None) == 0
    assert parse_memory_content_offset("") == 0
    assert parse_memory_content_offset("80") == 80
    with pytest.raises(ValueError):
        parse_memory_content_offset("-1")
    with pytest.raises(ValueError):
        parse_memory_content_offset("abc")


def test_apply_memory_content_splice_replaces_middle_and_rejects_oob():
    assert apply_memory_content_splice("ABCDEFGHIJ", 3, 4, "xyz") == "ABCxyzHIJ"
    assert apply_memory_content_splice("ABCDEFGHIJ", 0, 3, "") == "DEFGHIJ"
    with pytest.raises(ValueError, match="超出正文范围"):
        apply_memory_content_splice("abc", 2, 4, "x")
    with pytest.raises(ValueError, match="单次写入内容过长"):
        apply_memory_content_splice("abc", 0, 1, "x" * (MEMORY_RETRIEVE_CONTENT_LIMIT_MAX + 1))


def test_partial_update_splices_page_without_replacing_all():
    memory = _memory()
    memory.content = "ABCDEFGHIJ"
    memory.save(update_fields=["content"])
    serializer = MemorySerializer(
        memory,
        data={
            "content": "xyz",
            "content_offset": 3,
            "content_replace_length": 4,
            "expected_updated_at": memory.updated_at,
        },
        partial=True,
    )
    assert serializer.is_valid(), serializer.errors
    serializer.save()
    memory.refresh_from_db()
    assert memory.content == "ABCxyzHIJ"
    assert memory.title == "m-1"
    assert serializer.data["content"] == "xyz"
    assert serializer.data["content_length"] == 9
    assert serializer.data["content_offset"] == 3
    assert serializer.data["content_truncated"] is True


def test_partial_update_splice_requires_expected_updated_at():
    memory = _memory()
    serializer = MemorySerializer(
        memory,
        data={"content": "xyz", "content_offset": 0, "content_replace_length": 1},
        partial=True,
    )
    assert serializer.is_valid() is False
    assert "expected_updated_at" in serializer.errors


def test_partial_update_splice_requires_offset_and_length_together():
    memory = _memory()
    serializer = MemorySerializer(memory, data={"content": "xyz", "content_offset": 1}, partial=True)
    assert serializer.is_valid() is False
    serializer = MemorySerializer(memory, data={"content_offset": 0, "content_replace_length": 1}, partial=True)
    assert serializer.is_valid() is False


def test_partial_update_splice_rejects_stale_expected_updated_at():
    memory = _memory()
    stale = memory.updated_at
    Memory.objects.filter(pk=memory.pk).update(
        content="ABCDEFGHIJ",
        updated_at=timezone.now() + timedelta(seconds=5),
    )
    memory.refresh_from_db()
    serializer = MemorySerializer(
        memory,
        data={
            "content": "xyz",
            "content_offset": 3,
            "content_replace_length": 4,
            "expected_updated_at": stale,
        },
        partial=True,
    )
    assert serializer.is_valid(), serializer.errors
    with pytest.raises(MemoryContentConflict) as captured:
        serializer.save()
    assert isinstance(captured.value, APIException)
    assert captured.value.status_code == 409
    memory.refresh_from_db()
    assert memory.content == "ABCDEFGHIJ"
