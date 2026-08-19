"""补丁管理对外暴露专用 serializer（schema 即契约，字段只增不删不改名）。"""

from rest_framework import serializers

from apps.core.openapi.serializers import PaginatedRequestSerializer


class ModuleDataQuerySerializer(PaginatedRequestSerializer):
    module = serializers.ChoiceField(choices=["patch_target"])
    child_module = serializers.CharField(required=False, allow_blank=True, default="")
    group_id = serializers.IntegerField(min_value=1)
