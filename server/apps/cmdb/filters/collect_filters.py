# -- coding: utf-8 --
# @File: collect_filters.py
# @Time: 2025/3/3 14:00
# @Author: windyzhao
from django.db.models import Q
from django_filters import CharFilter, FilterSet

from apps.cmdb.models.collect_model import CollectModels, OidMapping
from apps.cmdb.utils.base import get_cmdb_rules
from apps.cmdb.utils.permission import InstancePermissionManage


class CollectModelFilter(FilterSet):
    # inst_id = NumberFilter(field_name="inst_id", lookup_expr="exact", label="实例ID")
    name = CharFilter(field_name="name", lookup_expr="icontains", label="模型ID")
    driver_type = CharFilter(field_name="driver_type", label="任务类型")
    exec_status = CharFilter(field_name="exec_status", label="任务类型")
    model_id = CharFilter(field_name="model_id", label="模型id")

    class Meta:
        model = CollectModels
        fields = ["name", "driver_type", "exec_status", "model_id"]

    @property
    def qs(self):
        # 先获取父类应用所有过滤器后的查询集
        queryset = super().qs

        # 然后应用权限过滤
        filters = self.get_user_permission_filters()
        if filters:
            queryset = queryset.filter(filters)

        return queryset

    def get_user_permission_filters(self):
        """
        获取用户task权限过滤条件
        """
        rules = get_cmdb_rules(self.request)
        result = InstancePermissionManage.get_task_permissions(rules=rules)
        filters = Q()
        if not self.request.user.is_superuser:
            filters |= Q(created_by=self.request.user.username)
        if not result:
            return filters
        for task_type, instance_map in result.items():
            filters |= ~Q(task_type=task_type)
            filters |= Q(id__in=list(instance_map.keys()))
        return filters


class OidModelFilter(FilterSet):
    model = CharFilter(field_name="model", lookup_expr="icontains", label="型号")
    oid = CharFilter(field_name="oid", lookup_expr="icontains", label="oid")
    brand = CharFilter(field_name="brand", lookup_expr="icontains", label="品牌")
    device_type = CharFilter(field_name="device_type", label="类型")

    class Meta:
        model = OidMapping
        fields = ["model", "oid", "brand", "device_type"]
