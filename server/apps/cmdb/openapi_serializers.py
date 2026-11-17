"""cmdb 对外暴露专用 serializer（schema 即契约，字段只增不删不改名）。"""

from uuid import UUID

from rest_framework import serializers

from apps.cmdb.constants.constants import PERMISSION_INSTANCES
from apps.core.openapi.serializers import OpenAPIRequestSerializer, PaginatedRequestSerializer


class InstUuidField(serializers.CharField):
    """实例 UUID。

    网关 JSON Schema 只暴露普通 string，避免 ITSM 把 format:uuid 当成变量逻辑类型
    把引用变量筛空。运行时仍校验 UUID 形态。
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("min_length", 1)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        try:
            return str(UUID(str(value)))
        except (ValueError, AttributeError, TypeError) as exc:
            raise serializers.ValidationError("Must be a valid UUID.") from exc


class CmdbInstanceListSerializer(PaginatedRequestSerializer):
    """查询实例列表（原 /api/open/models/{model_id}/instances）。组织身份只允许由网关注入。"""

    model_id = serializers.CharField()
    order = serializers.CharField(required=False, default="", allow_blank=True)
    filters = serializers.CharField(required=False, default="[]", allow_blank=True)

    def validate_page_size(self, value):
        # 内层 InstanceListQuerySerializer 上限 200；越限钳制，避免落到 BUSINESS_REJECTED。
        return min(max(int(value), 1), 200)


class CmdbModuleDataQuerySerializer(PaginatedRequestSerializer):
    # M1 仅暴露带用户权限过滤的实例分支；PERMISSION_MODEL / PERMISSION_TASK
    # 分支在现有实现中不做按用户过滤，不得经网关暴露
    module = serializers.ChoiceField(choices=[PERMISSION_INSTANCES])
    child_module = serializers.CharField()
    group_id = serializers.IntegerField(min_value=1)
    # 组织锚点（锚点式注入）：JWT 凭据由客户端指定且必须为直属组织，
    # 传非直属组织仅得空结果；API 令牌凭据下网关强制覆盖为绑定组织
    team = serializers.IntegerField(required=False, min_value=1)
    include_children = serializers.BooleanField(required=False, default=False)


class CmdbNoParamsSerializer(OpenAPIRequestSerializer):
    """无查询参数的只读目录接口。"""


class CmdbModelIdSerializer(OpenAPIRequestSerializer):
    model_id = serializers.CharField()


class CmdbInstanceKeySerializer(OpenAPIRequestSerializer):
    model_id = serializers.CharField()
    inst_uuid = InstUuidField()


class CmdbInstanceCreateSerializer(OpenAPIRequestSerializer):
    model_id = serializers.CharField()
    attrs = serializers.DictField()


class CmdbInstanceUpdateSerializer(OpenAPIRequestSerializer):
    model_id = serializers.CharField()
    inst_uuid = InstUuidField()
    attrs = serializers.DictField()


class CmdbInstanceBatchCreateSerializer(OpenAPIRequestSerializer):
    model_id = serializers.CharField()
    items = serializers.ListField(child=serializers.DictField(), min_length=1, max_length=100)


class CmdbInstanceBatchUpdateSerializer(OpenAPIRequestSerializer):
    model_id = serializers.CharField()
    inst_uuids = serializers.ListField(child=InstUuidField(), min_length=1, max_length=100)
    update_data = serializers.DictField()


class CmdbInstanceBatchDeleteSerializer(OpenAPIRequestSerializer):
    model_id = serializers.CharField()
    inst_uuids = serializers.ListField(child=InstUuidField(), min_length=1, max_length=100)


class CmdbInstanceAssociationCreateSerializer(OpenAPIRequestSerializer):
    model_id = serializers.CharField()
    inst_uuid = InstUuidField()
    model_asst_id = serializers.CharField(max_length=255)
    target_model_id = serializers.CharField()
    target_inst_uuid = InstUuidField()


class CmdbInstanceAssociationDeleteSerializer(OpenAPIRequestSerializer):
    model_id = serializers.CharField()
    inst_uuid = InstUuidField()
    dst_inst_uuid = InstUuidField()
    model_asst_id = serializers.CharField(max_length=255)
