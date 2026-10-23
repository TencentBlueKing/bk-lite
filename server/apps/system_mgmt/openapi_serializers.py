"""system_mgmt 对外暴露专用 serializer（schema 即契约，字段只增不删不改名）。"""

from rest_framework import serializers

from apps.core.openapi.serializers import OpenAPIRequestSerializer

_USER_SELECTORS = ("user_id", "username", "usernames", "search")
_DIRECTORY_PAGE_SIZE_DEFAULT = 200
_DIRECTORY_PAGE_SIZE_MAX = 500
_USERNAMES_MAX = 100


class StrictBooleanField(serializers.BooleanField):
    """只接受 JSON 布尔或字面 true/false，拒绝 1/True/yes 等宽松值。"""

    def to_internal_value(self, data):
        if data is True or data is False:
            return data
        if data in ("true", "false"):
            return data == "true"
        self.fail("invalid", input=data)


class DirectoryPageSerializer(OpenAPIRequestSerializer):
    page = serializers.IntegerField(required=False, default=1, min_value=1)
    page_size = serializers.IntegerField(required=False, default=_DIRECTORY_PAGE_SIZE_DEFAULT, min_value=1)
    group_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    include_children = StrictBooleanField(required=False, default=False)

    def validate_page_size(self, value):
        return min(int(value), _DIRECTORY_PAGE_SIZE_MAX)


class SystemMgmtGroupsQuerySerializer(DirectoryPageSerializer):
    """组织目录查询。组织身份只允许由网关注入。"""


class SystemMgmtNotificationChannelQuerySerializer(DirectoryPageSerializer):
    """当前组织可外部投递的通知渠道。组织身份只允许由网关注入。"""


class SystemMgmtNotificationSendSerializer(OpenAPIRequestSerializer):
    """向目录中的渠道投递一条消息。不接受附件，不暴露渠道配置。"""

    channel_id = serializers.IntegerField(min_value=1)
    title = serializers.CharField(required=False, allow_blank=True, default="", max_length=512)
    content = serializers.CharField(max_length=20000)
    receivers = serializers.ListField(
        child=serializers.CharField(allow_blank=False, max_length=150),
        min_length=1,
        max_length=100,
    )
    group_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    include_children = StrictBooleanField(required=False, default=False)

    def validate_content(self, value):
        if not str(value).strip():
            raise serializers.ValidationError("content must not be blank")
        return value

    def validate_receivers(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError("receivers must be unique")
        return value


class NotificationSendParameterSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=32)
    type = serializers.CharField(max_length=16)
    required = serializers.BooleanField()
    description = serializers.CharField()


class NotificationChannelItemSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=100)
    channel_type = serializers.CharField(max_length=30)
    description = serializers.CharField(allow_blank=True)
    delivery_mode = serializers.CharField(max_length=32)
    recipient_mode = serializers.CharField(max_length=32)
    availability = serializers.CharField(max_length=32)
    send_parameters = NotificationSendParameterSerializer(many=True)


class NotificationChannelPageResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField(min_value=0)
    page = serializers.IntegerField(min_value=1)
    page_size = serializers.IntegerField(min_value=1)
    results = NotificationChannelItemSerializer(many=True)


class NotificationSendResponseSerializer(serializers.Serializer):
    channel_id = serializers.IntegerField(min_value=1)
    channel_type = serializers.CharField(max_length=30)
    delivery_code = serializers.CharField(max_length=64)


class SystemMgmtUsersQuerySerializer(DirectoryPageSerializer):
    """用户目录查询。组织身份只允许由网关注入。"""

    user_id = serializers.RegexField(regex=r"^[1-9][0-9]*$", required=False)
    username = serializers.CharField(required=False, allow_blank=False, max_length=100)
    usernames = serializers.CharField(required=False, allow_blank=False, max_length=4096)
    search = serializers.CharField(required=False, allow_blank=False, max_length=128)
    disabled = StrictBooleanField(required=False)

    def validate_usernames(self, value):
        names = []
        seen = set()
        for item in str(value).split(","):
            name = item.strip()
            if not name or name in seen:
                continue
            seen.add(name)
            names.append(name)
        if not names:
            raise serializers.ValidationError("usernames must contain at least one username")
        if len(names) > _USERNAMES_MAX:
            raise serializers.ValidationError(f"usernames at most {_USERNAMES_MAX}")
        return names

    def validate(self, attrs):
        present = [name for name in _USER_SELECTORS if name in attrs]
        if len(present) > 1:
            raise serializers.ValidationError("at most one of user_id, username, usernames, search")
        return attrs
