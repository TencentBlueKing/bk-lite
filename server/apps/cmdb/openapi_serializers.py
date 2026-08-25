"""cmdb 对外暴露专用 serializer（schema 即契约，字段只增不删不改名）。"""

from rest_framework import serializers

from apps.cmdb.constants.constants import PERMISSION_INSTANCES
from apps.core.openapi.serializers import PaginatedRequestSerializer


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
