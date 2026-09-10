from django.db import transaction
from django.db.models.functions import Left, Length
from rest_framework import serializers, status
from rest_framework.exceptions import APIException

from apps.core.utils.serializers import AuthSerializer, TeamSerializer
from apps.opspilot.memory.visibility import get_visible_memories_qs
from apps.opspilot.models.memory_mgmt import Memory, MemorySpace

# 列表只返回短预览，避免把数 MB 正文塞进记忆列表响应。
MEMORY_LIST_CONTENT_PREVIEW_CHARS = 240
# 详情预览上限；完整正文仅在不带 content_limit 时返回。
MEMORY_RETRIEVE_CONTENT_LIMIT_MAX = 200_000
# updated_at 同时作为切片写乐观锁令牌，必须保留微秒，不能用全局秒级 DATETIME_FORMAT。
MEMORY_VERSION_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"


class MemoryContentConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "memory_content_conflict"
    default_detail = "记忆已被其他人更新，请刷新后重试"


def parse_memory_content_limit(raw) -> int | None:
    """解析 retrieve 的 content_limit。None 表示返回完整正文。"""
    if raw is None:
        return None
    try:
        limit = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("content_limit 必须是正整数") from exc
    if limit < 1:
        raise ValueError("content_limit 必须是正整数")
    return min(limit, MEMORY_RETRIEVE_CONTENT_LIMIT_MAX)


def parse_memory_content_offset(raw) -> int:
    """解析 retrieve 的 content_offset，0 表示从正文开头截取。"""
    if raw is None or raw == "":
        return 0
    try:
        offset = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("content_offset 必须是非负整数") from exc
    if offset < 0:
        raise ValueError("content_offset 必须是非负整数")
    return offset


def apply_memory_content_splice(original: str, offset: int, replace_length: int, replacement: str) -> str:
    """用 replacement 替换 original[offset:offset+replace_length]，供分页编辑写回。"""
    if offset < 0:
        raise ValueError("content_offset 必须是非负整数")
    if replace_length < 0:
        raise ValueError("content_replace_length 必须是非负整数")
    if len(replacement) > MEMORY_RETRIEVE_CONTENT_LIMIT_MAX:
        raise ValueError("单次写入内容过长")
    end = offset + replace_length
    if offset > len(original) or end > len(original):
        raise ValueError("content_offset 超出正文范围")
    return original[:offset] + replacement + original[end:]


def annotate_memory_content_preview(queryset, *, chars: int = MEMORY_LIST_CONTENT_PREVIEW_CHARS):
    """defer 完整 content，在数据库侧截取预览并统计字数。"""
    return queryset.defer("content").annotate(
        _content_preview=Left("content", chars),
        _content_length=Length("content"),
    )


class MemorySpaceSerializer(TeamSerializer, AuthSerializer):
    permission_key = "memory"
    memory_count = serializers.SerializerMethodField()
    masked_storage_config = serializers.SerializerMethodField()

    class Meta:
        model = MemorySpace
        fields = [
            "id",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "domain",
            "updated_by_domain",
            "name",
            "introduction",
            "team",
            "scope",
            "write_rule",
            "default_model",
            "storage_type",
            "storage_config",
            # 只读派生字段（保持现有读取输出不变）
            "permissions",
            "team_name",
            "memory_count",
            "masked_storage_config",
        ]
        extra_kwargs = {
            "storage_config": {"write_only": True},  # 原始配置仅用于写入
        }

    def get_memory_count(self, instance: MemorySpace):
        request = self.context.get("request") if hasattr(self, "context") else None
        user = getattr(request, "user", None)
        return get_visible_memories_qs(user).filter(memory_space_id=instance.id).count()

    def get_masked_storage_config(self, instance: MemorySpace):
        """返回脱敏后的配置"""
        return instance.get_masked_config()

    def validate(self, attrs):
        """校验更新时不允许切换存储类型"""
        if self.instance:  # 更新操作
            new_storage_type = attrs.get("storage_type")
            if new_storage_type and new_storage_type != self.instance.storage_type:
                raise serializers.ValidationError({"storage_type": "不允许切换存储类型，请创建新的记忆空间"})
        return attrs

    def to_representation(self, instance):
        """自定义输出，用脱敏配置替换原始配置"""
        data = super().to_representation(instance)
        # 移除 write_only 的 storage_config，添加脱敏版本
        data.pop("storage_config", None)
        data["storage_config"] = self.get_masked_storage_config(instance)
        return data


class WorkflowMemorySpaceOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MemorySpace
        fields = ("id", "name", "scope", "default_model")


class MemorySerializer(serializers.ModelSerializer):
    updated_at = serializers.DateTimeField(read_only=True, format=MEMORY_VERSION_DATETIME_FORMAT)
    expected_updated_at = serializers.DateTimeField(write_only=True, required=False)
    content_offset = serializers.IntegerField(write_only=True, required=False, min_value=0)
    content_replace_length = serializers.IntegerField(write_only=True, required=False, min_value=0)

    class Meta:
        model = Memory
        fields = [
            "id",
            "created_at",
            "updated_at",
            "expected_updated_at",
            "created_by",
            "updated_by",
            "domain",
            "updated_by_domain",
            "memory_space",
            "title",
            "content",
            "content_offset",
            "content_replace_length",
            "owner_username",
            "owner_domain",
            "organization_id",
        ]
        read_only_fields = ("owner_username", "owner_domain")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 编辑记忆内容时只提交 content；空间与标题已在记录上，更新不必再传。
        if self.instance is not None:
            self.fields["memory_space"].required = False
            self.fields["title"].required = False

    def validate(self, attrs):
        has_offset = "content_offset" in attrs
        has_replace_length = "content_replace_length" in attrs
        if has_offset != has_replace_length:
            raise serializers.ValidationError("content_offset 与 content_replace_length 必须同时提供")
        if has_offset and "content" not in attrs:
            raise serializers.ValidationError("分页写入必须提供 content")
        if has_offset:
            if "expected_updated_at" not in attrs:
                raise serializers.ValidationError({"expected_updated_at": ["分页写入必须提供当前版本"]})
            replacement = attrs.get("content") or ""
            if len(replacement) > MEMORY_RETRIEVE_CONTENT_LIMIT_MAX:
                raise serializers.ValidationError({"content": "单次写入内容过长"})
        return attrs

    def update(self, instance, validated_data):
        offset = validated_data.pop("content_offset", None)
        replace_length = validated_data.pop("content_replace_length", None)
        expected_updated_at = validated_data.pop("expected_updated_at", None)
        if offset is None or replace_length is None:
            return super().update(instance, validated_data)

        replacement = validated_data.get("content") or ""
        with transaction.atomic():
            locked = Memory.objects.select_for_update().get(pk=instance.pk)
            if expected_updated_at != locked.updated_at:
                raise MemoryContentConflict()
            try:
                spliced = apply_memory_content_splice(
                    locked.content or "",
                    offset,
                    replace_length,
                    replacement,
                )
            except ValueError as exc:
                raise serializers.ValidationError({"content": str(exc)}) from exc
            validated_data["content"] = spliced
            updated = super().update(locked, validated_data)
            self._splice_response = {
                "preview": replacement,
                "content_length": len(spliced),
                "offset": offset,
            }
            return updated

    def to_representation(self, instance):
        splice = getattr(self, "_splice_response", None)
        if splice is None:
            return super().to_representation(instance)
        # 切片写成功后禁止把合并后的全文再塞回响应。
        original_content = instance.content
        instance.content = splice["preview"]
        try:
            data = super().to_representation(instance)
        finally:
            instance.content = original_content
        preview = splice["preview"]
        content_length = splice["content_length"]
        offset = splice["offset"]
        data["content"] = preview
        data["content_length"] = content_length
        data["content_offset"] = offset
        data["content_truncated"] = offset > 0 or offset + len(preview) < content_length
        return data


class MemoryListSerializer(MemorySerializer):
    content = serializers.SerializerMethodField()
    content_length = serializers.SerializerMethodField()
    content_truncated = serializers.SerializerMethodField()

    class Meta(MemorySerializer.Meta):
        fields = MemorySerializer.Meta.fields + ["content_length", "content_truncated"]

    def get_content(self, obj):
        preview = getattr(obj, "_content_preview", None)
        if preview is None:
            return ""
        return preview

    def get_content_length(self, obj):
        return int(getattr(obj, "_content_length", 0) or 0)

    def get_content_truncated(self, obj):
        preview = self.get_content(obj) or ""
        return self.get_content_length(obj) > len(preview)
