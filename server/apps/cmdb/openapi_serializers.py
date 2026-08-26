"""cmdb 对外暴露专用 serializer（schema 即契约，字段只增不删不改名）。"""

from rest_framework import serializers

from apps.cmdb.constants.constants import PERMISSION_INSTANCES
from apps.core.openapi.serializers import PaginatedRequestSerializer


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
