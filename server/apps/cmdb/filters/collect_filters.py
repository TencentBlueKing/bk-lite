# -- coding: utf-8 --
# @File: collect_filters.py
# @Time: 2025/3/3 14:00
# @Author: windyzhao
from django.db.models import Q
from django_filters import CharFilter, FilterSet

from apps.cmdb.collection.physical_server_protocol import PHYSICAL_SERVER_MODEL_ID
from apps.cmdb.constants.constants import CollectDriverTypes
from apps.cmdb.models.collect_model import CollectModels, OidMapping, PortFingerprint


class CollectModelFilter(FilterSet):
    # inst_id = NumberFilter(field_name="inst_id", lookup_expr="exact", label="实例ID")
    name = CharFilter(field_name="name", lookup_expr="icontains", label="模型ID")
    driver_type = CharFilter(field_name="driver_type", label="任务类型")
    exec_status = CharFilter(field_name="exec_status", label="任务类型")
    model_id = CharFilter(field_name="model_id", label="模型id")
    collection_protocol = CharFilter(method="filter_collection_protocol", label="物理服务器采集协议")

    @staticmethod
    def filter_collection_protocol(queryset, _name, value):
        protocol = str(value or "").strip().lower()
        queryset = queryset.filter(
            model_id=PHYSICAL_SERVER_MODEL_ID,
            driver_type=CollectDriverTypes.PROTOCOL,
        )
        if protocol == "ipmi":
            # 历史物理服务器协议任务没有 collection_protocol，按 IPMI 兼容。
            return queryset.filter(Q(params__collection_protocol="ipmi") | Q(params__collection_protocol__isnull=True))
        if protocol == "redfish":
            return queryset.filter(params__collection_protocol="redfish")
        return queryset.none()

    class Meta:
        model = CollectModels
        fields = ["name", "driver_type", "exec_status", "model_id", "collection_protocol"]


class OidModelFilter(FilterSet):
    model = CharFilter(field_name="model", lookup_expr="icontains", label="型号")
    oid = CharFilter(field_name="oid", lookup_expr="icontains", label="oid")
    brand = CharFilter(field_name="brand", lookup_expr="icontains", label="品牌")
    device_type = CharFilter(field_name="device_type", label="类型")

    class Meta:
        model = OidMapping
        fields = ["model", "oid", "brand", "device_type"]


class PortFingerprintFilter(FilterSet):
    target_type = CharFilter(field_name="target_type", label="类型")
    protocol = CharFilter(field_name="protocol", label="协议")

    class Meta:
        model = PortFingerprint
        fields = ["target_type", "protocol", "port"]
