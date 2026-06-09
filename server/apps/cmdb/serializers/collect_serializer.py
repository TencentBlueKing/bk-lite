# -- coding: utf-8 --
# @File: collect_serializer.py
# @Time: 2025/3/3 13:58
# @Author: windyzhao
from rest_framework import serializers
import copy

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes, PERMISSION_TASK
from apps.cmdb.models.collect_model import (
    ALLOWED_TOPOLOGY_FALLBACK_STRATEGIES,
    ALLOWED_TOPOLOGY_PROTOCOLS,
    CollectModels,
    DEFAULT_TOPOLOGY_FALLBACK_STRATEGY,
    DEFAULT_TOPOLOGY_MIN_CONFIDENCE,
    DEFAULT_TOPOLOGY_PROTOCOLS,
    OidMapping,
    normalize_topology_contract,
)
from apps.cmdb.services.collect_credential_pool_service import CollectCredentialPoolService
from apps.cmdb.services.encrypt_collect_password import get_collect_model_passwords
from apps.cmdb.utils.config_file_path import validate_absolute_path
from apps.core.utils.serializers import UsernameSerializer, AuthSerializer

class CollectModelSerializer(AuthSerializer):
    permission_key = PERMISSION_TASK

    class Meta:
        model = CollectModels
        fields = "__all__"
        extra_kwargs = {
            # "name": {"required": True},
            # "task_type": {"required": True},
        }

    def _get_attr_or_instance_value(self, attrs, field_name):
        value = attrs.get(field_name)
        if value is None and self.instance is not None:
            value = getattr(self.instance, field_name, None)
        return value

    def _get_effective_params(self, attrs):
        instance_params = {}
        if self.instance is not None:
            instance_params = dict(getattr(self.instance, "params", None) or {})

        raw_params = attrs.get("params")
        if raw_params is None:
            return instance_params

        params = dict(instance_params)
        params.update(dict(raw_params or {}))
        return params

    @staticmethod
    def _should_validate_network_topology(task_type, model_id):
        return task_type == CollectPluginTypes.SNMP or model_id == "network"

    @staticmethod
    def _validate_topology_params(params):
        errors = {}

        raw_protocols = params.get("topology_protocols")
        if raw_protocols is None:
            topology_protocols = list(DEFAULT_TOPOLOGY_PROTOCOLS)
        elif not isinstance(raw_protocols, list):
            errors["topology_protocols"] = "请选择至少一种拓扑协议"
            topology_protocols = []
        else:
            topology_protocols = []
            invalid_protocols = []
            for protocol in raw_protocols:
                if protocol not in ALLOWED_TOPOLOGY_PROTOCOLS:
                    invalid_protocols.append(protocol)
                    continue
                if protocol not in topology_protocols:
                    topology_protocols.append(protocol)
            if invalid_protocols:
                errors["topology_protocols"] = f"仅支持以下拓扑协议: {', '.join(ALLOWED_TOPOLOGY_PROTOCOLS)}"

        topology_fallback_strategy = params.get(
            "topology_fallback_strategy", DEFAULT_TOPOLOGY_FALLBACK_STRATEGY
        )
        if topology_fallback_strategy not in ALLOWED_TOPOLOGY_FALLBACK_STRATEGIES:
            errors["topology_fallback_strategy"] = (
                "拓扑回退策略不合法"
            )

        raw_min_confidence = params.get("min_confidence", DEFAULT_TOPOLOGY_MIN_CONFIDENCE)
        try:
            min_confidence = float(raw_min_confidence)
        except (TypeError, ValueError):
            errors["min_confidence"] = "置信度阈值必须是 0 到 1 之间的数字"
        else:
            if min_confidence < 0 or min_confidence > 1:
                errors["min_confidence"] = "置信度阈值必须是 0 到 1 之间的数字"

        if errors:
            raise serializers.ValidationError({"params": errors})

        normalized = normalize_topology_contract(
            {
                **params,
                "topology_protocols": topology_protocols,
                "topology_fallback_strategy": topology_fallback_strategy,
                "min_confidence": min_confidence,
            }
        )
        params.update(normalized)
        return params

    @staticmethod
    def _normalize_topology_params(params):
        params.update(normalize_topology_contract(params))
        return params

    def validate(self, attrs):
        task_type = self._get_attr_or_instance_value(attrs, "task_type")
        model_id = self._get_attr_or_instance_value(attrs, "model_id")

        if task_type != CollectPluginTypes.CONFIG_FILE:
            params = self._get_effective_params(attrs)
            if self._should_validate_network_topology(task_type, model_id):
                if normalize_topology_contract(params)["has_network_topo"]:
                    attrs["params"] = self._validate_topology_params(params)
                else:
                    attrs["params"] = self._normalize_topology_params(params)
            return attrs

        raw_params = attrs.get("params")
        if raw_params is None and self.instance is not None:
            raw_params = self.instance.params

        params = dict(raw_params or {})
        file_path = (params.get("config_file_path") or "").strip()
        if not validate_absolute_path(file_path):
            raise serializers.ValidationError({"params": "请输入有效的配置文件完整绝对路径，不能填写目录"})

        params.update(
            {
                "config_file_path": file_path,
            }
        )

        raw_instances = attrs.get("instances")
        if raw_instances is None and self.instance is not None:
            raw_instances = self.instance.instances

        if not raw_instances:
            raise serializers.ValidationError("请选择主机")

        attrs["ip_range"] = ""

        attrs["params"] = params
        attrs["driver_type"] = CollectDriverTypes.JOB
        return attrs

    def to_representation(self, instance):
        """重写序列化输出"""
        representation = super().to_representation(instance)
        # 对返回的凭据中的密码字段进行脱敏处理
        credential = CollectCredentialPoolService.normalize_pool(copy.deepcopy(representation.get("credential")))
        encrypted_fields = get_collect_model_passwords(collect_model_id=instance.model_id, driver_type=instance.driver_type)
        for item in credential:
            if not isinstance(item, dict):
                continue
            for encrypted_field in encrypted_fields:
                if encrypted_field in item:
                    item[encrypted_field] = "******"

        representation["credential"] = credential

        if self._should_validate_network_topology(instance.task_type, instance.model_id):
            raw_params = dict(representation.get("params") or {})
            representation["params"] = self._normalize_topology_params(raw_params)

        return representation


class CollectModelIdStatusSerializer(AuthSerializer):
    permission_key = PERMISSION_TASK

    class Meta:
        model = CollectModels
        fields = ("model_id", "driver_type", "exec_status")


class CollectModelLIstSerializer(AuthSerializer):
    permission_key = PERMISSION_TASK
    message = serializers.SerializerMethodField()
    _should_validate_network_topology = staticmethod(CollectModelSerializer._should_validate_network_topology)
    _normalize_topology_params = staticmethod(CollectModelSerializer._normalize_topology_params)

    class Meta:
        model = CollectModels
        fields = [
            "id",
            "name",
            "task_type",
            "driver_type",
            "model_id",
            "exec_status",
            "updated_at",
            "message",
            "exec_time",
            "created_by",
            "input_method",
            "params",
            "team",
            "permissions",
            "data_cleanup_strategy",
            "expire_days",
        ]

    @staticmethod
    def get_message(instance):
        if instance.collect_digest:
            return instance.collect_digest

        data = {
            "add": 0,
            "update": 0,
            "delete": 0,
            "association": 0,
        }
        return data

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if self._should_validate_network_topology(instance.task_type, instance.model_id):
            raw_params = dict(representation.get("params") or {})
            representation["params"] = self._normalize_topology_params(raw_params)
        return representation


class OidModelSerializer(UsernameSerializer):
    class Meta:
        model = OidMapping
        fields = "__all__"
        extra_kwargs = {}
