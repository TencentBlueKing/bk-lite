# -- coding: utf-8 --
# @File: collect_serializer.py
# @Time: 2025/3/3 13:58
# @Author: windyzhao
from rest_framework import serializers
import copy

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes, PERMISSION_TASK
from apps.cmdb.models.collect_model import CollectModels, OidMapping
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

    def validate(self, attrs):
        task_type = attrs.get("task_type")
        if task_type is None and self.instance is not None:
            task_type = self.instance.task_type

        if task_type != CollectPluginTypes.CONFIG_FILE:
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

        return representation


class CollectModelIdStatusSerializer(AuthSerializer):
    permission_key = PERMISSION_TASK

    class Meta:
        model = CollectModels
        fields = ("model_id", "driver_type", "exec_status")


class CollectModelLIstSerializer(AuthSerializer):
    permission_key = PERMISSION_TASK
    message = serializers.SerializerMethodField()

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


class OidModelSerializer(UsernameSerializer):
    class Meta:
        model = OidMapping
        fields = "__all__"
        extra_kwargs = {}
